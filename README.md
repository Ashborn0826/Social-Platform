# Social Platform

A full-stack real-time social platform with chat, feed, and media uploads. Built as a learning project to demonstrate system-design concepts (WebSockets, Redis pub/sub, fan-out on write, presigned URLs, async pipelines) using the OpenSpec spec-driven workflow.

This is **Project 2** in a two-project series. [Project 1](../01-url-shortener/) is a URL shortener built with the same workflow; together they cover the patterns you'll see in most production backends.

## Features

- **User accounts** with bcrypt-hashed passwords + JWT (HS256) access + refresh tokens with type-claim separation
- **Text posts** with attachment support (image/video via presigned URLs)
- **Direct-to-storage uploads** — the API server never sees file bytes (LocalBackend for dev, S3Backend for production via boto3)
- **Social graph + feed** with fan-out-on-write — posts appear in followers' timelines within milliseconds, cached in Redis sorted sets
- **1-on-1 real-time chat** over WebSockets, fanned out across workers via Redis pub/sub
- **Async thumbnail pipeline** with Pillow — upload, complete, enqueue, worker generates 400-px-wide JPEG with retry + DLQ
- **Cursor pagination** on feed, posts, and message history
- **CORS-enabled** React frontend (create-URL form + stats dashboard + chat)

## Tech stack

| Layer | Choice |
|-------|--------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, Alembic |
| Frontend | React 19, TypeScript, Vite, Vitest, @testing-library/react |
| Storage | Postgres 15 (production), SQLite (tests) |
| Cache + queue + pub/sub | Redis 7 |
| Object storage | `LocalBackend` (filesystem, dev/tests) / `S3Backend` (boto3, prod/MinIO) behind a shared `ObjectStorage` Protocol |
| WebSocket gateway | FastAPI native WebSocket + Redis pub/sub |
| Worker | asyncio + raw Redis list (LPUSH/BRPOP) with retry + DLQ |
| Tests | pytest + pytest-asyncio (backend), Vitest + jsdom (frontend), fakeredis (backend) |

## Quick start (with Docker for Postgres + Redis)

Prerequisites: Docker, Docker Compose, Node 18+, Python 3.11+.

```bash
# 1. Start Postgres + Redis
docker compose -f infra/docker-compose.yml up -d

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1                  # Windows
# source .venv/bin/activate                 # Linux/macOS
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000  # API + WebSocket gateway
python -m app.media_processing             # Thumbnail worker (separate shell)

# 3. Frontend
cd ../frontend
npm install
npm run dev
```

Open `http://localhost:5173`. API at `http://localhost:8000`. Swagger UI at `http://localhost:8000/_internal/docs`.

## Quick start (tests only — no infrastructure needed)

```bash
# Backend — 182 tests, ~45s
cd backend
.venv\Scripts\python.exe -m pytest

# Frontend — see frontend/README.md
cd ../frontend
npm test
```

The backend tests run against SQLite (file-based, auto-cleaned between tests) and fakeredis. No Postgres or Redis required.

## Architecture

```
                       +-------------------+      WebSocket       +-----------+
 Browser (React + Vite)  <------------------>  /api/chats/ws   | FastAPI   |
  - create form         |                       REST           | (uvicorn) |
  - chat panel          |                                       |   x N     |
  - upload UI           |                                       +-----+-----+
                        |  CORS                                     |
                        |                                           |
                        |   +-------------+                       +--+
                            | Redis     |                       |  |
                            |  - cache   |  <-- cache-aside -->  |  |
                            |  - queue   |  <-- async pipeline -> |  |
                            |  - pub/sub |  <-- WS fanout     --> |  |
                            +-------------+                       +--+
                                  |
                                  v
                            +----------+
                            | Postgres |
                            | users    |
                            | posts    |
                            | follows  |
                            | timeline |
                            | chats    |
                            | messages |
                            | attaches |
                            +----------+
```

Three Redis namespaces stay isolated:

| Prefix | Purpose | Type |
|--------|---------|------|
| `feed:{user_id}` | Cache-aside for the timeline | sorted set |
| `rl:{ip}` | Rate-limit counter (carried from P1) | counter |
| `clicks:queue` / `clicks:dlq` | URL redirect events (carried from P1) | list |
| `chat:events` | Pub/sub channel for chat messages | pub/sub |
| `media:processing` / `media:processing:dlq` | Thumbnail-generation jobs | list |

## API endpoints

### REST

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/auth/signup` | — | Register. Returns `{access_token, refresh_token, user}`. |
| `POST` | `/auth/login` | — | Login. Returns same shape. |
| `POST` | `/auth/refresh` | refresh | Rotate tokens. |
| `POST` | `/api/posts` | bearer | Create a post. Body: `{text, attachment_ids?}`. |
| `GET` | `/api/posts/{id}` | optional | Retrieve a post + author. |
| `GET` | `/api/users/{id}/posts` | optional | List a user's posts (cursor pagination). |
| `POST` | `/api/users/{id}/follow` | bearer | Follow. 400 self / 404 unknown / 409 already. |
| `DELETE` | `/api/users/{id}/follow` | bearer | Unfollow. 204 / 404 not-following. |
| `GET` | `/api/feed` | bearer | User's feed (cursor pagination, hydrated with attachments). |
| `POST` | `/api/uploads` | bearer | Get a presigned upload URL. |
| `POST` | `/api/uploads/{id}/complete` | bearer | Mark upload complete; queues thumbnail if image. |
| `GET` | `/api/uploads/{id}` | bearer (owner) | Attachment metadata + presigned URL. |
| `GET` | `/api/chats` | bearer | List chats with peer + last message. |
| `POST` | `/api/chats/{peer_user_id}` | bearer | Lazy-create chat with peer. |
| `GET` | `/api/chats/{chat_id}/messages` | bearer (participant) | Message history (cursor pagination). |

### WebSocket

```
wss://api/chats/ws?token=<jwt>
  ← {"type": "ready"}
  → {"type": "send", "to_user_id"|"chat_id", "text"}
  ← {"type": "message", "chat_id", "message": {...}}
```

Close codes: `4401` for missing/invalid token.

## Configuration

All backend config via env vars (see `backend/.env.example`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `postgresql+asyncpg://social:social@localhost:5432/social` | SQLAlchemy async URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL (cache + queue + pub/sub) |
| `JWT_SECRET` | dev placeholder | **CHANGE IN PROD** |
| `OBJECT_STORAGE_BACKEND` | `local` | `local` (filesystem) or `s3` (boto3) |
| `LOCAL_STORAGE_DIR` | `/tmp/social-storage` | Where LocalBackend stores files |
| `S3_BUCKET` / `S3_REGION` / `S3_ENDPOINT_URL` | — | S3Backend config (for MinIO set endpoint) |
| `API_HOST` | `http://localhost:8000` | Used to build presigned local URLs |
| `STORAGE_SECRET` | dev placeholder | HMAC secret for LocalBackend signed URLs |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS allow-list |
| `DEBUG` | `false` | Enable SQLAlchemy echo |

## Object storage abstraction

Both backends implement the same `ObjectStorage` Protocol:

```python
class ObjectStorage(Protocol):
    def presigned_put_url(self, key, content_type, expires_seconds=900) -> str: ...
    def presigned_get_url(self, key, content_type, expires_seconds=900) -> str: ...
    def exists(self, key) -> bool: ...
    def size(self, key) -> int: ...
    def delete(self, key) -> None: ...
    def put_bytes(self, key, data, content_type) -> None: ...
    def get_bytes(self, key) -> bytes: ...
```

- **`LocalBackend`** — stores files under `LOCAL_STORAGE_DIR`. Presigned URLs are URLs to our own `/api/uploads/local/{key}` endpoint, signed with HMAC-SHA256. Works without Docker, ideal for dev/tests.
- **`S3Backend`** — uses `boto3.generate_presigned_url`. Works against real AWS S3, MinIO, Cloudflare R2, Backblaze B2, or any S3-compatible service.

The application code is identical on both. Swap by setting `OBJECT_STORAGE_BACKEND=s3` in production.

## OpenSpec workflow

This project was built spec-first using [OpenSpec](https://github.com/Fission-AI/OpenSpec):

- **`openspec/specs/`** — the live contract. Six capability specs: `user-accounts`, `posts`, `media-uploads`, `feed`, `chat`, `media-processing`. Every pytest maps to at least one scenario in one of these.
- **`openspec/changes/archive/2026-09-29-add-social-platform/`** — historical change with `proposal.md`, `design.md`, `tasks.md`. The full record of WHY/WHAT/HOW for this project.
- **`openspec/config.yaml`** — schema config (`spec-driven`).

Future changes that touch these capabilities will be written as **deltas** against the live specs, then archived the same way.

## Project structure

```
02-social-platform/
├── backend/
│   ├── app/
│   │   ├── api/             REST + WebSocket routes (auth, chats, feed, posts, uploads)
│   │   ├── auth/            bcrypt + JWT helpers
│   │   ├── cache/           Redis client dependency
│   │   ├── db/              SQLAlchemy models, session, repositories
│   │   ├── feed/            fan-out service (cache-aside reads + fan-out writes)
│   │   ├── media_processing/ thumbnail queue + worker + Pillow pipeline
│   │   ├── realtime/        ConnectionManager + Redis subscriber + WS handler
│   │   ├── schemas.py       Pydantic models
│   │   ├── storage/         ObjectStorage Protocol + Local/S3 backends
│   │   ├── config.py        pydantic-settings
│   │   └── main.py          FastAPI app factory + lifespan (starts subscriber)
│   ├── alembic/             9 migrations (users, posts, follows, timeline,
│   │                         chats, chat_participants, messages, attachments,
│   │                         post_attachments)
│   ├── tests/               182 tests
│   └── scripts/smoke.py     (Phase 5+ future work — placeholder)
├── frontend/                (carried from P1, similar setup — see frontend/README.md)
├── infra/
│   └── docker-compose.yml   Postgres 15 + Redis 7
├── openspec/
│   ├── specs/               Live contract (6 capability specs)
│   ├── changes/
│   │   └── archive/
│   │       └── 2026-09-29-add-social-platform/   Proposal + design + tasks
│   └── config.yaml
├── notes/                   (gitignored — teaching content)
│   ├── phase-{1..5}-explanation.md
│   ├── phase-{1..5}-teaching.md
│   ├── phase-1-2-recap.md
│   └── bugs.md
├── .gitignore
└── README.md                (this file)
```

## Key design decisions

| Decision | Why |
|----------|-----|
| Direct-to-storage uploads | The API server never touches file bytes; presigned URLs bypass it entirely |
| Fan-out on write (not read) | O(1) reads at the cost of O(followers) writes — acceptable up to ~10k followers |
| Cursor pagination everywhere | Stable across new inserts, no offset drift |
| Same 404 for "unknown" and "not yours" | No enumeration of which user_ids / attachment_ids exist |
| Composite PKs on Follow / ChatParticipant | Natural keys; INSERT...ON CONFLICT trivial |
| Redis pub/sub for cross-worker WebSocket | Send once; every worker fans out to its local connections |
| Process-local ConnectionManager singleton | Can't DI per-process state via Depends |
| Stateless JWT (no session table) | Scales horizontally; each worker verifies independently |
| Refresh token rotation | Compromised token has bounded damage window |
| Same async pipeline pattern across the codebase (P1 clicks, P2 media) | Producer → Redis list → consumer → retry → DLQ; learn once, reuse everywhere |
| Status state machine on Attachment | pending → processing → ready \| failed; explicit transitions |

## Lessons learned (the bugs we hit)

Full root-cause write-ups in `notes/bugs.md`. Highlights:

- **Bug 1 (P1)**: SQLite rejects `pool_size` / `max_overflow`. Use dialect-aware engine kwargs.
- **Bug 2 (P1)**: Catch-all `IntegrityError → "duplicate"` hides real errors. Inspect `error.orig` before mapping.
- **Bug 3 (P1)**: SQLite only auto-fills `INTEGER PRIMARY KEY`, not `BIGINT PRIMARY KEY`. Use `BigInteger().with_variant(Integer(), "sqlite")`.
- **Bug 4 (P1)**: FastAPI `/docs` shadows our `/{short_code}`. Move defaults to `/_internal/*`.
- **Bug 5 (P2)**: Self-referencing SQL queries can hit ambiguous column names.
- **Bug 6 (P2)**: Mock objects must satisfy the full interface, not just the method under test.
- **Bug 7 (P2)**: WebSocket is full-duplex; drain server-initiated messages before testing client flows.
- **Bug 8 (P2)**: State machines need explicit transitions for every edge — `update_thumbnail` had to restore `status='ready'`.
- **Bug 9 (P2)**: `session.expire_all()` triggers async greenlet failures — use a `fresh_session` fixture for cross-session verification reads.

The general lesson: **carry the fix forward**. Bugs in P1 became the starting pattern for P2 — we didn't hit them again because we knew what to avoid.

## What's NOT in this README (production concerns)

This is a learning codebase. Production concerns NOT addressed:

- **TLS / HTTPS** — run behind Caddy / nginx / a cloud load balancer
- **Managed databases** — swap docker-compose for RDS / Cloud SQL + ElastiCache / MemoryStore
- **Push notifications** — for offline mobile/web push when chat messages arrive
- **Read receipts, typing indicators** — standard chat features deferred
- **Multi-region** — Redis pub/sub is single-region; use Kafka/RabbitMQ/NATS for replication
- **Image rotation** — phone photos with EXIF orientation should be rotated before thumbnailing
- **Garbage collection** — orphaned files in storage are not cleaned up
- **Rate limiting per user** (we have per-IP only)

Each is a separate change with its own OpenSpec change proposal.

## Test results

```
182 passed in 45.10s
```

62 from Phase 1 + 2 carryover, broken down by area:
- Auth (JWT + bcrypt): 19 tests
- Posts (CRUD + cursor pagination): 14 tests
- Storage (Local + S3 + factory): 21 tests
- Uploads (presigned + complete + local download): 17 tests
- Feed (fan-out + repository): 27 tests
- Chat (REST + WebSocket + repository): 21 tests
- Chat connection manager (process-local): 10 tests
- Media processing (thumbnail + worker + retry + DLQ + e2e): 22 tests
- (Phase 1 carries: 11 tests from URL shortener area — mostly cross-cutting config tests)

## What's next

For your resume, this is a solid portfolio piece:

> Built a real-time social platform with WebSocket-based chat, fan-out-on-write feeds, presigned-URL media uploads, and async thumbnail processing. Backend in Python + FastAPI + SQLAlchemy + Redis + Pillow; frontend in React + Vite + TypeScript; spec-driven via OpenSpec with full test coverage (182 tests) and end-to-end integration tests for the chat pipeline.

If you want to extend it, the natural next changes (each its own OpenSpec change proposal):

1. **Email verification + password reset** (uses the user-accounts spec)
2. **Likes / comments / mentions** (extends posts spec)
3. **Group chat rooms** (extends chat spec)
4. **Push notifications** (new capability)
5. **Search** (full-text on posts + messages)

Each is scoped, has its own design decisions, and teaches a new pattern. The same workflow as this project: explore → propose → apply phases → verify → archive.

## License

MIT (educational use).