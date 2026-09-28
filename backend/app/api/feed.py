"""Feed endpoints: follow / unfollow / read feed."""
from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.cache.redis_client import get_redis
from app.db.models import User
from app.db.repository import (
    AlreadyFollowingError,
    FollowRepository,
    NotFollowingError,
    UserRepository,
)
from app.db.session import get_session
from app.feed.service import FeedService
from app.schemas import (
    FeedAttachment,
    FeedPostAuthor,
    FeedPostItem,
    FeedResponse,
)
from app.storage.base import ObjectStorage
from app.storage.factory import get_storage

router = APIRouter(prefix="/api", tags=["feed"])


@router.post("/users/{user_id}/follow", status_code=201)
async def follow_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    if user_id == user.id:
        # Self-follow would create noise and let users trivially pollute
        # their own timeline. Reject with 400.
        raise HTTPException(status_code=400, detail="cannot_follow_self") from None

    target = await UserRepository(session).get_by_id(user_id)
    if target is None:
        # 404 for non-existent user (no enumeration: same code as not-followed)
        raise HTTPException(status_code=404, detail="not_found") from None

    repo = FollowRepository(session)
    try:
        await repo.follow(follower_id=user.id, followee_id=user_id)
    except AlreadyFollowingError:
        raise HTTPException(status_code=409, detail="already_following") from None


@router.delete("/users/{user_id}/follow", status_code=204)
async def unfollow_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    repo = FollowRepository(session)
    try:
        await repo.unfollow(follower_id=user.id, followee_id=user_id)
    except NotFollowingError:
        raise HTTPException(status_code=404, detail="not_following") from None


@router.get("/feed", response_model=FeedResponse)
async def get_feed(
    limit: int = Query(20, ge=1, le=100),
    before: int | None = Query(None, description="Return posts with id < this cursor"),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    storage: ObjectStorage = Depends(get_storage),
    user: User = Depends(current_user),
) -> FeedResponse:
    service = FeedService(session, redis)
    items = await service.read_feed(
        user_id=user.id, limit=limit, before=before, storage=storage
    )
    next_cursor = items[-1]["id"] if len(items) == limit else None
    return FeedResponse(
        posts=[FeedPostItem(**item) for item in items],
        next_cursor=next_cursor,
    )