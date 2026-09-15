from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import hash_password, verify_password
from app.auth.tokens import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.db.repository import EmailAlreadyExistsError, UserRepository
from app.db.session import get_session
from app.schemas import (
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_response(user) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at,
    )


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    repo = UserRepository(session)
    existing = await repo.get_by_email(payload.email)
    if existing is not None:
        raise HTTPException(status_code=409, detail="email_taken") from None

    try:
        user = await repo.create(
            email=payload.email,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
        )
    except EmailAlreadyExistsError:
        # Race condition: another request inserted the same email between our
        # get_by_email check and our insert. Surface as 409 like the check above.
        raise HTTPException(status_code=409, detail="email_taken") from None

    access = create_access_token(user.id)
    refresh, _ = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=_user_response(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    repo = UserRepository(session)
    user = await repo.get_by_email(payload.email)
    # Same error code for unknown email and wrong password — don't leak
    # which emails are registered.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid_credentials") from None

    access = create_access_token(user.id)
    refresh, _ = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=_user_response(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    try:
        claims = decode_token(payload.refresh_token, expected_type="refresh")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid_token") from None

    user_id = int(claims["sub"])
    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="user_not_found") from None

    access = create_access_token(user.id)
    new_refresh, _ = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access,
        refresh_token=new_refresh,
        user=_user_response(user),
    )