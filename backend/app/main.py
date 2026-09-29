"""FastAPI app factory + lifespan (starts the chat pub/sub subscriber).

The lifespan:
1. On startup: gets the Redis client (from app.state.redis if the test
   app set it, else from settings.redis_url), starts a background task
   that subscribes to `chat:events` and forwards to local WebSockets.
2. On shutdown: cancels the subscriber task, closes the Redis client.
"""
import asyncio
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api import auth, chats, feed, posts, uploads, users
from app.cache.redis_client import get_redis
from app.config import settings
from app.realtime.subscriber import run_subscriber
from app.realtime import ws as realtime_ws

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Resolve Redis: prefer app.state.redis (set by tests), else create from settings.
    if not getattr(app.state, "redis", None):
        app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)

    redis = app.state.redis

    # Force every `Depends(get_redis)` to return this exact instance.
    # Critical: the WebSocket endpoint and the chat endpoints must share
    # the same Redis (so pub/sub publish and subscribe match).
    async def _get_redis():
        return redis

    app.dependency_overrides[get_redis] = _get_redis

    subscriber_task = asyncio.create_task(run_subscriber(redis))
    app.state.subscriber_task = subscriber_task
    logger.info("app startup: subscriber task created")

    try:
        yield
    finally:
        logger.info("app shutdown: cancelling subscriber")
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass
        # Only close Redis if we created it (production), not if a test
        # fixture provided it (tests manage their own teardown).
        if not getattr(app.state, "redis_owned_by_test", False):
            try:
                await redis.aclose()
            except Exception:
                pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="Social Platform",
        version="0.1.0",
        docs_url="/_internal/docs",
        redoc_url="/_internal/redoc",
        openapi_url="/_internal/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(chats.router)
    app.include_router(feed.router)
    app.include_router(posts.router)
    app.include_router(uploads.router)
    app.include_router(uploads.local_router)
    app.include_router(realtime_ws.router)
    return app


app = create_app()