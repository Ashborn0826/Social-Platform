import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.config import settings

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=7)
ALGORITHM = "HS256"


class InvalidTokenError(Exception):
    """Raised when a JWT cannot be decoded or fails validation."""


def create_access_token(user_id: int) -> str:
    """Issue a short-lived access token for the given user."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + ACCESS_TOKEN_TTL).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_refresh_token(user_id: int) -> tuple[str, str]:
    """Issue a long-lived refresh token. Returns (token, jti)."""
    now = datetime.now(timezone.utc)
    jti = secrets.token_urlsafe(16)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + REFRESH_TOKEN_TTL).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    return token, jti


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    """Decode and verify a JWT. Raises InvalidTokenError on any failure.

    Validates signature, expiry, AND that the `type` claim matches expected_type
    (so an access token can't be used as a refresh token and vice versa).
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except JWTError as e:
        raise InvalidTokenError(str(e)) from e

    if payload.get("type") != expected_type:
        raise InvalidTokenError(
            f"expected type={expected_type}, got {payload.get('type')}"
        )

    return payload