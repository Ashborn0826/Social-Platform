"""Users endpoint: list other users (for Discover page)."""
from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.cache.redis_client import get_redis
from app.db.models import User
from app.db.session import get_session
from app.schemas import UserListResponse, UserSummary

router = APIRouter(prefix="/api/users", tags=["users"])


async def _get_online_user_ids(redis: Redis) -> set[int]:
    """Scan Redis for `online:{user_id}` keys (set with TTL when WS connects)."""
    ids: set[int] = set()
    async for key in redis.scan_iter(match="online:*"):
        try:
            uid = int(key.split(":")[1])
            ids.add(uid)
        except (ValueError, IndexError):
            continue
    return ids


@router.get("", response_model=UserListResponse)
async def list_users(
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
    current: User = Depends(current_user),
) -> UserListResponse:
    """Return all users except the caller. Ordered newest-first.
    Each user gets is_online=true if they currently have an open WS."""
    result = await session.execute(
        select(User)
        .where(User.id != current.id)
        .order_by(User.id.desc())
        .limit(limit)
    )
    users = result.scalars().all()
    online_ids = await _get_online_user_ids(redis)
    return UserListResponse(
        users=[
            UserSummary(
                id=u.id,
                display_name=u.display_name,
                is_online=u.id in online_ids,
            )
            for u in users
        ]
    )