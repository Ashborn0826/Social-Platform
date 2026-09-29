"""Process-local registry of WebSocket connections.

Each uvicorn worker process has its own ConnectionManager. When a user has
multiple browser tabs open, all tabs connect to one or more workers; each
worker tracks only its own connections. Cross-worker delivery is handled
by Redis pub/sub (see subscriber.py).

The manager is process-local (module-level singleton) because WebSocket
connections in FastAPI don't have a clean dependency-injection path for
per-process state — we can't easily inject a per-request singleton.
"""
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks WebSocket connections per user_id.

    A user may have multiple connections (e.g., multiple browser tabs, or
    one tab connected to two different workers via load balancing).
    """

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}

    async def connect(self, ws: WebSocket, user_id: int) -> None:
        await ws.accept()
        self._connections.setdefault(user_id, set()).add(ws)

    def disconnect(self, ws: WebSocket, user_id: int) -> None:
        conns = self._connections.get(user_id)
        if conns is None:
            return
        conns.discard(ws)
        if not conns:
            del self._connections[user_id]

    async def send_to_user(self, user_id: int, payload: dict[str, Any]) -> None:
        """Best-effort send to all of user's local connections.

        Stale connections (closed between dispatch and send) are swallowed;
        they'll be cleaned up on the next disconnect call.
        """
        conns = list(self._connections.get(user_id, ()))
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception as e:
                logger.debug("send_to_user: stale connection (%s): %s", user_id, e)

    def user_count(self, user_id: int) -> int:
        return len(self._connections.get(user_id, ()))

    def total_connections(self) -> int:
        return sum(len(c) for c in self._connections.values())


# Process-local singleton. WebSocket routes access via `from app.realtime.connection_manager import manager`.
manager = ConnectionManager()