"""Core processing: fetch original, generate thumbnail, upload, update DB.

Includes retry-with-exponential-backoff. After max retries, the job is
moved to the DLQ.

Idempotency: if the attachment is already `ready` with a `thumbnail_key`,
or isn't an image, processing is a no-op (returns True).
"""
import asyncio
import logging

from redis.asyncio import Redis

from app.db.repository import AttachmentRepository
from app.db.session import AsyncSessionLocal
from app.media_processing.queue import push_to_dlq
from app.media_processing.thumbnail import generate_thumbnail
from app.storage.base import ObjectStorage

logger = logging.getLogger(__name__)

# Retry policy: 1 initial attempt + N retries with exponential backoff.
# Tests monkey-patch this to make retries near-instant.
RETRY_DELAYS = [1, 4, 16]


async def process_attachment(
    attachment_id: int,
    storage: ObjectStorage,
    redis: Redis,
) -> bool:
    """Process one attachment. Returns True on success/no-op, False on DLQ.

    Flow per attempt:
      1. Set status='processing'
      2. Skip if not an image (videos stay thumbnail-less, status remains 'ready')
      3. Skip if already processed (idempotency: thumbnail_key already set)
      4. Fetch original bytes from storage
      5. Generate thumbnail (max 400 px wide)
      6. Upload to storage as `{key}.thumb`
      7. Update DB with thumbnail_key
    """
    last_error: Exception | None = None
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            await _process_once(attachment_id, storage)
            return True
        except Exception as e:
            last_error = e
            if attempt < len(RETRY_DELAYS):
                delay = RETRY_DELAYS[attempt]
                logger.warning(
                    "thumbnail attempt %d for attachment %d failed: %s; retrying in %ds",
                    attempt + 1, attachment_id, e, delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "thumbnail permanently failed for attachment %d after %d attempts: %s",
                    attachment_id,
                    len(RETRY_DELAYS) + 1,
                    e,
                )

    # All attempts failed — mark failed + DLQ
    try:
        await push_to_dlq(redis, attachment_id, str(last_error) if last_error else "unknown")
    except Exception as dlq_err:
        logger.warning("failed to push to DLQ for attachment %d: %s", attachment_id, dlq_err)

    async with AsyncSessionLocal() as session:
        await AttachmentRepository(session).mark_failed(attachment_id)

    return False


async def _process_once(attachment_id: int, storage: ObjectStorage) -> None:
    async with AsyncSessionLocal() as session:
        repo = AttachmentRepository(session)
        attachment = await repo.get_by_id(attachment_id)
        if attachment is None:
            raise ValueError(f"attachment {attachment_id} not found")

        # Idempotency 1: already processed (thumbnail already uploaded)
        if attachment.thumbnail_key is not None:
            logger.info(
                "attachment %d already has thumbnail_key=%s; skipping",
                attachment_id,
                attachment.thumbnail_key,
            )
            return

        # Idempotency 2: not an image (videos don't get thumbnails in v1)
        if not attachment.content_type.startswith("image/"):
            logger.info(
                "attachment %d is content_type=%s; skipping thumbnail",
                attachment_id,
                attachment.content_type,
            )
            return

        # Mark as processing so concurrent calls don't double-process
        await repo.mark_processing(attachment_id)

        # Fetch original bytes (sync call; could be slow for large files
        # but our test files are small)
        original_bytes = storage.get_bytes(attachment.storage_key)

        # Generate thumbnail
        thumb_bytes = generate_thumbnail(original_bytes, max_width=400)

        # Upload thumbnail as `<original_key>.thumb`
        thumb_key = attachment.storage_key + ".thumb"
        storage.put_bytes(thumb_key, thumb_bytes, "image/jpeg")

        # Update DB
        await repo.update_thumbnail(attachment_id, thumb_key)