## 1. Phase 1 — Auth (signup/login/JWT) + Users + Posts CRUD

- [x] 1.1 Reuse backend/ skeleton from P1: copy pyproject.toml, alembic config, db session/repository, conftest pattern and verify `pip install -e '.[dev]'` succeeds
- [x] 1.2 Add auth deps to pyproject: `python-jose[cryptography]`, `passlib[bcrypt]`, `bcrypt==4.0.1` and verify install succeeds
- [x] 1.3 Add User SQLAlchemy model (id, email UNIQUE, password_hash, display_name, created_at) + Alembic migration and verify `alembic upgrade head` creates the table
- [x] 1.4 Implement `backend/app/auth/passwords.py` with `hash_password(plain) -> str` (bcrypt cost=12) and `verify_password(plain, hashed) -> bool` and verify unit tests cover both
- [x] 1.5 Implement `backend/app/auth/tokens.py` with `create_access_token(user_id)`, `create_refresh_token(user_id, jti)`, `decode_token(token) -> dict` (HS256, jti claim) and verify unit tests cover expiry, signature, and tampering
- [x] 1.6 Implement `backend/app/auth/deps.py` with `current_user(token) -> User` FastAPI dependency that decodes + looks up the user and returns 401 on any failure
- [x] 1.7 Implement `POST /auth/signup` + `POST /auth/login` + `POST /auth/refresh` endpoints with Pydantic request validation and verify integration tests cover success, duplicate-email 409, wrong-password 401, expired-refresh 401
- [x] 1.8 Add Post SQLAlchemy model (id, author_id FK, text, created_at) + Alembic migration and verify upgrade succeeds
- [x] 1.9 Implement `POST /api/posts` (auth required, validates text length 1-2000), `GET /api/posts/{id}` (public), `GET /api/users/{id}/posts?limit=&before=` (cursor pagination) and verify integration tests cover all status codes
- [x] 1.10 Phase 1 verification: `pytest -q` all green, smoke-check that POST /auth/signup → POST /api/posts round-trip works end-to-end; write `notes/phase-1-explanation.md` (system-design walkthrough) AND `notes/phase-1-teaching.md` (zero-knowledge tutorial covering HTTP, FastAPI, JWT, bcrypt, SQLAlchemy, async/await, status codes, cursors)

## 2. Phase 2 — Media upload pipeline (presigned URLs, S3/FS abstraction)

- [x] 2.1 Add media deps to pyproject: `boto3`, `pillow`, `python-multipart`, `moto[s3]` (dev) and verify install succeeds
- [x] 2.2 Implement `backend/app/storage/base.py` with the `ObjectStorage` Protocol (presigned_put_url, presigned_get_url, exists, size, delete, put_bytes, get_bytes) and verify it imports cleanly
- [x] 2.3 Implement `backend/app/storage/local.py` with `LocalBackend` (filesystem under `settings.local_storage_dir`) — returns presigned URLs as `/api/uploads/local/{key}?expires=...&sig=...` and verify unit tests cover put/get/exists/size/delete round-trip
- [x] 2.4 Implement `backend/app/storage/s3.py` with `S3Backend` using boto3 (uses `generate_presigned_url`) and verify against moto in tests
- [x] 2.5 Add `backend/app/storage/factory.py` `get_storage() -> ObjectStorage` (lru_cache, reads `settings.object_storage_backend`) and verify integration test that switching env var changes backend
- [x] 2.6 Add Attachment SQLAlchemy model (id, owner_id, content_type, size_bytes, storage_key UNIQUE, thumbnail_key, status with default 'pending', created_at, completed_at) + Alembic migration and verify upgrade succeeds
- [x] 2.7 Implement `POST /api/uploads` (auth, validates content_type in image/*|video/*, size_bytes ≤ 50MB) returning `{upload_url, attachment_id, storage_key, expires_at}` and verify integration tests cover happy path + content-type rejection + size rejection
- [x] 2.8 Implement `POST /api/uploads/{id}/complete` (auth, ownership check) that verifies object exists in storage + size > 0, transitions to status='ready', and verify integration tests cover success + object-not-found 409
- [x] 2.9 Implement `GET /api/uploads/{id}` with ownership check (404 for non-owners — don't leak existence) and verify integration tests cover owner + non-owner paths
- [x] 2.10 Add a local-storage download route at `GET /api/uploads/local/{key}?sig=...&expires=...` (only for LocalBackend) and verify it serves the uploaded bytes
- [x] 2.11 Cross-spec validation: extend `POST /api/posts` to accept `attachment_ids` and reject (a) attachments from other users with 403, (b) attachments not in `ready` status with 409 and verify integration tests cover both
- [x] 2.12 Phase 2 verification: `pytest -q` all green, end-to-end test "upload a JPEG to local backend, complete, attach to post" passes; write `notes/phase-2-explanation.md` AND `notes/phase-2-teaching.md` (zero-knowledge tutorial covering presigned URLs, S3 SDK, content-type validation, multipart upload, why client uploads directly)

## 3. Phase 3 — Feed with fan-out on write

- [ ] 3.1 Add follow model (`follower_id`, `followee_id`, `created_at`, composite PK) + timeline_entries model (`user_id`, `post_id`, `inserted_at`, composite PK) + Alembic migration and verify upgrade succeeds
- [ ] 3.2 Implement `POST /api/users/{id}/follow` (auth, blocks self-follow, 409 on duplicate) + `DELETE /api/users/{id}/follow` (auth, 404 if not following) and verify integration tests cover all paths
- [ ] 3.3 Implement `FollowRepository.follow(follower_id, followee_id)`, `unfollow`, `list_follower_ids_of(user_id) -> list[int]` and verify unit tests
- [ ] 3.4 Implement fan-out: extend `POST /api/posts` to (a) insert post, (b) fetch follower ids, (c) bulk INSERT into timeline_entries, (d) ZADD into Redis sorted set `feed:{user_id}` for each follower; verify integration test "create post with 5 followers -> 5 timeline rows + 5 Redis zset entries"
- [ ] 3.5 Implement `GET /api/feed?limit=&before=` that reads from Redis sorted set first, falls through to Postgres timeline_entries on miss, hydrates each post with author + attachment presigned-URLs, and verify integration tests cover populated feed + empty feed + cache-miss fallback
- [ ] 3.6 Implement feed eviction: when a post is deleted (admin only, future work) or a user unfollows, the unfollowed user's posts from before the unfollow remain (documented in spec — historical posts not retroactively removed); verify there's a test that documents this behavior
- [ ] 3.7 Phase 3 verification: `pytest -q` all green, end-to-end "user A follows B, B posts, A's feed contains B's post"; write `notes/phase-3-explanation.md` AND `notes/phase-3-teaching.md` (zero-knowledge tutorial covering follow graphs, fan-out on write vs read, write amplification, sorted sets, cursor pagination)

## 4. Phase 4 — WebSocket gateway + 1-on-1 chat with Redis pub/sub

- [ ] 4.1 Add websockets to deps (`fastapi[standard]` includes it, or `pip install websockets`) and verify install succeeds
- [ ] 4.2 Add Chat (id, created_at), ChatParticipant (chat_id, user_id composite PK), Message (id, chat_id, sender_id, text, created_at) models + Alembic migration and verify upgrade succeeds
- [ ] 4.3 Implement `POST /api/chats/{peer_user_id}` (auth, lazily creates chat) — or accept `to_user_id` field — for the lazy-create scenario and verify integration test
- [ ] 4.4 Implement `GET /api/chats` returning `{chats: [{chat_id, peer, last_message, unread}, ...]}` and verify integration test with no chats + 2 chats
- [ ] 4.5 Implement `GET /api/chats/{id}/messages?limit=&before=` with participant check (403 for non-participants) and verify integration tests
- [ ] 4.6 Implement `backend/app/realtime/connection_manager.py` with `register(user_id, ws)`, `unregister(user_id, ws)`, `send_to_user(user_id, payload)` that finds all local connections for a user and sends — verify unit tests with mocked WebSockets
- [ ] 4.7 Implement WebSocket endpoint `WS /api/chats/ws?token=<jwt>` that (a) authenticates, (b) registers connection, (c) starts Redis subscriber task, (d) handles incoming `send` messages by persisting + publishing to `chat:room:{chat_id}`, (e) cleans up on disconnect; verify integration test with TestClient or websocket client
- [ ] 4.8 Implement Redis pub/sub subscriber: on receiving a message from `chat:room:{chat_id}`, iterate the local connection registry and forward to matching WebSockets; verify integration test with two simulated workers (sharing Redis, separate connection managers)
- [ ] 4.9 Phase 4 verification: `pytest -q` all green, end-to-end test "two clients on simulated separate workers exchange messages in real time"; write `notes/phase-4-explanation.md` AND `notes/phase-4-teaching.md` (zero-knowledge tutorial covering WebSockets vs HTTP, connection state, pub/sub, channels, message persistence, optimistic send)

## 5. Phase 5 — Background media processing worker (thumbnails)

- [ ] 5.1 Verify Pillow is installed (from Phase 2 pyproject) and verify `python -c "from PIL import Image; print(Image.__version__)"`
- [ ] 5.2 Implement `backend/app/media_processing/thumbnail.py` with `generate_thumbnail(source_bytes, max_width=400) -> bytes` using Pillow resize with aspect ratio preserved, JPEG output and verify unit tests with a small fixture image
- [ ] 5.3 Implement `backend/app/media_processing/queue.py` with `enqueue(redis, attachment_id)`, `dequeue(redis, timeout=1.0)`, `push_to_dlq(...)` (carry over from P1's click pipeline pattern)
- [ ] 5.4 Implement `backend/app/media_processing/process.py` with `process_attachment(redis, attachment_id)` that (a) updates status='processing', (b) fetches original bytes from storage, (c) checks content_type is image/*, (d) generates thumbnail, (e) uploads to storage as `{key}.thumb`, (f) updates status='ready' + thumbnail_key, with retry+DLQ on failure
- [ ] 5.5 Wire up: extend `POST /api/uploads/{id}/complete` to LPUSH to `media:processing` after the storage verification, AND add idempotency (don't re-enqueue if already in `processing` or `ready` with thumbnail_key set)
- [ ] 5.6 Add `python -m app.media_processing.worker` entry-point that runs the BRPOP loop with graceful shutdown (carry over from P1's `app/__main__.py` pattern); verify it boots in a test
- [ ] 5.7 Update `app/__main__.py` to dispatch: if env var `WORKER_ROLE=clicks` → run click worker (P1), else → run media-processing worker (P2); or use two separate entry points
- [ ] 5.8 Phase 5 verification: `pytest -q` all green, end-to-end test "upload small JPEG → complete → wait → attachment.thumbnail_key is set"; write `notes/phase-5-explanation.md` AND `notes/phase-5-teaching.md` (zero-knowledge tutorial covering async processing, retry with exponential backoff, idempotency, status state machine, why separate workers)

## 6. Phase 6 — Verify + archive + push

- [ ] 6.1 Run `openspec validate add-social-platform --strict` and ensure it passes
- [ ] 6.2 Run full backend test suite + frontend test suite; capture counts
- [ ] 6.3 Write a project-root `README.md` (similar to P1's) with quick-start, architecture diagram, API summary, env vars, OpenSpec workflow note
- [ ] 6.4 Run `openspec archive add-social-platform --yes` to merge the delta specs into `openspec/specs/`
- [ ] 6.5 Final commit + push to GitHub remote (ask user for the URL when ready)
