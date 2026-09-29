"""Core thumbnail-processing tests (mocking storage via LocalBackend)."""
import io

import pytest
from PIL import Image

from app.db.repository import (
    AlreadyFollowingError,  # noqa: F401 (kept for compat w/ potential refactor)
    AttachmentRepository,
    UserRepository,
)
from app.media_processing import process as process_module
from app.media_processing.process import process_attachment


_DUMMY_HASH = "$2b$12$abcdefghijklmnopqrstuuW4MCKbvDxFC5mDb5n3qV7G"


def _make_jpeg_bytes(width: int = 800, height: int = 600) -> bytes:
    img = Image.new("RGB", (width, height), (100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


async def _make_user_with_attachment(
    session, storage, content_type: str = "image/jpeg", suffix: str = ".jpg"
):
    user = await UserRepository(session).create(
        email=f"{content_type.replace('/', '_')}@x.com",
        password_hash=_DUMMY_HASH,
        display_name="U",
    )
    await session.commit()

    storage_key = f"attachments/{user.id}/test{suffix}"
    storage.put_bytes(storage_key, _make_jpeg_bytes(), content_type)

    repo = AttachmentRepository(session)
    att = await repo.create(
        owner_id=user.id,
        content_type=content_type,
        size_bytes=100,
        storage_key=storage_key,
    )
    await session.commit()
    return user, att


async def test_process_image_attachment_generates_thumbnail(
    session, fresh_session, redis_client, storage, monkeypatch
):
    # Make retries instant so the test is fast
    monkeypatch.setattr(process_module, "RETRY_DELAYS", [0, 0, 0])

    user, att = await _make_user_with_attachment(session, storage)

    success = await process_attachment(att.id, storage, redis_client)
    assert success is True

    # Thumbnail was uploaded under <key>.thumb
    thumb_key = f"attachments/{user.id}/test.jpg.thumb"
    assert storage.exists(thumb_key)

    # DB was updated with thumbnail_key. Use fresh_session because the test's
    # session has the attachment cached with stale fields.
    updated = await AttachmentRepository(fresh_session).get_by_id(att.id)
    assert updated.thumbnail_key == thumb_key
    assert updated.status == "ready"


async def test_process_video_attachment_skips_gracefully(
    session, fresh_session, redis_client, storage, monkeypatch
):
    monkeypatch.setattr(process_module, "RETRY_DELAYS", [0, 0, 0])

    user, att = await _make_user_with_attachment(
        session, storage, content_type="video/mp4", suffix=".mp4"
    )

    success = await process_attachment(att.id, storage, redis_client)
    # Success=True because we skip cleanly (not a failure)
    assert success is True

    updated = await AttachmentRepository(fresh_session).get_by_id(att.id)
    assert updated.thumbnail_key is None
    # Status stays as whatever it was before — videos don't transition to ready
    # via the worker (a real /complete would have done that already).
    assert updated.status == "pending"


async def test_process_attachment_idempotent_when_thumbnail_exists(
    session, fresh_session, redis_client, storage, monkeypatch
):
    """If thumbnail_key is already set, processing is a no-op."""
    monkeypatch.setattr(process_module, "RETRY_DELAYS", [0, 0, 0])

    user, att = await _make_user_with_attachment(session, storage)

    # First call processes
    success1 = await process_attachment(att.id, storage, redis_client)
    assert success1 is True

    # Capture the original thumb key + storage state
    original_thumb_key = (
        await AttachmentRepository(fresh_session).get_by_id(att.id)
    ).thumbnail_key
    assert original_thumb_key is not None

    # Delete the thumbnail file from storage to prove it's not regenerated
    storage.delete(original_thumb_key)

    # Second call — should skip (idempotency check)
    success2 = await process_attachment(att.id, storage, redis_client)
    assert success2 is True

    # Thumbnail file is still missing (not regenerated)
    assert not storage.exists(original_thumb_key)

    # DB still has the same thumbnail_key (idempotent)
    again = await AttachmentRepository(fresh_session).get_by_id(att.id)
    assert again.thumbnail_key == original_thumb_key


async def test_process_attachment_nonexistent_returns_false(
    db_setup, redis_client, storage, monkeypatch
):
    """No such attachment — process returns False (failure) after retries."""
    monkeypatch.setattr(process_module, "RETRY_DELAYS", [0, 0, 0])

    success = await process_attachment(99999, storage, redis_client)
    assert success is False


async def test_process_attachment_retries_then_dlqs_on_persistent_failure(
    session, fresh_session, redis_client, storage, monkeypatch
):
    """If storage.get_bytes always raises, after N retries the job goes to DLQ."""
    monkeypatch.setattr(process_module, "RETRY_DELAYS", [0, 0, 0])

    user, att = await _make_user_with_attachment(session, storage)

    # Force storage.get_bytes to always raise
    def boom(key):
        raise RuntimeError("simulated storage outage")

    monkeypatch.setattr(storage, "get_bytes", boom)

    success = await process_attachment(att.id, storage, redis_client)
    assert success is False  # failed permanently

    # DLQ should have the failed job
    from app.media_processing.queue import MEDIA_DLQ_KEY

    dlq_size = await redis_client.llen(MEDIA_DLQ_KEY)
    assert dlq_size == 1

    # Attachment status should be 'failed'
    updated = await AttachmentRepository(fresh_session).get_by_id(att.id)
    assert updated.status == "failed"


async def test_process_attachment_succeeds_after_transient_failure(
    session, redis_client, storage, monkeypatch
):
    """If first attempt fails but second succeeds, the overall result is success."""
    monkeypatch.setattr(process_module, "RETRY_DELAYS", [0, 0, 0])

    user, att = await _make_user_with_attachment(session, storage)

    real_get_bytes = storage.get_bytes
    call_count = {"n": 0}

    def flaky_get_bytes(key):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("transient")
        return real_get_bytes(key)

    monkeypatch.setattr(storage, "get_bytes", flaky_get_bytes)

    success = await process_attachment(att.id, storage, redis_client)
    assert success is True
    # First attempt failed, second succeeded → 2 calls
    assert call_count["n"] >= 2


async def test_process_attachment_uses_storage_key_dot_thumb_suffix(
    session, fresh_session, redis_client, storage, monkeypatch
):
    """The thumbnail storage key is `<original_key>.thumb`."""
    monkeypatch.setattr(process_module, "RETRY_DELAYS", [0, 0, 0])

    user, att = await _make_user_with_attachment(
        session, storage, suffix=".custom.jpg"
    )

    await process_attachment(att.id, storage, redis_client)

    expected_thumb_key = f"attachments/{user.id}/test.custom.jpg.thumb"
    assert storage.exists(expected_thumb_key)

    updated = await AttachmentRepository(fresh_session).get_by_id(att.id)
    assert updated.thumbnail_key == expected_thumb_key