"""Redis-backed queue for media processing jobs.

Same pattern as Project 1's click pipeline: a Redis list as a queue, with
a dead-letter queue (DLQ) for permanent failures. JSON payload so we can
extend with metadata later (e.g., retry count, original requester).

Keys:
    media:processing      LPUSH by producer, BRPOP by worker
    media:processing:dlq  RPUSH on permanent failure; humans inspect
"""
import json

MEDIA_QUEUE_KEY = "media:processing"
MEDIA_DLQ_KEY = "media:processing:dlq"


async def enqueue(redis, attachment_id: int) -> None:
    """Add a thumbnail-generation job to the queue."""
    payload = json.dumps({"attachment_id": int(attachment_id)})
    await redis.lpush(MEDIA_QUEUE_KEY, payload)


async def dequeue(redis, timeout: float = 1.0) -> int | None:
    """Block-pop one job. Returns attachment_id or None on timeout."""
    result = await redis.brpop(MEDIA_QUEUE_KEY, timeout=timeout)
    if result is None:
        return None
    _, value = result
    payload = json.loads(value)
    return int(payload["attachment_id"])


async def push_to_dlq(redis, attachment_id: int, error: str) -> None:
    """Push a permanently-failed job to the DLQ with the error context."""
    payload = json.dumps({"attachment_id": int(attachment_id), "error": error})
    await redis.rpush(MEDIA_DLQ_KEY, payload)