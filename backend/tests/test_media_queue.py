"""Redis-backed media processing queue tests (fakeredis)."""
import pytest


async def test_enqueue_dequeue_round_trip(redis_client):
    from app.media_processing.queue import enqueue, dequeue

    await enqueue(redis_client, 42)
    aid = await dequeue(redis_client, timeout=0.5)
    assert aid == 42


async def test_enqueue_dequeue_fifo_order(redis_client):
    """LPUSH adds to head, BRPOP pops from tail. So jobs are FIFO."""
    from app.media_processing.queue import enqueue, dequeue

    await enqueue(redis_client, 1)
    await enqueue(redis_client, 2)
    await enqueue(redis_client, 3)

    assert await dequeue(redis_client, timeout=0.5) == 1
    assert await dequeue(redis_client, timeout=0.5) == 2
    assert await dequeue(redis_client, timeout=0.5) == 3


async def test_dequeue_empty_returns_none(redis_client):
    from app.media_processing.queue import dequeue
    assert await dequeue(redis_client, timeout=0.2) is None


async def test_push_to_dlq_lands_in_dlq_key(redis_client):
    from app.media_processing.queue import push_to_dlq

    await push_to_dlq(redis_client, 42, "boom")
    size = await redis_client.llen("media:processing:dlq")
    assert size == 1

    raw = await redis_client.rpop("media:processing:dlq")
    import json

    payload = json.loads(raw)
    assert payload["attachment_id"] == 42
    assert payload["error"] == "boom"


async def test_enqueue_isolated_from_dlq(redis_client):
    """Enqueueing to the main queue doesn't affect the DLQ."""
    from app.media_processing.queue import enqueue, push_to_dlq

    await enqueue(redis_client, 1)
    await push_to_dlq(redis_client, 2, "err")

    main_size = await redis_client.llen("media:processing")
    dlq_size = await redis_client.llen("media:processing:dlq")
    assert main_size == 1
    assert dlq_size == 1