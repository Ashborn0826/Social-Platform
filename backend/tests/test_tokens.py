from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.auth.tokens import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.config import settings


def test_access_token_round_trips():
    token = create_access_token(user_id=42)
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "42"
    assert payload["type"] == "access"


def test_refresh_token_round_trips():
    token, jti = create_refresh_token(user_id=42)
    payload = decode_token(token, expected_type="refresh")
    assert payload["sub"] == "42"
    assert payload["type"] == "refresh"
    assert payload["jti"] == jti


def test_refresh_token_jti_is_unique():
    _, jti1 = create_refresh_token(user_id=1)
    _, jti2 = create_refresh_token(user_id=1)
    assert jti1 != jti2


def test_decode_rejects_wrong_type():
    access = create_access_token(user_id=1)
    with pytest.raises(InvalidTokenError):
        decode_token(access, expected_type="refresh")


def test_decode_rejects_tampered_signature():
    token = create_access_token(user_id=1)
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    with pytest.raises(InvalidTokenError):
        decode_token(tampered, expected_type="access")


def test_decode_rejects_expired_token():
    expired = jwt.encode(
        {
            "sub": "1",
            "type": "access",
            "exp": int((datetime.now(timezone.utc) - timedelta(seconds=10)).timestamp()),
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_token(expired, expected_type="access")


def test_decode_rejects_garbage():
    with pytest.raises(InvalidTokenError):
        decode_token("not.a.jwt", expected_type="access")


def test_decode_rejects_token_signed_with_wrong_secret():
    forged = jwt.encode(
        {"sub": "1", "type": "access", "exp": 9999999999},
        "wrong-secret",
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_token(forged, expected_type="access")