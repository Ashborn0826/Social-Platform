"""Cross-spec: posts can include attachment_ids; validation rules from media-uploads spec."""

import pytest


async def _signup_token(client, email="alice@example.com") -> str:
    r = await client.post(
        "/auth/signup",
        json={"email": email, "password": "CorrectHorse9", "display_name": "Alice"},
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _make_ready_attachment(client, token, storage) -> int:
    """Create an attachment, upload to storage, mark complete. Returns the attachment id."""
    upload = await client.post(
        "/api/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 100},
        headers=_auth(token),
    )
    data = upload.json()
    storage.put_bytes(data["storage_key"], b"x" * 100, "image/jpeg")
    complete = await client.post(
        f"/api/uploads/{data['attachment_id']}/complete", headers=_auth(token)
    )
    assert complete.status_code == 200
    return data["attachment_id"]


async def test_create_post_with_attachment_success(client, storage):
    token = await _signup_token(client)
    aid = await _make_ready_attachment(client, token, storage)

    r = await client.post(
        "/api/posts",
        json={"text": "with image", "attachment_ids": [aid]},
        headers=_auth(token),
    )
    assert r.status_code == 201


async def test_create_post_with_multiple_attachments_success(client, storage):
    token = await _signup_token(client)
    a1 = await _make_ready_attachment(client, token, storage)
    a2 = await _make_ready_attachment(client, token, storage)

    r = await client.post(
        "/api/posts",
        json={"text": "two images", "attachment_ids": [a1, a2]},
        headers=_auth(token),
    )
    assert r.status_code == 201


async def test_create_post_with_other_users_attachment_returns_403(client, storage):
    alice_token = await _signup_token(client, "alice@example.com")
    alice_aid = await _make_ready_attachment(client, alice_token, storage)

    bob_token = await _signup_token(client, "bob@example.com")
    r = await client.post(
        "/api/posts",
        json={"text": "stolen image", "attachment_ids": [alice_aid]},
        headers=_auth(bob_token),
    )
    assert r.status_code == 403


async def test_create_post_with_pending_attachment_returns_409(client):
    """If the attachment is still in 'pending' status (no complete call yet),
    creating a post referencing it must fail."""
    token = await _signup_token(client)
    upload = await client.post(
        "/api/uploads",
        json={"content_type": "image/jpeg", "size_bytes": 100},
        headers=_auth(token),
    )
    aid = upload.json()["attachment_id"]
    # Don't call /complete

    r = await client.post(
        "/api/posts",
        json={"text": "with pending", "attachment_ids": [aid]},
        headers=_auth(token),
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "attachment_not_ready"


async def test_create_post_with_unknown_attachment_returns_403(client):
    """Don't leak whether an attachment id exists or not."""
    token = await _signup_token(client)
    r = await client.post(
        "/api/posts",
        json={"text": "with ghost", "attachment_ids": [99999]},
        headers=_auth(token),
    )
    assert r.status_code == 403


async def test_create_post_dedupes_attachment_ids(client, storage):
    """If the same attachment_id appears twice, we link it once."""
    token = await _signup_token(client)
    aid = await _make_ready_attachment(client, token, storage)

    r = await client.post(
        "/api/posts",
        json={"text": "double link", "attachment_ids": [aid, aid]},
        headers=_auth(token),
    )
    assert r.status_code == 201
    # Verify only one post_attachments row exists
    from sqlalchemy import select, func
    from app.db.models import PostAttachment

    me = await client.post(
        "/auth/login",
        json={"email": "alice@example.com", "password": "CorrectHorse9"},
    )
    user_id = me.json()["user"]["id"]

    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(PostAttachment)
            .where(PostAttachment.attachment_id == aid)
        )
    assert count == 1