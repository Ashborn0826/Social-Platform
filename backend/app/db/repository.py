from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Attachment,
    Chat,
    ChatParticipant,
    Follow,
    Message,
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

    async def mark_processing(self, attachment_id: int) -> None:
        att = await self.get_by_id(attachment_id)
        if att is None:
            return
        att.status = "processing"
        await self.session.commit()

    async def mark_failed(self, attachment_id: int) -> None:
        att = await self.get_by_id(attachment_id)
        if att is None:
            return
        att.status = "failed"
        await self.session.commit()

    async def update_thumbnail(self, attachment_id: int, thumbnail_key: str) -> None:
        att = await self.get_by_id(attachment_id)
        if att is None:
            return
        att.thumbnail_key = thumbnail_key
        # Mark the attachment as ready again after successful thumbnail processing.
        # mark_processing set it to 'processing' before the work; we restore 'ready'
        # here because the attachment is fully ready (original + thumbnail both
        # in storage).
        att.status = "ready"
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


class ChatRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_chat(self, user_a_id: int, user_b_id: int) -> Chat:
        """Find an existing chat between these two users, or create one.

        Uses HAVING COUNT to ensure both users are participants.
        """
        from sqlalchemy import func

        if user_a_id == user_b_id:
            raise ValueError("cannot_chat_with_self")

        stmt = (
            select(Chat)
            .join(ChatParticipant, ChatParticipant.chat_id == Chat.id)
            .where(ChatParticipant.user_id.in_([user_a_id, user_b_id]))
            .group_by(Chat.id)
            .having(func.count(func.distinct(ChatParticipant.user_id)) == 2)
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        chat = Chat()
        self.session.add(chat)
        await self.session.flush()  # populate chat.id
        self.session.add_all([
            ChatParticipant(chat_id=chat.id, user_id=user_a_id),
            ChatParticipant(chat_id=chat.id, user_id=user_b_id),
        ])
        await self.session.commit()
        await self.session.refresh(chat)
        return chat

    async def is_participant(self, chat_id: int, user_id: int) -> bool:
        result = await self.session.execute(
            select(ChatParticipant.chat_id).where(
                ChatParticipant.chat_id == chat_id,
                ChatParticipant.user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def get_participant_ids(self, chat_id: int) -> list[int]:
        result = await self.session.execute(
            select(ChatParticipant.user_id).where(ChatParticipant.chat_id == chat_id)
        )
        return [row[0] for row in result.all()]

    async def list_chats_for_user(self, user_id: int) -> list[dict]:
        """Return all chats the user is in, with peer info + last message.

        Hydration done in SQL (3 queries total): get chats, get peers,
        get last messages. Hydrating in Python would be N+1.
        """
        # 1. Get chat IDs the user is in
        result = await self.session.execute(
            select(ChatParticipant.chat_id).where(ChatParticipant.user_id == user_id)
        )
        chat_ids = [row[0] for row in result.all()]
        if not chat_ids:
            return []

        # 2. Get peers (the other participant in each chat)
        my_chats_q = (
            select(ChatParticipant.chat_id)
            .where(ChatParticipant.user_id == user_id)
            .subquery()
        )
        result = await self.session.execute(
            select(
                ChatParticipant.chat_id.label("chat_id"),
                User.id.label("peer_id"),
                User.display_name.label("peer_display_name"),
            )
            .join(User, User.id == ChatParticipant.user_id)
            .where(
                ChatParticipant.chat_id.in_(select(my_chats_q.c.chat_id)),
                ChatParticipant.user_id != user_id,
            )
        )
        peer_by_chat: dict[int, dict] = {}
        for chat_id, uid, display_name in result.all():
            peer_by_chat[chat_id] = {"id": uid, "display_name": display_name}

        # 3. Get last message per chat (using a window function would be cleaner;
        #    for clarity we use a subquery)
        from sqlalchemy import func as sa_func
        last_msg_subq = (
            select(
                Message.chat_id,
                Message.id,
                Message.sender_id,
                Message.text,
                Message.created_at,
                sa_func.row_number()
                .over(partition_by=Message.chat_id, order_by=Message.id.desc())
                .label("rn"),
            )
            .subquery()
        )
        result = await self.session.execute(
            select(
                last_msg_subq.c.chat_id,
                last_msg_subq.c.id,
                last_msg_subq.c.sender_id,
                last_msg_subq.c.text,
                last_msg_subq.c.created_at,
            ).where(last_msg_subq.c.rn == 1)
            .where(last_msg_subq.c.chat_id.in_(chat_ids))
        )
        last_msg_by_chat: dict[int, dict] = {}
        for chat_id, mid, sender_id, text, created_at in result.all():
            last_msg_by_chat[chat_id] = {
                "id": mid, "sender_id": sender_id, "text": text, "created_at": created_at
            }

        return [
            {
                "chat_id": cid,
                "peer": peer_by_chat.get(cid, {"id": 0, "display_name": "unknown"}),
                "last_message": last_msg_by_chat.get(cid),
            }
            for cid in chat_ids
        ]

    async def create_message(self, chat_id: int, sender_id: int, text: str) -> Message:
        msg = Message(chat_id=chat_id, sender_id=sender_id, text=text)
        self.session.add(msg)
        await self.session.commit()
        await self.session.refresh(msg)
        return msg

    async def list_messages(
        self, chat_id: int, limit: int = 50, before: Optional[int] = None
    ) -> list[Message]:
        query = (
            select(Message)
            .where(Message.chat_id == chat_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
        if before is not None:
            query = query.where(Message.id < before)
        result = await self.session.execute(query)
        return list(result.scalars().all())