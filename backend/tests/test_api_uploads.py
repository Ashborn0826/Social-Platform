import pytest


async def _signup_token(client, email="alice@example.com") -> str:
    r = await client.post(
        "/auth/signup",
        json={"email": email, "password": "CorrectHorse9", "display_name": "Alice"},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_request_upload_success(client):
    token = await _signup_token(client)
    r = await client.post(
        "/api/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 1024},
        headers=_auth(token),
    )
    assert r.status_code == 201
    data = r.json()
    assert "upload_url" in data
    assert data["storage_key"].startswith("attachments/")
    assert data["storage_key"].endswith(".jpeg")
    assert "expires_at" in data


async def test_request_upload_requires_auth(client):
    r = await client.post(
        "/api/uploads", json={"content_type": "image/jpeg", "size_bytes": 1024}
    )
    assert r.status_code == 401


async def test_request_upload_accepts_video(client):
    token = await _signup_token(client)
    r = await client.post(
        "/api/uploads",
        json={"content_type": "video/mp4", "size_bytes": 1024},
        headers=_auth(token),
    )
    assert r.status_code == 201
    assert r.json()["storage_key"].endswith(".mp4")


async def test_request_upload_rejects_non_media_content_type(client):
    token = await _signup_token(client)
    r = await client.post(
        "/api/uploads",
        json={"content_type": "application/x-msdownload", "size_bytes": 1024},
        headers=_auth(token),
    )
    assert r.status_code == 422


async def test_request_upload_rejects_too_large(client):
    token = await _signup_token(client)
    r = await client.post(
        "/api/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 60_000_000},
        headers=_auth(token),
    )
    assert r.status_code == 422


async def test_request_upload_rejects_zero_size(client):
    token = await _signup_token(client)
    r = await client.post(
        "/api/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 0},
        headers=_auth(token),
    )
    assert r.status_code == 422


async def test_complete_upload_success(client, storage):
    token = await _signup_token(client)
    upload = await client.post(
        "/api/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 100},
        headers=_auth(token),
    )
    data = upload.json()

    # Simulate the client uploading bytes to storage
    storage.put_bytes(data["storage_key"], b"x" * 100, "image/jpeg")

    complete = await client.post(
        f"/api/uploads/{data['attachment_id']}/complete",
        headers=_auth(token),
    )
    assert complete.status_code == 200
    body = complete.json()
    assert body["status"] == "ready"
    assert body["attachment_id"] == data["attachment_id"]


async def test_complete_upload_object_not_found_returns_409(client):
    token = await _signup_token(client)
    upload = await client.post(
        "/api/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 100},
        headers=_auth(token),
    )
    data = upload.json()
    # No put_bytes — storage is empty

    complete = await client.post(
        f"/api/uploads/{data['attachment_id']}/complete",
        headers=_auth(token),
    )
    assert complete.status_code == 409
    assert complete.json()["detail"] == "object_not_found"


async def test_complete_upload_other_users_attachment_returns_404(client, storage):
    alice_token = await _signup_token(client, "alice@example.com")
    upload = await client.post(
        "/api/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 100},
        headers=_auth(alice_token),
    )
    data = upload.json()
    storage.put_bytes(data["storage_key"], b"x" * 100, "image/jpeg")

    bob_token = await _signup_token(client, "bob@example.com")
    r = await client.post(
        f"/api/uploads/{data['attachment_id']}/complete",
        headers=_auth(bob_token),
    )
    assert r.status_code == 404


async def test_get_attachment_owner(client):
    token = await _signup_token(client)
    upload = await client.post(
        "/api/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 100},
        headers=_auth(token),
    )
    data = upload.json()
    r = await client.get(
        f"/api/uploads/{data['attachment_id']}",
        headers=_auth(token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["storage_key"] == data["storage_key"]
    assert body["status"] == "pending"


async def test_get_attachment_other_users_returns_404(client):
    alice_token = await _signup_token(client, "alice@example.com")
    upload = await client.post(
        "/api/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 100},
        headers=_auth(alice_token),
    )
    aid = upload.json()["attachment_id"]

    bob_token = await _signup_token(client, "bob@example.com")
    r = await client.get(f"/api/uploads/{aid}", headers=_auth(bob_token))
    assert r.status_code == 404


async def test_get_attachment_unknown_returns_404(client):
    token = await _signup_token(client)
    r = await client.get("/api/uploads/99999", headers=_auth(token))
    assert r.status_code == 404