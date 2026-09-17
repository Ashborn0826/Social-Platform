"""Storage backend factory.

Picks the backend implementation from `settings.object_storage_backend`.
Tests can override this with FastAPI's `dependency_overrides[get_storage]`.
"""
from app.config import settings
from app.storage.base import ObjectStorage
from app.storage.local import LocalBackend
from app.storage.s3 import S3Backend


def get_storage() -> ObjectStorage:
    backend = settings.object_storage_backend
    if backend == "local":
        return LocalBackend(
            base_dir=settings.local_storage_dir,
            api_base_url=settings.api_host,
            secret=settings.storage_secret,
        )
    if backend == "s3":
        return S3Backend(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url or None,
        )
    raise ValueError(f"unknown OBJECT_STORAGE_BACKEND: {backend!r}")