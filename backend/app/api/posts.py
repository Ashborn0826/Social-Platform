from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.db.models import User
from app.db.repository import PostRepository, UserRepository
from app.db.session import get_session
from app.schemas import (
    CreatePostRequest,
    PostListItem,
    PostListResponse,
    PostResponse,
    UserResponse,
)

router = APIRouter(prefix="/api", tags=["posts"])


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at,
    )


@router.post("/posts", response_model=PostResponse, status_code=201)
async def create_post(
    payload: CreatePostRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> PostResponse:
    repo = PostRepository(session)
    post = await repo.create(author_id=user.id, text=payload.text)
    return PostResponse(
        id=post.id,
        author_id=post.author_id,
        text=post.text,
        created_at=post.created_at,
        author=_user_response(user),
    )


@router.get("/posts/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: int,
    session: AsyncSession = Depends(get_session),
) -> PostResponse:
    post = await PostRepository(session).get_by_id(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="not_found") from None

    author = await UserRepository(session).get_by_id(post.author_id)
    return PostResponse(
        id=post.id,
        author_id=post.author_id,
        text=post.text,
        created_at=post.created_at,
        author=_user_response(author) if author else None,
    )


@router.get("/users/{user_id}/posts", response_model=PostListResponse)
async def list_user_posts(
    user_id: int,
    limit: int = Query(20, ge=1, le=100),
    before: int | None = Query(None, description="Return posts with id < this cursor"),
    session: AsyncSession = Depends(get_session),
) -> PostListResponse:
    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user_not_found") from None

    posts = await PostRepository(session).list_by_author(
        author_id=user_id, limit=limit, before=before
    )
    author = _user_response(user)
    items = [
        PostListItem(
            id=p.id,
            author_id=p.author_id,
            text=p.text,
            created_at=p.created_at,
            author=author,
        )
        for p in posts
    ]
    # If we got a full page, the last id is the cursor for the next page.
    next_cursor = posts[-1].id if len(posts) == limit else None
    return PostListResponse(posts=items, next_cursor=next_cursor)