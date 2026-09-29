# Design — add-social-platform

See `proposal.md` for motivation. This document covers **how** we build it.

## Context

Greenfield. The stack continues from Project 1: Python + FastAPI + Postgres + Redis + React/Vite. What's new in Project 2 is the set of patterns:

- **WebSockets** for real-time delivery (vs. request/response)
- **Redis pub/sub** for cross-worker message distribution (vs. cache + queue + rate-limit in P1)
- **Presigned URLs** for direct-to-storage uploads (vs. bytes flow through the API)
- **Object storage** with a swappable backend (vs. Postgres-only in P1)
- **Fan-out on write** for feed reads (vs. cache-aside reads in P1)
- **JWT auth** with refresh tokens (vs. no auth in P1)

These patterns layer onto the P1 stack rather than replace it: the rate limit, cache-aside, async pipeline, retry/DLQ patterns still apply, just for different concerns.

## Goals / Non-Goals

**Goals**
- Real-time chat: messages reach the recipient's open session within ~200ms across any number of API workers
- Feed reads are sub-100ms p99 even at 10k followers per user
- Media uploads don't bottleneck on the API server (client uploads directly to storage)
- Auth is correct, stateless, and easy to extend (refresh token rotation)
- Object storage is portable: same boto3 client code runs against MinIO, S3, or any S3-compatible store; local filesystem works without Docker

**Non-Goals (v1)**
- Likes, comments, reactions, mentions, hashtags
- Follow-graph ranking / algorithmic feed (timeline is reverse-chronological only)
- Group chat rooms, chat presence indicators, typing indicators, read receipts
- Search (full-text, user search)
- Push notifications (web push, mobile push)
- Email verification, password reset, OAuth/SSO
- Real-time notifications for new followers
- Video transcoding (videos get uploaded, stored, and downloaded as-is; no thumbnail, no streaming)
- Multi-region replication

## Architecture Overview

```
                       +-------------------+      WebSocket       +-----------+
 Browser (React + Vite)  <------------------>  /api/chats/ws   | FastAPI   |
  - /login              |                       REST           | (uvicorn) |
  - /feed               |                                       |   x N     |
  - /chats/:id          |                                       +-----+-----+
  - upload UI           |                                             |
                        |                                             |
                        |  CORS                                       |  +--+
                        |                                             |  |  |
                        |   +-------------+                           |  +--+
                            |  /api/uploads|  presigned PUT            |
                            |     (201)    +--------------------+      |
                            |             |                    |      |
                            |             v                    v      v
                            |     +------------------+    +---------------+
                            |     | Object storage   |    |   Postgres    |
                            |     | (S3 / FS)        |    | users, posts,  |
                            |     |                  |    | follows, msgs, |
                            |     +------------------+    | attachments,  |
                            |             ^               | timelines     |
                            |             |               +-------+-------+
                            |             |                       |
                            |             | thumbnail_key         |
                            |     +-------+--------+              |
                            |     | Worker (asyncio)|              |
                            +---->| drains uploads  +<-------------+
                                  | queue + thumbs  |
                                  +----------------+
                                       |       ^
                                       v       |
                                  +-----+--+   |
                                  | Redis |   |
                                  |  pub  |   |
                                  |  sub  |   |
                                  |  cache|---+
                                  |  rate |
                                  |  queue|
                                  +------+
```

The novelty vs Project 1 is the **WebSocket gateway** and the **object storage** with **direct upload**. Everything else is an extension of P1 patterns.

## Database Schema

```sql
-- Users (auth)
CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,            -- bcrypt
    display_name  VARCHAR(64) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Follows (graph)
CREATE TABLE follows (
    follower_id  BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    followee_id  BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (follower_id, followee_id)
);
CREATE INDEX follows_followee_idx ON follows (followee_id);

-- Posts
CREATE TABLE posts (
    id          BIGSERIAL PRIMARY KEY,
    author_id   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX posts_author_created_idx ON posts (author_id, created_at DESC);

-- Attachments (uploaded media)
CREATE TABLE attachments (
    id            BIGSERIAL PRIMARY KEY,
    owner_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content_type  VARCHAR(64) NOT NULL,
    size_bytes    BIGINT NOT NULL,
    storage_key   VARCHAR(512) UNIQUE NOT NULL,
    thumbnail_key VARCHAR(512),
    status        VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending|processing|ready|failed|expired
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at  TIMESTAMPTZ
);
CREATE INDEX attachments_owner_idx ON attachments (owner_id);

-- Post-Attachment join
CREATE TABLE post_attachments (
    post_id      BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    attachment_id BIGINT NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
    position     INT NOT NULL DEFAULT 0,
    PRIMARY KEY (post_id, attachment_id)
);

-- Permanent feed timeline (fan-out on write durable copy)
CREATE TABLE timeline_entries (
    user_id  BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    post_id  BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, post_id)
);
CREATE INDEX timeline_user_idx ON timeline_entries (user_id, inserted_at DESC);

-- Chats (1-on-1)
CREATE TABLE chats (
    id          BIGSERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chat_participants (
    chat_id  BIGINT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    user_id  BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (chat_id, user_id)
);

-- Messages
CREATE TABLE messages (
    id          BIGSERIAL PRIMARY KEY,
    chat_id     BIGINT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    sender_id   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX messages_chat_idx ON messages (chat_id, created_at DESC);
```

Notes:
- `attachments.status` is the state machine that the media-processing worker transitions: `pending → processing → ready | failed | expired`. The `expired` state is set by a sweep job (or on read, lazily).
- `timeline_entries` is the durable copy of the fan-out; the Redis sorted set is the cache. Reads check cache first, fall through to this table.
- No `messages.attachment_ids` for v1 — chat attachments are deferred to a later change. The schema can be extended with a `message_attachments` join table.

## API Contracts (summary; full contracts in specs/)

### REST

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/auth/signup` | — | Register. Returns user + tokens. |
| `POST` | `/auth/login` | — | Login. Returns user + tokens. |
| `POST` | `/auth/refresh` | refresh | Rotate tokens. |
| `POST` | `/api/posts` | bearer | Create a post. |
| `GET` | `/api/posts/{id}` | optional | Retrieve a post. |
| `GET` | `/api/users/{id}/posts` | optional | List a user's posts. |
| `POST` | `/api/users/{id}/follow` | bearer | Follow. |
| `DELETE` | `/api/users/{id}/follow` | bearer | Unfollow. |
| `GET` | `/api/feed` | bearer | User's feed. |
| `POST` | `/api/uploads` | bearer | Get a presigned upload URL. |
| `POST` | `/api/uploads/{id}/complete` | bearer | Mark upload complete. |
| `GET` | `/api/uploads/{id}` | bearer (owner) | Get attachment metadata. |
| `GET` | `/api/chats` | bearer | List chat rooms. |
| `GET` | `/api/chats/{id}/messages` | bearer (participant) | Message history. |

### WebSocket

```
wss://api/chats/ws?token=<jwt>
  ← {"type": "ready"}
  → {"type": "send", "to_user_id": "<id>", "text": "..."}    (lazy-creates chat)
  → {"type": "send", "chat_id": "<id>", "text": "..."}      (existing chat)
  ← {"type": "message", "chat_id": "<id>", "message": {...}}
```

## Auth flow (JWT)

```
POST /auth/signup {email, password, display_name}
  → hash password with bcrypt(cost=12)
  → INSERT users
  → sign access_token (HS256, 15 min TTL) and refresh_token (HS256, 7 day TTL, jti claim)
  → 201 {user, access_token, refresh_token}

POST /auth/login {email, password}
  → SELECT users WHERE email = ?
  → bcrypt.verify(password, user.password_hash)
  → sign tokens
  → 200 {user, access_token, refresh_token}

POST /auth/refresh {refresh_token}
  → decode + verify signature + expiry + jti not revoked
  → sign new tokens (rotate jti)
  → 200 {access_token, refresh_token}
```

For v1, refresh tokens are stateless JWTs with no revocation list. If you need logout-everywhere, you'd add a Redis-backed jti revocation set. Documented as future work.

## WebSocket + Redis pub/sub architecture

```
                     Worker 1                       Worker 2
                     -------                        -------
Client A <--WS--> conn_mgr[A] <--SUBSCRIBE--> chat:room:42 <--PUBLISH--> conn_mgr[B] <--WS--> Client B
                                                            ↑
Client C <--WS--> conn_mgr[C] --------SUBSCRIBE----------------+
                                                            |
              (A and C are on worker 1; B is on worker 2)
              (A sends message: PUBLISH chat:room:42 {message})
              (worker 1 fans out to A and C; worker 2 fans out to B)
```

When a sender publishes a message, **every worker** subscribed to that chat topic receives it. Each worker's `ConnectionManager` checks its local connection registry and forwards to the matching connections. A worker without any connections for that chat simply drops the message.

This means:
- **Send complexity: O(1)** — publish once, Redis handles delivery
- **Receive complexity: O(N workers)** — but workers are few (4-8 typical)
- **Total work per send: O(connected_participants)** — bounded by number of open WebSockets, not followers

Channels: `chat:room:{chat_id}` — one per chat.

## Presigned URL flow

```
CLIENT                           API                          OBJECT STORAGE
  |                               |                                |
  |---POST /api uploads----------->|                                |
  |    {content_type, size_bytes} |                                |
  |                               |--INSERT attachments(status=pending)
  |<--201 {upload_url, attachment_id}                              |
  |                               |                                |
  |---PUT upload_url--------------|------------------------------->|
  |    (file bytes)               |                                |
  |<----------------------------- 200 OK (uploaded) ---------------|
  |                               |                                |
  |---POST /api/uploads/{id}/complete--------------------------->|
  |                               |--HEAD storage_key to verify exists + non-zero size
  |                               |--UPDATE attachments SET status='ready'
  |                               |--LPUSH media:processing queue {attachment_id}
  |<--200 {attachment_id, status: "ready"}                         |
```

Key points:
- The API server never sees the file bytes
- The presigned URL has the content type and expiry baked in
- The `complete` call verifies the object exists before marking ready (defends against abandoned uploads)
- Media-processing is enqueued at `complete` time (when status flips to `ready`), so workers only process real uploads

## Fan-out on write

```
POST /api/posts {text, attachment_ids}
  -> INSERT posts
  -> SELECT follower_ids FROM follows WHERE followee_id = current_user
  -> For each follower:
       INSERT INTO timeline_entries (user_id, post_id)
       ZADD feed:{user_id} {post_id} {timestamp}
  -> 201 {post}
```

For a user with 10,000 followers, this is 10,000 inserts on the write path. We do this **synchronously inside the request** in v1 for simplicity. Two alternatives:

| Approach | Trade-off |
|----------|-----------|
| **Sync fan-out (chosen)** | Simple. Write latency grows with follower count. Acceptable up to ~10k followers. |
| **Async fan-out via worker** | Lower write latency. More complexity (queue + idempotency). |
| **Fan-out on read** | Cheap writes, expensive reads (joins across follows+posts). Doesn't scale for celebrity users. |

Documented future work: async fan-out for users with > N followers.

## Object storage abstraction

```python
class ObjectStorage(Protocol):
    def presigned_put_url(self, key: str, content_type: str, expires_seconds: int = 900) -> str: ...
    def presigned_get_url(self, key: str, expires_seconds: int = 900) -> str: ...
    def exists(self, key: str) -> bool: ...
    def size(self, key: str) -> int: ...
    def delete(self, key: str) -> None: ...
    def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...  # for tests
    def get_bytes(self, key: str) -> bytes: ...                                # for tests
```

Two implementations:

| Backend | When | URL format |
|---------|------|-----------|
| `LocalBackend` | dev, tests, no-Docker | Returns `/api/uploads/local/{key}` route served by the API |
| `S3Backend` | prod, MinIO via Docker | boto3 `generate_presigned_url("put_object", ...)` |

Config: `OBJECT_STORAGE_BACKEND=local|s3`, plus per-backend settings.

The contract is **identical** for the rest of the app. Tests use `LocalBackend` with an in-memory-or-temp-dir filesystem; production swaps to S3 by changing one env var. The boto3 client surface is the same on both.

## Async media processing

Same pattern as Project 1's click pipeline:

- Producer: `complete` handler `LPUSH media:processing {attachment_id}`
- Worker: `BRPOP media:processing` → fetch image → Pillow resize (max 400px wide) → upload thumbnail → `UPDATE attachments SET thumbnail_key=?, status='ready'`
- Retry: 3 attempts, 1s/4s/16s exponential backoff
- DLQ: `media:processing:dlq` for permanent failures

This is intentionally identical to P1's click pipeline. The lesson: this pattern is reusable across any "post-write processing" use case.

## Decisions

### D1. JWT over session cookies
- **JWT (chosen)**: stateless, scales horizontally, no session store.
- **Session cookies**: easier to revoke, slightly more secure (server-side state). But requires a session store on every request.

For a real-time social app where the same client might hit multiple workers, JWT is the natural fit. Documented future work: jti revocation list for logout-everywhere.

### D2. Fan-out on write over fan-out on read
- **Fan-out on write (chosen)**: O(followers) writes per post, O(1) reads. Great for celebrity timelines once warmed up.
- **Fan-out on read**: O(1) writes, O(followers) joins per feed read. Cheaper at low scale, breaks at high scale (Twitter switched FROM this).

### D3. Redis pub/sub for WebSocket fan-out vs per-worker connection state
- **Redis pub/sub (chosen)**: any worker can deliver any message. Horizontal scaling.
- **Sticky sessions**: route a user to the same worker for all their WS frames. No pub/sub, but doesn't survive worker restart and prevents load balancing.

### D4. Local filesystem backend for S3-compatible dev
- **Local FS (chosen)**: works without Docker, instant, testable. Same interface.
- **MinIO via Docker**: closer to production S3. Requires Docker (which we don't have locally).

We implement BOTH and pick at config time. The resume bullet is "pluggable object storage with S3-compatible interface (boto3) running against local filesystem in dev and S3/MinIO in production — same code path".

### D5. Pillow for thumbnails vs ImageMagick
- **Pillow (chosen)**: pure Python, no system dependencies, easy install.
- **ImageMagick**: more formats, better quality control. Requires system binary.

### D6. Cursor pagination on feed and chats
- **Cursor (`before=<post_id>`) (chosen)**: stable across new inserts, O(limit) query.
- **Offset pagination**: simple but breaks when new items are inserted (items shift).

### D7. Stateless JWT refresh tokens (no revocation list)
- **Stateless (chosen)**: zero server state, just verify signature.
- **Stateful with revocation list**: required for logout-everywhere.

Documented future work: a Redis-backed jti set for revocation.

### D8. WebSocket over Server-Sent Events
- **WebSocket (chosen)**: bidirectional. Required for typing indicators / presence (future).
- **SSE**: server-push only, simpler, but no client-push.

Chat is inherently bidirectional (client sends messages too), so WebSocket is the right choice. SSE could work for one-way notifications.

### D9. Bcrypt cost factor 12
- **Cost 12 (chosen)**: ~250ms per hash on modern hardware. Standard for 2024+.
- **Cost 10**: faster (~100ms) but weaker against offline attacks.
- **Argon2**: newer, more configurable. Adds a dependency.

Documented future work: argon2 if we ever need better resistance to GPU attacks.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Sync fan-out blocks the request for high-follower users | Future: async fan-out for users with > N followers |
| JWT refresh tokens can't be revoked without a server-side list | Acceptable for v1. Documented future work. |
| Local FS backend doesn't enforce S3's content-type validation | Tests run with explicit content type assertions |
| WebSocket connection state is per-worker (lost on worker restart) | Clients reconnect with exponential backoff. Documented in WS protocol. |
| No rate limit on signup/login | Inherit P1's per-IP rate limit (reuse `enforce_rate_limit`). No per-user limit yet. |
| Attachment of >50MB will fail at presign time (we reject) but not enforce actual size | Trust the size_bytes hint from client; verify object size at `complete`. |
| Postgres connection pool exhaustion under high fan-out | Larger pool size (config); async fan-out defers this. |

## Migration Plan

Greenfield. Steps:

1. Apply Alembic migrations: `alembic upgrade head` creates all tables
2. Start API: `uvicorn app.main:app --workers 4 --port 8000`
3. Start worker: `python -m app` (or `arq app.worker.WorkerSettings` — see D in Phase 5)
4. Frontend: `npm run dev`

## Open Questions

None. All decisions taken above.
