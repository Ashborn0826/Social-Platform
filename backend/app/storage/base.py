from typing import Protocol


class ObjectStorage(Protocol):
    """Abstract object storage interface.

    Two implementations: LocalBackend (filesystem, dev/tests) and S3Backend
    (boto3, production / MinIO). Apps depend only on this Protocol — swapping
    backends is a single env-var change (`OBJECT_STORAGE_BACKEND=local|s3`).

    Keys are opaque strings like "attachments/42/abc123.jpg". They are passed
    through unmodified to the underlying storage.
    """

    def presigned_put_url(
        self, key: str, content_type: str, expires_seconds: int = 900
    ) -> str:
        """Return a URL the client can PUT file content to within `expires_seconds`."""
        ...

    def presigned_get_url(
        self, key: str, content_type: str, expires_seconds: int = 900
    ) -> str:
        """Return a URL the client can GET the file from within `expires_seconds`."""
        ...

    def exists(self, key: str) -> bool:
        """Return True iff an object exists at `key`."""
        ...

    def size(self, key: str) -> int:
        """Return the size of the object at `key` in bytes (assumes exists)."""
        ...

    def delete(self, key: str) -> None:
        """Delete the object at `key` (no-op if missing)."""
        ...

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        """Write bytes to `key` (server-side; not used by clients directly)."""
        ...

    def get_bytes(self, key: str) -> bytes:
        """Read bytes from `key` (server-side; not used by clients directly)."""
        ...