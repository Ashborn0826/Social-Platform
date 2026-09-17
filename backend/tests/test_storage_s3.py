import boto3
import pytest
from moto import mock_aws

from app.storage.s3 import S3Backend


@pytest.fixture
def moto_aws():
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        yield


@pytest.fixture
def s3_backend(moto_aws):
    return S3Backend(bucket="test-bucket", region="us-east-1")


def test_s3_put_and_get(s3_backend):
    s3_backend.put_bytes("foo.txt", b"hello", "text/plain")
    assert s3_backend.exists("foo.txt")
    assert s3_backend.get_bytes("foo.txt") == b"hello"


def test_s3_size(s3_backend):
    s3_backend.put_bytes("foo.txt", b"hello world", "text/plain")
    assert s3_backend.size("foo.txt") == 11


def test_s3_delete(s3_backend):
    s3_backend.put_bytes("foo.txt", b"hello", "text/plain")
    s3_backend.delete("foo.txt")
    assert not s3_backend.exists("foo.txt")


def test_s3_exists_returns_false_for_missing(s3_backend):
    assert not s3_backend.exists("nope.txt")


def test_s3_presigned_put_url_format(s3_backend):
    url = s3_backend.presigned_put_url("foo.txt", "text/plain", expires_seconds=60)
    assert "X-Amz-Signature" in url
    assert "test-bucket" in url
    assert "foo.txt" in url


def test_s3_presigned_get_url_format(s3_backend):
    url = s3_backend.presigned_get_url("foo.txt", "text/plain", expires_seconds=60)
    assert "X-Amz-Signature" in url
    assert "test-bucket" in url