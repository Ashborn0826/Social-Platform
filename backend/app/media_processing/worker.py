"""Worker entry point.

Run via:
    python -m app.media_processing

Drains the `media:processing` queue, processes each attachment (with retry
+ DLQ), and shuts down gracefully on SIGINT/SIGTERM.

Same shape as Project 1's `app/__main__.py`: BRPOP loop with a short
timeout so cancellation is responsive, signal handlers that set a stop
Event.
"""
import asyncio
import logging
import signal

from redis.asyncio import Redis

from app.config import settings
from app.media_processing.process import process_attachment
from app.media_processing.queue import dequeue
from app.storage.factory import get_storage

logger = logging.getLogger(__name__)


async def run_worker(redis: Redis, storage, stop_event: asyncio.Event) -> None:
    """Long-running BRPOP loop. Stops when stop_event is set."""
    logger.info("media-processing worker started")
    while not stop_event.is_set():
        try:
            attachment_id = await dequeue(redis, timeout=0.5)
        except Exception as e:
            logger.warning("dequeue failed: %s", e)
            await asyncio.sleep(0.5)
            continue

        if attachment_id is None:
            continue

        logger.info("processing attachment %d", attachment_id)
        success = await process_attachment(attachment_id, storage, redis)
        if success:
            logger.info("attachment %d processed successfully", attachment_id)
        else:
            logger.warning("attachment %d permanently failed (DLQ)", attachment_id)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    storage = get_storage()
    stop = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            # Windows: SIGTERM isn't supported by asyncio's signal handlers.
            # SIGINT (Ctrl-C) still works.
            pass

    logger.info("media worker starting (redis=%s)", settings.redis_url)
    try:
        await run_worker(redis, storage, stop)
    finally:
        logger.info("media worker stopped")
        try:
            await redis.aclose()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())