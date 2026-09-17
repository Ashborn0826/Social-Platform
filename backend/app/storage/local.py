"""Local filesystem implementation of ObjectStorage.

Files live under `settings.local_storage_dir/<key>`. The "presigned" URLs
are actually URLs to our own `/api/uploads/local/{key}` route, signed with
HMAC-SHA256 using `settings.storage_secret`. The signature covers the key,
expiry, content-type, and mode (put|get) so a tampered URL is rejected.

Used in dev, tests, and any deployment where you don't want to depend on
S3-compatible object storage.
"""
import hashlib
import hmac
import time
from pathlib import Path


class LocalBackend:
    def __init__(self, base_dir: str, api_base_url: str, secret: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.api_base_url = api_base_url.rstrip("/")
        self.secret = secret

    def _path(self, key: str) -> Path:
        # Prevent path traversal: reject keys with '..' or absolute path components
        if ".." in key or key.startswith("/") or "\\" in key:
            raise ValueError(f"invalid key: {key!r}")
        return self.base_dir / key

    def _sign(self, key: str, expires_at: int, content_type: str, mode: str) -> str:
        msg = f"{key}|{expires_at}|{content_type}|{mode}".encode()
        return hmac.new(self.secret.encode(), msg, hashlib.sha256).hexdigest()

    def presigned_put_url(
        self, key: str, content_type: str, expires_seconds: int = 900
    ) -> str:
        expires = int(time.time()) + expires_seconds
        sig = self._sign(key, expires, content_type, "put")
        ct = _urlquote(content_type)
        return (
            f"{self.api_base_url}/api/uploads/local/{key}"
            f"?expires={expires}&sig={sig}&mode=put&content_type={ct}"
        )

    def presigned_get_url(
        self, key: str, content_type: str, expires_seconds: int = 900
    ) -> str:
        expires = int(time.time()) + expires_seconds
        sig = self._sign(key, expires, content_type, "get")
        ct = _urlquote(content_type)
        return (
            f"{self.api_base_url}/api/uploads/local/{key}"
            f"?expires={expires}&sig={sig}&mode=get&content_type={ct}"
        )

    def verify_signature(
        self, key: str, expires: int, content_type: str, mode: str, sig: str
    ) -> None:
        """Verify a signature. Raises ValueError on bad sig / expired / wrong params."""
        if int(time.time()) > expires:
            raise ValueError("expired")
        expected = self._sign(key, expires, content_type, mode)
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad_signature")

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def size(self, key: str) -> int:
        return self._path(key).stat().st_size

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()


def _urlquote(s: str) -> str:
    """Minimal URL-encoding for the content_type query param value."""
    from urllib.parse import quote
    return quote(s, safe="")