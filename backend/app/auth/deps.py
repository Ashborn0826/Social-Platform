from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import InvalidTokenError, decode_token
from app.db.models import User
from app.db.repository import UserRepository
from app.db.session import get_session


bearer_scheme = HTTPBearer(auto_error=False)


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Resolve the current authenticated user from the Authorization header.

    Returns 401 for any failure: missing header, invalid/expired token,
    or token references a user that no longer exists. Single error code so
    callers don't need to differentiate 'no token' from 'bad token'.
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing_token")

    try:
        payload = decode_token(credentials.credentials, expected_type="access")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid_token") from None

    user_id = int(payload["sub"])
    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="user_not_found") from None

    return user