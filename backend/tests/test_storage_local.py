from app.storage.local import LocalBackend


def test_put_and_get_bytes(tmp_path):
    b = LocalBackend(base_dir=str(tmp_path), api_base_url="http://test", secret="s")
    b.put_bytes("foo.txt", b"hello", "text/plain")
    assert b.get_bytes("foo.txt") == b"hello"


def test_exists(tmp_path):
    b = LocalBackend(base_dir=str(tmp_path), api_base_url="http://test", secret="s")
    assert not b.exists("foo.txt")
    b.put_bytes("foo.txt", b"x", "text/plain")
    assert b.exists("foo.txt")


def test_size(tmp_path):
    b = LocalBackend(base_dir=str(tmp_path), api_base_url="http://test", secret="s")
    b.put_bytes("foo.txt", b"hello", "text/plain")
    assert b.size("foo.txt") == 5


def test_delete(tmp_path):
    b = LocalBackend(base_dir=str(tmp_path), api_base_url="http://test", secret="s")
    b.put_bytes("foo.txt", b"hello", "text/plain")
    b.delete("foo.txt")
    assert not b.exists("foo.txt")


def test_delete_nonexistent_is_noop(tmp_path):
    b = LocalBackend(base_dir=str(tmp_path), api_base_url="http://test", secret="s")
    b.delete("nope.txt")  # should not raise


def test_presigned_put_url_format(tmp_path):
    b = LocalBackend(base_dir=str(tmp_path), api_base_url="http://test", secret="s")
    url = b.presigned_put_url("attachments/1/abc.jpg", "image/jpeg", expires_seconds=60)
    assert url.startswith("http://test/api/uploads/local/attachments/1/abc.jpg")
    assert "mode=put" in url
    assert "content_type=" in url
    assert "expires=" in url
    assert "sig=" in url


def test_presigned_get_url_format(tmp_path):
    b = LocalBackend(base_dir=str(tmp_path), api_base_url="http://test", secret="s")
    url = b.presigned_get_url("foo.txt", "text/plain", expires_seconds=60)
    assert "mode=get" in url


def test_signature_verification(tmp_path):
    import time
    b = LocalBackend(base_dir=str(tmp_path), api_base_url="http://test", secret="s")
    expires = int(time.time()) + 60
    sig = b._sign("foo.txt", expires, "text/plain", "get")
    b.verify_signature("foo.txt", expires, "text/plain", "get", sig)


def test_signature_rejects_expired(tmp_path):
    import time
    import pytest
    b = LocalBackend(base_dir=str(tmp_path), api_base_url="http://test", secret="s")
    expires = int(time.time()) - 10
    sig = b._sign("foo.txt", expires, "text/plain", "get")
    with pytest.raises(ValueError, match="expired"):
        b.verify_signature("foo.txt", expires, "text/plain", "get", sig)


def test_signature_rejects_bad_sig(tmp_path):
    import time
    import pytest
    b = LocalBackend(base_dir=str(tmp_path), api_base_url="http://test", secret="s")
    expires = int(time.time()) + 60
    with pytest.raises(ValueError, match="bad_signature"):
        b.verify_signature("foo.txt", expires, "text/plain", "get", "deadbeef" * 8)


def test_signature_rejects_tampered_mode(tmp_path):
    """Sig is signed over key+expires+content_type+mode — changing mode invalidates."""
    import time
    import pytest
    b = LocalBackend(base_dir=str(tmp_path), api_base_url="http://test", secret="s")
    expires = int(time.time()) + 60
    sig = b._sign("foo.txt", expires, "text/plain", "get")
    with pytest.raises(ValueError, match="bad_signature"):
        b.verify_signature("foo.txt", expires, "text/plain", "put", sig)


def test_rejects_path_traversal_in_key(tmp_path):
    import pytest
    b = LocalBackend(base_dir=str(tmp_path), api_base_url="http://test", secret="s")
    with pytest.raises(ValueError, match="invalid key"):
        b.put_bytes("../etc/passwd", b"x", "text/plain")
    with pytest.raises(ValueError, match="invalid key"):
        b.put_bytes("/etc/passwd", b"x", "text/plain")