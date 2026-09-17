import pytest

from app.storage.factory import get_storage
from app.storage.local import LocalBackend
from app.storage.s3 import S3Backend


def test_factory_returns_local_for_local_backend(monkeypatch):
    monkeypatch.setattr("app.config.settings.object_storage_backend", "local")
    monkeypatch.setattr("app.config.settings.local_storage_dir", "/tmp/x")
    monkeypatch.setattr("app.config.settings.api_host", "http://test")
    monkeypatch.setattr("app.config.settings.storage_secret", "s")
    backend = get_storage()
    assert isinstance(backend, LocalBackend)


def test_factory_returns_s3_for_s3_backend(monkeypatch):
    monkeypatch.setattr("app.config.settings.object_storage_backend", "s3")
    monkeypatch.setattr("app.config.settings.s3_bucket", "test")
    monkeypatch.setattr("app.config.settings.s3_region", "us-east-1")
    backend = get_storage()
    assert isinstance(backend, S3Backend)


def test_factory_raises_for_unknown_backend(monkeypatch):
    monkeypatch.setattr("app.config.settings.object_storage_backend", "magic")
    with pytest.raises(ValueError, match="unknown OBJECT_STORAGE_BACKEND"):
        get_storage()