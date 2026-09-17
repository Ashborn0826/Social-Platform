"""Upload endpoints: presigned URL issuance, completion, retrieval, local download.

Flow:
1. Client POSTs /api/uploads with content_type + size_bytes
2. Server validates, inserts Attachment (status='pending'), returns a
   presigned PUT URL (LocalBackend signs a URL to our own route; S3Backend
   signs an actual S3 URL via boto3)
3. Client PUTs the file bytes directly to that URL (the API server is NOT
   in the path — bytes flow client ↔ storage)
4. Client POSTs /api/uploads/{id}/complete
5. Server verifies object exists in storage, flips status to 'ready'

GET /api/uploads/{id} returns attachment metadata (owner-scoped; 404 for non-owners).
GET /api/uploads/local/{key} is the route that LocalBackend signs against;
PUT /api/uploads/local/{key} is the corresponding upload route. Both only work
when the active backend is LocalBackend.
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.db.models import User
from app.db.repository import AttachmentRepository, PostAttachmentRepository
from app.db.session import get_session
from app.schemas import (
    AttachmentResponse,
    CompleteUploadResponse,
    PresignedUploadRequest,
    PresignedUploadResponse,
)
from app.storage.base import ObjectStorage
from app.storage.factory import get_storage
from app.storage.local import LocalBackend

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

# Local download/upload routes share the same /api/uploads prefix as the
# main router so presigned URLs (built with the api_host setting) resolve
# to the right route. The local routes are registered BEFORE /{attachment_id}
# in the main router so /api/uploads/local/foo doesn't get matched as
# attachment_id="local".
local_router = APIRouter(prefix="/api/uploads/local", tags=["uploads-local"])


def _attachment_response(att) -> AttachmentResponse:
    return AttachmentResponse(
        id=att.id,
        owner_id=att.owner_id,
        content_type=att.content_type,
        size_bytes=att.size_bytes,
        storage_key=att.storage_key,
        thumbnail_key=att.thumbnail_key,
        status=att.status,
        created_at=att.created_at,
        completed_at=att.completed_at,
    )


@router.post("", response_model=PresignedUploadResponse, status_code=status.HTTP_201_CREATED)
async def request_upload(
    payload: PresignedUploadRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
    storage: ObjectStorage = Depends(get_storage),
) -> PresignedUploadResponse:
    ext = payload.content_type.split("/", 1)[1]
    storage_key = f"attachments/{user.id}/{uuid.uuid4().hex}.{ext}"

    att = await AttachmentRepository(session).create(
        owner_id=user.id,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        storage_key=storage_key,
    )

    expires_seconds = 900  # 15 minutes
    upload_url = storage.presigned_put_url(
        storage_key, payload.content_type, expires_seconds
    )
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_seconds)

    return PresignedUploadResponse(
        upload_url=upload_url,
        attachment_id=att.id,
        storage_key=storage_key,
        expires_at=expires_at,
    )


@router.post(
    "/{attachment_id}/complete",
    response_model=CompleteUploadResponse,
)
async def complete_upload(
    attachment_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
    storage: ObjectStorage = Depends(get_storage),
) -> CompleteUploadResponse:
    att = await AttachmentRepository(session).get_by_id(attachment_id)
    # Don't leak existence: 404 for both "doesn't exist" and "exists but not yours"
    if att is None or att.owner_id != user.id:
        raise HTTPException(status_code=404, detail="not_found") from None

    # Verify the object actually arrived in storage
    if not storage.exists(att.storage_key):
        raise HTTPException(status_code=409, detail="object_not_found") from None

    size = storage.size(att.storage_key)
    if size <= 0:
        raise HTTPException(status_code=409, detail="object_empty") from None

    await AttachmentRepository(session).mark_ready(attachment_id)
    return CompleteUploadResponse(attachment_id=attachment_id, status="ready")


@router.get("/{attachment_id}", response_model=AttachmentResponse)
async def get_attachment(
    attachment_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> AttachmentResponse:
    att = await AttachmentRepository(session).get_by_id(attachment_id)
    if att is None or att.owner_id != user.id:
        # Same as complete: 404 for non-owners, no existence leak
        raise HTTPException(status_code=404, detail="not_found") from None
    return _attachment_response(att)


# --- Local-only routes (signed URLs route here) ---

def _verify_or_403(local: LocalBackend, key: str, expires: int, content_type: str, mode: str, sig: str) -> None:
    try:
        local.verify_signature(key=key, expires=expires, content_type=content_type, mode=mode, sig=sig)
    except ValueError:
        raise HTTPException(status_code=403, detail="invalid_signature") from None


@local_router.get("/{key_path:path}")
async def download_local(
    key_path: str,
    expires: int = Query(...),
    sig: str = Query(...),
    content_type: str = Query(...),
    mode: str = Query("get"),
    storage: ObjectStorage = Depends(get_storage),
) -> Response:
    if not isinstance(storage, LocalBackend):
        raise HTTPException(status_code=404, detail="not_found") from None
    _verify_or_403(storage, key_path, expires, content_type, mode, sig)
    if not storage.exists(key_path):
        raise HTTPException(status_code=404, detail="not_found") from None
    data = storage.get_bytes(key_path)
    return Response(content=data, media_type=content_type)


@local_router.put("/{key_path:path}")
async def upload_local(
    key_path: str,
    request: Request,
    expires: int = Query(...),
    sig: str = Query(...),
    content_type: str = Query(...),
    mode: str = Query("put"),
    storage: ObjectStorage = Depends(get_storage),
) -> dict:
    if not isinstance(storage, LocalBackend):
        raise HTTPException(status_code=404, detail="not_found") from None
    _verify_or_403(storage, key_path, expires, content_type, mode, sig)
    data = await request.body()
    storage.put_bytes(key_path, data, content_type)
    return {"ok": True, "bytes": len(data)}