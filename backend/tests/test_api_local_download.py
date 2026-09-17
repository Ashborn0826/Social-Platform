"""Tests for the local storage download + upload routes.

These routes only exist when LocalBackend is active (the S3 backend
issues real S3 URLs and never hits our /api/uploads/local/* route).
"""
import time

import pytest

from app.config import settings


async def _signup_token(client, email="alice@example.com") -> str:
    r = await client.post(
        "/auth/signup",
        json={"email": email, "password": "CorrectHorse9", "display_name": "Alice"},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_get_url(storage, storage_key: str, content_type: str, expires_seconds: int = 60) -> str:
    expires = int(time.time()) + expires_seconds
    sig = storage._sign(storage_key, expires, content_type, "get")
    ct = "image%2Fjpeg" if content_type == "image/jpeg" else content_type
    return f"/api/uploads/local/{storage_key}?expires={expires}&sig={sig}&mode=get&content_type={ct}"


def _make_put_url(storage, storage_key: str, content_type: str, expires_seconds: int = 60) -> str:
    expires = int(time.time()) + expires_seconds
    sig = storage._sign(storage_key, expires, content_type, "put")
    ct = "image%2Fjpeg" if content_type == "image/jpeg" else content_type
    return f"/api/uploads/local/{storage_key}?expires={expires}&sig={sig}&mode=put&content_type={ct}"


async def test_local_get_serves_uploaded_bytes(client, storage):
    token = await _signup_token(client)
    upload = await client.post(
        "/api/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 100},
        headers=_auth(token),
    )
    data = upload.json()
    storage.put_bytes(data["storage_key"], b"jpeg bytes here", "image/jpeg")

    url = _make_get_url(storage, data["storage_key"], "image/jpeg")
    r = await client.get(url)
    assert r.status_code == 200
    assert r.content == b"jpeg bytes here"
    assert r.headers["content-type"].startswith("image/jpeg")


async def test_local_get_expired_returns_403(client, storage):
    token = await _signup_token(client)
    upload = await client.post(
        "/api/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 100},
        headers=_auth(token),
    )
    data = upload.json()
    storage.put_bytes(data["storage_key"], b"x" * 100, "image/jpeg")

    # Build an already-expired URL
    expires = int(time.time()) - 10
    sig = storage._sign(data["storage_key"], expires, "image/jpeg", "get")
    url = f"/api/uploads/local/{data['storage_key']}?expires={expires}&sig={sig}&mode=get&content_type=image%2Fjpeg"

    r = await client.get(url)
    assert r.status_code == 403


async def test_local_get_bad_signature_returns_403(client):
    url = "/api/uploads/local/anything?expires=9999999999&sig=deadbeefdeadbeef&mode=get&content_type=text%2Fplain"
    r = await client.get(url)
    assert r.status_code == 403


async def test_local_get_wrong_content_type_returns_403(client, storage):
    """Sig was made for image/jpeg but URL says content_type=text/plain."""
    token = await _signup_token(client)
    upload = await client.post(
        "/api/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 100},
        headers=_auth(token),
    )
    data = upload.json()
    storage.put_bytes(data["storage_key"], b"x" * 100, "image/jpeg")

    expires = int(time.time()) + 60
    sig = storage._sign(data["storage_key"], expires, "image/jpeg", "get")
    # Tamper the content_type in the URL
    url = f"/api/uploads/local/{data['storage_key']}?expires={expires}&sig={sig}&mode=get&content_type=text%2Fplain"

    r = await client.get(url)
    assert r.status_code == 403


async def test_local_put_uploads_bytes(client, storage):
    token = await _signup_token(client)
    upload = await client.post(
        "/api/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 100},
        headers=_auth(token),
    )
    data = upload.json()

    url = _make_put_url(storage, data["storage_key"], "image/jpeg")
    r = await client.put(url, content=b"uploaded bytes via local backend")
    assert r.status_code == 200
    assert r.json()["bytes"] == len(b"uploaded bytes via local backend")

    # Verify it landed
    assert storage.exists(data["storage_key"])
    assert storage.get_bytes(data["storage_key"]) == b"uploaded bytes via local backend"


async def test_local_put_then_get_round_trip(client, storage):
    """Full flow: presigned PUT → presigned GET serves the same bytes."""
    token = await _signup_token(client)
    upload = await client.post(
        "/api/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 1000},
        headers=_auth(token),
    )
    data = upload.json()

    # PUT via signed URL
    payload = b"this is a fake jpeg" * 10
    put_url = _make_put_url(storage, data["storage_key"], "image/jpeg")
    r = await client.put(put_url, content=payload)
    assert r.status_code == 200

    # GET via signed URL
    get_url = _make_get_url(storage, data["storage_key"], "image/jpeg")
    r = await client.get(get_url)
    assert r.status_code == 200
    assert r.content == payload