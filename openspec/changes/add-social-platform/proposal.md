## Why

Project 2 builds a real-time social platform with chat, feed, and media uploads. The goal is to teach the four patterns that distinguish a modern social app from a CRUD API: **WebSocket-based real-time delivery**, **Redis pub/sub for cross-process message routing**, **presigned-URL media uploads** that bypass the API server, and **fan-out-on-write** for sub-100ms feed reads. These complement Project 1's read-heavy URL shortener with a write-heavy social workload — together they cover the patterns you'll see in most production backends.

## What Changes

- New REST API for users, posts, follows, chats, and attachments
- New WebSocket gateway for real-time chat delivery (Redis pub/sub for cross-worker routing)
- New object-storage abstraction (S3 in production, local filesystem in dev) with presigned-URL upload flow
- New background worker for async media processing (thumbnail generation)
- New feed fan-out-on-write for O(1) feed reads
- New JWT-based auth (signup / login / refresh) — every authenticated endpoint validates a bearer token
- React frontend: feed view, chat room view, upload UI

## Capabilities

### New Capabilities

- `user-accounts`: Signup, login, JWT issuance and refresh; password hashing with bcrypt
- `posts`: Create, retrieve, list text posts owned by an authenticated user; posts are immutable
- `media-uploads`: Presigned-URL upload flow (client uploads directly to storage), attachment metadata, shared by posts and chat
- `feed`: User feed with fan-out-on-write — followers get the post on their personal timeline on publish
- `chat`: 1-on-1 chat with WebSocket-based real-time delivery, Redis pub/sub for cross-worker routing, message history persistence
- `media-processing`: Background worker that processes uploaded media (thumbnail generation) with retry + DLQ

### Modified Capabilities

None — greenfield project.

## Impact

- New backend service (FastAPI) with REST + WebSocket endpoints
- New background worker (asyncio, runs alongside API server)
- Postgres schema: `users`, `follows`, `posts`, `attachments`, `timelines`, `chats`, `chat_participants`, `messages`
- Redis: pub/sub for WebSocket routing (NEW usage beyond Project 1's cache + queue + rate-limit)
- Object storage: abstraction layer with `local` (filesystem) and `s3` (boto3) backends. Default = local; production = S3 by config.
- New frontend views: feed page, chat room page, upload UI
- New Python deps: `python-jose[cryptography]` (JWT), `passlib[bcrypt]` (password hashing), `boto3` (S3 SDK), `pillow` (thumbnail), `python-multipart` (multipart fallback), `websockets` (FastAPI), `moto[s3]` (test mock for S3)
- Local infrastructure: Postgres + Redis (docker-compose; P1 already covered this). MinIO is **optional** via Docker for the S3 backend — tests use moto so no Docker is required for the test suite.
