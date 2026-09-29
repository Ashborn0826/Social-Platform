"""Feed service: fan-out on write, cache-aside reads.

Fan-out on write: when a post is created, we synchronously insert a row
into `timeline_entries` for each follower, and ZADD the post id into a
Redis sorted set keyed `feed:{user_id}`. The fan-out is in the request
path — acceptable up to ~10k followers per user. Documented future work:
async fan-out via a worker for celebrity users.

Cache-aside reads: `GET /api/feed` reads post ids from the Redis sorted
set first (fast path, ~1ms). On miss (Redis empty or evicted), falls back
to a `SELECT post_id FROM timeline_entries ORDER BY post_id DESC LIMIT n`
query against Postgres (slower, ~10ms). The Redis key is repopulated on
the next write that affects this user.

Hydration: regardless of the source, we batch-load posts + authors +
attachments and emit a list of `FeedPostItem` with presigned attachment URLs.
"""
import logging

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Attachment, Post, PostAttachment, User
from app.db.repository import FollowRepository, TimelineRepository
from app.storage.base import ObjectStorage

logger = logging.getLogger(__name__)

FEED_KEY = "feed:{user_id}"  # Redis sorted set; score == post id (newest first)


class FeedService:
    def __init__(self, session: AsyncSession, redis: Redis):
        self.session = session
        self.redis = redis

    async def fan_out_post(self, post_id: int, author_id: int) -> int:
        """Append post_id to every follower's timeline (Redis + Postgres).

        Includes the author in the fan-out so their own posts appear in their
        own feed without requiring self-follow (which the API rejects).

        Returns the number of users the post was fanned out to.
        """
        follower_ids = await FollowRepository(self.session).list_follower_ids_of(author_id)
        # Always include the author so they see their own posts in their feed.
        recipients = list(follower_ids) + [author_id]

        # Postgres durable copy
        await TimelineRepository(self.session).insert_many(recipients, post_id)

        # Redis cache: ZADD into each recipient's feed
        pipe = self.redis.pipeline()
        for fid in recipients:
            pipe.zadd(FEED_KEY.format(user_id=fid), {str(post_id): float(post_id)})
        await pipe.execute()

        await self.session.commit()
        return len(recipients)

    async def get_post_ids(
        self, user_id: int, limit: int, before: int | None = None
    ) -> list[int]:
        """Return post ids for the user's feed, newest first.

        Tries the Redis sorted set first; falls through to Postgres if empty.
        The cursor `before` is exclusive (returns posts with id < before).
        """
        key = FEED_KEY.format(user_id=user_id)

        if before is None:
            raw = await self.redis.zrevrange(key, 0, limit - 1)
        else:
            # Exclusive upper bound (the `(` prefix in Redis)
            raw = await self.redis.zrevrangebyscore(
                key, f"({before}", "-inf", start=0, num=limit
            )

        if raw:
            return [int(x) for x in raw]

        # Cache miss: fall through to Postgres timeline_entries
        return await TimelineRepository(self.session).list_post_ids_for_user(
            user_id=user_id, limit=limit, before=before
        )

    async def hydrate(
        self,
        post_ids: list[int],
        storage: ObjectStorage,
    ) -> list[dict]:
        """Batch-load posts + authors + attachments, return hydrated FeedPostItem dicts."""
        if not post_ids:
            return []

        # Load posts (preserve feed order)
        result = await self.session.execute(
            select(Post).where(Post.id.in_(post_ids))
        )
        posts_by_id = {p.id: p for p in result.scalars().all()}
        ordered = [posts_by_id[pid] for pid in post_ids if pid in posts_by_id]
        if not ordered:
            return []

        # Load authors in one query
        author_ids = list({p.author_id for p in ordered})
        result = await self.session.execute(
            select(User).where(User.id.in_(author_ids))
        )
        authors_by_id = {u.id: u for u in result.scalars().all()}

        # Load post_attachments (ordered by position)
        result = await self.session.execute(
            select(PostAttachment).where(
                PostAttachment.post_id.in_([p.id for p in ordered])
            )
        )
        pa_by_post: dict[int, list[PostAttachment]] = {}
        for pa in result.scalars().all():
            pa_by_post.setdefault(pa.post_id, []).append(pa)
        for pas in pa_by_post.values():
            pas.sort(key=lambda x: x.position)

        # Load attachment metadata
        att_ids = {pa.attachment_id for pas in pa_by_post.values() for pa in pas}
        atts_by_id: dict[int, Attachment] = {}
        if att_ids:
            result = await self.session.execute(
                select(Attachment).where(Attachment.id.in_(att_ids))
            )
            atts_by_id = {a.id: a for a in result.scalars().all()}

        # Build the hydrated list
        items: list[dict] = []
        for post in ordered:
            author = authors_by_id.get(post.author_id)
            if author is None:
                # Author deleted but post still around (CASCADE didn't fire
                # because of a race); skip the orphaned post
                continue

            attachments: list[dict] = []
            for pa in pa_by_post.get(post.id, []):
                att = atts_by_id.get(pa.attachment_id)
                if att is None:
                    continue
                attachments.append(
                    {
                        "id": att.id,
                        "content_type": att.content_type,
                        "url": storage.presigned_get_url(
                            att.storage_key, att.content_type
                        ),
                        "thumbnail_url": None,  # Phase 5
                    }
                )

            items.append(
                {
                    "id": post.id,
                    "text": post.text,
                    "created_at": post.created_at,
                    "author": {
                        "id": author.id,
                        "display_name": author.display_name,
                    },
                    "attachments": attachments,
                }
            )
        return items

    async def read_feed(
        self,
        user_id: int,
        limit: int,
        before: int | None,
        storage: ObjectStorage,
    ) -> list[dict]:
        """High-level read: get post ids, hydrate, return list."""
        post_ids = await self.get_post_ids(user_id, limit, before)
        return await self.hydrate(post_ids, storage)