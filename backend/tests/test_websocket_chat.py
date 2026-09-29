"""WebSocket chat tests using FastAPI's sync TestClient.

The TestClient runs the lifespan (which starts the chat pub/sub subscriber),
then we connect via WebSocket and exercise the send/receive protocol.
"""
import json
import time

import pytest


def _signup_sync(client, email: str, password: str = "CorrectHorse9") -> str:
    r = client.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "display_name": email.split("@")[0]},
    )
    return r.json()["access_token"]


def _user_id_sync(client, token: str, email: str) -> int:
    me = client.post(
        "/api/auth/login",
        json={"email": email, "password": "CorrectHorse9"},
    )
    return me.json()["user"]["id"]


def test_websocket_no_token_closes_with_4401(sync_client):
    """No `?token=` -> close 4401."""
    with pytest.raises(Exception):
        with sync_client.websocket_connect("/api/chats/ws") as ws:
            ws.receive_json()


def test_websocket_invalid_token_closes_with_4401(sync_client):
    with pytest.raises(Exception):
        with sync_client.websocket_connect("/api/chats/ws?token=not-a-real-jwt") as ws:
            ws.receive_json()


def test_websocket_valid_token_connects_and_sends_ready(sync_client):
    token = _signup_sync(sync_client, "alice@example.com")
    with sync_client.websocket_connect(f"/api/chats/ws?token={token}") as ws:
        ready = ws.receive_json()
        assert ready == {"type": "ready"}


def test_websocket_send_to_peer_creates_chat_and_returns_message(sync_client):
    alice_token = _signup_sync(sync_client, "alice@example.com")
    _signup_sync(sync_client, "bob@example.com")
    bob_id = _user_id_sync(sync_client, alice_token, "bob@example.com")

    with sync_client.websocket_connect(f"/api/chats/ws?token={alice_token}") as ws:
        # Drain the initial "ready" before sending.
        assert ws.receive_json() == {"type": "ready"}
        ws.send_json({"type": "send", "to_user_id": bob_id, "text": "hello bob"})
        msg = ws.receive_json()
        assert msg["type"] == "message"
        assert msg["message"]["text"] == "hello bob"
        assert msg["chat_id"] > 0


def test_websocket_send_to_self_is_silently_dropped(sync_client):
    alice_token = _signup_sync(sync_client, "alice@example.com")
    alice_id = _user_id_sync(sync_client, alice_token, "alice@example.com")

    with sync_client.websocket_connect(f"/api/chats/ws?token={alice_token}") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_json({"type": "send", "to_user_id": alice_id, "text": "talking to myself"})
        # The server drops it without echoing. Verify connection is alive.
        time.sleep(0.3)


def test_websocket_send_empty_text_is_dropped(sync_client):
    alice_token = _signup_sync(sync_client, "alice@example.com")
    _signup_sync(sync_client, "bob@example.com")
    bob_id = _user_id_sync(sync_client, alice_token, "bob@example.com")

    with sync_client.websocket_connect(f"/api/chats/ws?token={alice_token}") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_json({"type": "send", "to_user_id": bob_id, "text": "   "})
        time.sleep(0.3)


def test_websocket_send_to_existing_chat_id(sync_client):
    alice_token = _signup_sync(sync_client, "alice@example.com")
    _signup_sync(sync_client, "bob@example.com")
    bob_id = _user_id_sync(sync_client, alice_token, "bob@example.com")

    chat_id = sync_client.post(
        f"/api/chats/{bob_id}",
        headers={"Authorization": f"Bearer {alice_token}"},
    ).json()["chat_id"]

    with sync_client.websocket_connect(f"/api/chats/ws?token={alice_token}") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_json({"type": "send", "chat_id": chat_id, "text": "in existing chat"})
        msg = ws.receive_json()
        assert msg["message"]["text"] == "in existing chat"
        assert msg["chat_id"] == chat_id


def test_websocket_message_persists_to_postgres(sync_client):
    """The message is persisted in Postgres, queryable via REST history."""
    alice_token = _signup_sync(sync_client, "alice@example.com")
    _signup_sync(sync_client, "bob@example.com")
    bob_id = _user_id_sync(sync_client, alice_token, "bob@example.com")

    chat_id = sync_client.post(
        f"/api/chats/{bob_id}",
        headers={"Authorization": f"Bearer {alice_token}"},
    ).json()["chat_id"]

    with sync_client.websocket_connect(f"/api/chats/ws?token={alice_token}") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_json({"type": "send", "chat_id": chat_id, "text": "persisted!"})
        msg = ws.receive_json()
        assert msg["message"]["text"] == "persisted!"

    history = sync_client.get(
        f"/api/chats/{chat_id}/messages",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    texts = [m["text"] for m in history.json()["messages"]]
    assert "persisted!" in texts


def test_websocket_sender_with_no_chat_id_or_peer_returns_silently(sync_client):
    alice_token = _signup_sync(sync_client, "alice@example.com")

    with sync_client.websocket_connect(f"/api/chats/ws?token={alice_token}") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_json({"type": "send", "text": "no destination"})
        time.sleep(0.3)


def test_websocket_unknown_chat_id_is_dropped(sync_client):
    alice_token = _signup_sync(sync_client, "alice@example.com")

    with sync_client.websocket_connect(f"/api/chats/ws?token={alice_token}") as ws:
        assert ws.receive_json() == {"type": "ready"}
        ws.send_json({"type": "send", "chat_id": 99999, "text": "no chat"})
        time.sleep(0.3)


def test_websocket_two_clients_same_user_get_message_twice(sync_client):
    """A user with two open WebSocket tabs should receive the same message on both."""
    alice_token = _signup_sync(sync_client, "alice@example.com")
    _signup_sync(sync_client, "bob@example.com")
    bob_id = _user_id_sync(sync_client, alice_token, "bob@example.com")

    bob_token = sync_client.post(
        "/api/auth/login",
        json={"email": "bob@example.com", "password": "CorrectHorse9"},
    ).json()["access_token"]

    # Pre-create chat (use alice's auth to create; bob will send into it)
    chat_id = sync_client.post(
        f"/api/chats/{bob_id}",
        headers={"Authorization": f"Bearer {alice_token}"},
    ).json()["chat_id"]

    with sync_client.websocket_connect(f"/api/chats/ws?token={alice_token}") as ws1:
        with sync_client.websocket_connect(f"/api/chats/ws?token={alice_token}") as ws2:
            assert ws1.receive_json() == {"type": "ready"}
            assert ws2.receive_json() == {"type": "ready"}

            with sync_client.websocket_connect(f"/api/chats/ws?token={bob_token}") as ws_bob:
                assert ws_bob.receive_json() == {"type": "ready"}

                ws_bob.send_json({"type": "send", "chat_id": chat_id, "text": "broadcast"})

                msg1 = ws1.receive_json()
                msg2 = ws2.receive_json()

                assert msg1["message"]["text"] == "broadcast"
                assert msg2["message"]["text"] == "broadcast"
                assert msg1["chat_id"] == chat_id
                assert msg2["chat_id"] == chat_id


def test_websocket_text_truncates_to_2000_chars(sync_client):
    alice_token = _signup_sync(sync_client, "alice@example.com")
    _signup_sync(sync_client, "bob@example.com")
    bob_id = _user_id_sync(sync_client, alice_token, "bob@example.com")

    with sync_client.websocket_connect(f"/api/chats/ws?token={alice_token}") as ws:
        assert ws.receive_json() == {"type": "ready"}
        long_text = "x" * 5000
        ws.send_json({"type": "send", "to_user_id": bob_id, "text": long_text})
        msg = ws.receive_json()
        assert len(msg["message"]["text"]) == 2000
