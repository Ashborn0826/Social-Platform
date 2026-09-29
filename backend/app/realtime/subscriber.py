"""Redis pub/sub bridge for chat messages.

Each worker subscribes to `chat:events` on startup. When a chat message is
sent via WebSocket, the sender's worker publishes to this channel. All
subscribed workers (including the sender's) receive the message and
forward to their local ConnectionManager connections.

Architecture (one-worker view):

   Worker 1 (client A + C connected)
     ├─ WS A ──┐
     │         ├─→ ConnectionManager[A,C] ──→ Redis subscriber ──┐
     └─ WS C ──┘                                                   │
                                                                  ↓
   Worker 2 (client B connected)                            chat:events ←──┘
     └─ WS B ──→ ConnectionManager[B] ──→ Redis subscriber ──→ forward to B
```

The publish-then-fanout pattern means: the sender doesn't need to know
where the recipient is connected. Any worker can deliver any message.
"""
import asyncio
import json
import logging

from redis.asyncio import Redis

from app.realtime.connection_manager import manager

logger = logging.getLogger(__name__)

CHANNEL = "chat:events"


async def run_subscriber(redis: Redis) -> None:
    """Long-running task. Subscribe + forward until cancelled.

    Uses `get_message(timeout=1.0)` polling so cancellation is responsive.
    """
    pubsub = redis.pubsub()
    await pubsub.subscribe(CHANNEL)
    logger.info("chat subscriber started on channel=%s", CHANNEL)
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if message is None or message.get("type") != "message":
                continue
            try:
                payload = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("subscriber: malformed payload: %s", e)
                continue

            for recipient_id in payload.get("recipient_ids", []):
                try:
                    await manager.send_to_user(int(recipient_id), payload)
                except Exception as e:
                    logger.warning("subscriber: forward to %s failed: %s", recipient_id, e)
    except asyncio.CancelledError:
        logger.info("chat subscriber cancelled")
        raise
    finally:
        try:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()
        except Exception:
            pass