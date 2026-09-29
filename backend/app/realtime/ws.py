"""WebSocket endpoint for real-time chat.

Protocol (JSON over WebSocket):

Client -> Server:
  {"type": "send", "to_user_id": <int>, "text": "<str>"}     -- lazy-create chat with peer
  {"type": "send", "chat_id": <int>, "text": "<str>"}       -- send in existing chat
  {"type": "ping"}                                         -- keepalive

Server -> Client:
  {"type": "ready"}                                        -- on connect (after auth)
  {"type": "message", "chat_id": <int>, "message": {...}}  -- broadcast
  {"type": "pong"}                                         -- pong reply

Close codes:
  4401 (unauthorized) — missing or invalid JWT in query string
"""
import asyncio
import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import InvalidTokenError, decode_token
from app.db.repository import ChatRepository
from app.db.session import AsyncSessionLocal
from app.realtime.connection_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/api/chats/ws")
async def chat_websocket(
    websocket: WebSocket,
    token: str | None = Query(None),
):
    # 1. Authenticate
    if not token:
        await websocket.close(code=4401, reason="missing_token")
        return
    try:
        payload = decode_token(token, expected_type="access")
    except InvalidTokenError:
        await websocket.close(code=4401, reason="invalid_token")
        return
    user_id = int(payload["sub"])

    redis: Redis = websocket.app.state.redis

    # 2. Register connection
    await manager.connect(websocket, user_id)
    await websocket.send_json({"type": "ready"})
    logger.info("WS connected: user=%s total_connections=%d", user_id, manager.total_connections())

    # 3. Main loop
    try:
        while True:
            data = await websocket.receive_json()
            await _handle_message(data, user_id, redis)
    except WebSocketDisconnect:
        logger.info("WS disconnected: user=%s", user_id)
    finally:
        manager.disconnect(websocket, user_id)


async def _handle_message(data: dict, sender_id: int, redis: Redis) -> None:
    """Process one incoming message from the WebSocket."""
    msg_type = data.get("type")
    if msg_type != "send":
        # Unknown types ignored (could pong here in future)
        return

    text = (data.get("text") or "").strip()
    if not text:
        return
    text = text[:2000]  # truncate to a sane limit

    async with AsyncSessionLocal() as session:
        repo = ChatRepository(session)
        try:
            chat_id = await _resolve_chat_id(data, sender_id, repo)
        except _ChatError:
            return

        if chat_id is None:
            return

        message = await repo.create_message(chat_id, sender_id, text)
        recipient_ids = await repo.get_participant_ids(chat_id)

    # Publish to Redis; subscribers forward to local connections.
    payload = {
        "type": "message",
        "chat_id": chat_id,
        "message": {
            "id": message.id,
            "sender_id": sender_id,
            "text": text,
            "created_at": message.created_at.isoformat(),
        },
        "recipient_ids": [int(rid) for rid in recipient_ids],
    }
    await redis.publish("chat:events", json.dumps(payload))


class _ChatError(Exception):
    pass


async def _resolve_chat_id(data: dict, sender_id: int, repo: ChatRepository) -> int | None:
    """Either reuse chat_id or lazily create a chat with to_user_id."""
    if "chat_id" in data:
        try:
            chat_id = int(data["chat_id"])
        except (TypeError, ValueError):
            return None
        if not await repo.is_participant(chat_id, sender_id):
            # Don't echo errors — would leak existence
            return None
        return chat_id

    if "to_user_id" in data:
        try:
            peer_id = int(data["to_user_id"])
        except (TypeError, ValueError):
            return None
        if peer_id == sender_id:
            return None
        try:
            chat = await repo.get_or_create_chat(sender_id, peer_id)
            return chat.id
        except ValueError:
            return None

    return None