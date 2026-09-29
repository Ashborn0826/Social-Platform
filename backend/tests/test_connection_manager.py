import pytest

from app.realtime.connection_manager import ConnectionManager


class MockWebSocket:
    def __init__(self):
        self.sent = []
        self.accepted = False
        self.closed = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self, code=None, reason=None):
        self.closed = True


async def test_connect_registers_single_connection():
    m = ConnectionManager()
    ws = MockWebSocket()
    await m.connect(ws, user_id=1)
    assert ws.accepted is True
    assert m.user_count(1) == 1


async def test_connect_registers_multiple_connections_same_user():
    m = ConnectionManager()
    ws1, ws2, ws3 = MockWebSocket(), MockWebSocket(), MockWebSocket()
    await m.connect(ws1, user_id=1)
    await m.connect(ws2, user_id=1)
    await m.connect(ws3, user_id=1)
    assert m.user_count(1) == 3


async def test_connect_different_users_tracked_separately():
    m = ConnectionManager()
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    await m.connect(ws1, user_id=1)
    await m.connect(ws2, user_id=2)
    assert m.user_count(1) == 1
    assert m.user_count(2) == 1
    assert m.total_connections() == 2


async def test_send_to_user_broadcasts_to_all_connections():
    m = ConnectionManager()
    ws1, ws2 = MockWebSocket(), MockWebSocket()
    await m.connect(ws1, user_id=1)
    await m.connect(ws2, user_id=1)
    await m.send_to_user(1, {"msg": "hello"})
    assert ws1.sent == [{"msg": "hello"}]
    assert ws2.sent == [{"msg": "hello"}]


async def test_send_to_user_with_no_connections_is_noop():
    m = ConnectionManager()
    # Should not raise
    await m.send_to_user(999, {"msg": "nobody listening"})


async def test_send_to_user_does_not_reach_other_users():
    m = ConnectionManager()
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    await m.connect(ws1, user_id=1)
    await m.connect(ws2, user_id=2)
    await m.send_to_user(1, {"msg": "for 1 only"})
    assert ws1.sent == [{"msg": "for 1 only"}]
    assert ws2.sent == []


async def test_disconnect_removes_connection():
    m = ConnectionManager()
    ws = MockWebSocket()
    await m.connect(ws, user_id=1)
    m.disconnect(ws, user_id=1)
    assert m.user_count(1) == 0


async def test_disconnect_one_of_many_leaves_others():
    m = ConnectionManager()
    ws1, ws2 = MockWebSocket(), MockWebSocket()
    await m.connect(ws1, user_id=1)
    await m.connect(ws2, user_id=1)
    m.disconnect(ws1, user_id=1)
    assert m.user_count(1) == 1
    assert m._connections[1] == {ws2}


async def test_disconnect_unknown_connection_is_noop():
    m = ConnectionManager()
    ws = MockWebSocket()
    # Never connected — disconnect is a no-op (no exception)
    m.disconnect(ws, user_id=1)


async def test_send_swallows_exceptions_from_stale_connections():
    m = ConnectionManager()

    class BrokenWebSocket:
        async def accept(self):
            pass

        async def send_json(self, data):
            raise RuntimeError("connection already closed")

    ws_broken = BrokenWebSocket()
    ws_good = MockWebSocket()

    await m.connect(ws_broken, user_id=1)  # type: ignore[arg-type]
    await m.connect(ws_good, user_id=1)

    # The broken socket's send raises; we swallow; the good one still gets it.
    await m.send_to_user(1, {"msg": "hi"})
    assert ws_good.sent == [{"msg": "hi"}]
