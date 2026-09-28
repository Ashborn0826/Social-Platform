from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Attachment,
    Follow,
    Post,
    PostAttachment,
    TimelineEntry,
    User,
)


class EmailAlreadyExistsError(Exception):
    """Raised when creating a user with an email that's already taken."""


def _is_email_unique_violation(error: IntegrityError) -> bool:
    """Inspect an IntegrityError to confirm it's a UNIQUE violation on users.email."""
    orig = error.orig
    msg = str(orig).lower()
    if "unique" in msg and "email" in msg:
        return True
    diag = getattr(orig, "diag", None)
    if diag is not None:
        constraint = getattr(diag, "constraint_name", "") or ""
        if "email" in constraint:
            return True
    return False


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, email: str, password_hash: str, display_name: str) -> User:
        user = User(email=email, password_hash=password_hash, display_name=display_name)
        self.session.add(user)
        try:
            await self.session.commit()
        except IntegrityError as e:
            await self.session.rollback()
            if _is_email_unique_violation(e):
                raise EmailAlreadyExistsError(email) from None
            raise
        await self.session.refresh(user)
        return user

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()


class PostRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, author_id: int, text: str) -> Post:
        post = Post(author_id=author_id, text=text)
        self.session.add(post)
        await self.session.commit()
        await self.session.refresh(post)
        return post

    async def get_by_id(self, post_id: int) -> Optional[Post]:
        result = await self.session.execute(select(Post).where(Post.id == post_id))
        return result.scalar_one_or_none()

    async def list_by_author(
        self,
        author_id: int,
        limit: int = 20,
        before: Optional[int] = None,
    ) -> list[Post]:
        query = (
            select(Post)
            .where(Post.author_id == author_id)
            .order_by(Post.id.desc())
            .limit(limit)
        )
        if before is not None:
            query = query.where(Post.id < before)
        result = await self.session.execute(query)
        return list(result.scalars().all())


class AttachmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        owner_id: int,
        content_type: str,
        size_bytes: int,
        storage_key: str,
    ) -> Attachment:
        att = Attachment(
            owner_id=owner_id,
            content_type=content_type,
            size_bytes=size_bytes,
            storage_key=storage_key,
            status="pending",
        )
        self.session.add(att)
        await self.session.commit()
        await self.session.refresh(att)
        return att

    async def get_by_id(self, attachment_id: int) -> Attachment | None:
        result = await self.session.execute(
            select(Attachment).where(Attachment.id == attachment_id)
        )
        return result.scalar_one_or_none()

    async def mark_ready(self, attachment_id: int) -> None:
        att = await self.get_by_id(attachment_id)
        if att is None:
            return
        att.status = "ready"
        att.completed_at = datetime.now(timezone.utc)
        await self.session.commit()


class PostAttachmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def attach(self, post_id: int, attachment_id: int, position: int = 0) -> None:
        pa = PostAttachment(
            post_id=post_id, attachment_id=attachment_id, position=position
        )
        self.session.add(pa)
        await self.session.flush()


class AlreadyFollowingError(Exception):
    """Raised when follow() is called for an existing follow."""


class NotFollowingError(Exception):
    """Raised when unfollow() is called but the user is not following."""


class FollowRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def follow(self, follower_id: int, followee_id: int) -> Follow:
        f = Follow(follower_id=follower_id, followee_id=followee_id)
        self.session.add(f)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise AlreadyFollowingError() from None
        await self.session.refresh(f)
        return f

    async def unfollow(self, follower_id: int, followee_id: int) -> bool:
        result = await self.session.execute(
            select(Follow).where(
                Follow.follower_id == follower_id, Follow.followee_id == followee_id
            )
        )
        f = result.scalar_one_or_none()
        if f is None:
            raise NotFollowingError() from None
        await self.session.delete(f)
        await self.session.commit()
        return True

    async def is_following(self, follower_id: int, followee_id: int) -> bool:
        result = await self.session.execute(
            select(Follow.follower_id).where(
                Follow.follower_id == follower_id, Follow.followee_id == followee_id
            )
        )
        return result.scalar_one_or_none() is not None

    async def list_follower_ids_of(self, user_id: int) -> list[int]:
        """Return the IDs of users who follow `user_id`."""
        result = await self.session.execute(
            select(Follow.follower_id).where(Follow.followee_id == user_id)
        )
        return [row[0] for row in result.all()]


class TimelineRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def insert_many(self, user_ids: list[int], post_id: int) -> None:
        """Bulk insert timeline entries. The (user_id, post_id) PK prevents dupes."""
        if not user_ids:
            return
        from sqlalchemy import insert

        await self.session.execute(
            insert(TimelineEntry),
            [{"user_id": uid, "post_id": post_id} for uid in user_ids],
        )

    async def list_post_ids_for_user(
        self, user_id: int, limit: int, before: Optional[int] = None
    ) -> list[int]:
        query = (
            select(TimelineEntry.post_id)
            .where(TimelineEntry.user_id == user_id)
            .order_by(TimelineEntry.post_id.desc())
            .limit(limit)
        )
        if before is not None:
            query = query.where(TimelineEntry.post_id < before)
        result = await self.session.execute(query)
        return [row[0] for row in result.all()]