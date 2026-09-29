import pytest

from app.db.repository import (
    FollowRepository,
    TimelineRepository,
    UserRepository,
)


_DUMMY_HASH = "$2b$12$abcdefghijklmnopqrstuuW4MCKbvDxFC5mDb5n3qV7G"


async def _make_user(session, email: str):
    u = await UserRepository(session).create(
        email=email, password_hash=_DUMMY_HASH, display_name=email.split("@")[0]
    )
    await session.commit()
    return u


async def _insert_post(session, author_id: int, text: str):
    from app.db.repository import PostRepository

    p = await PostRepository(session).create(author_id=author_id, text=text)
    await session.commit()
    return p


async def test_fan_out_inserts_for_all_followers(session, redis_client):
    alice = await _make_user(session, "alice@x.com")
    bob = await _make_user(session, "bob@x.com")
    carol = await _make_user(session, "carol@x.com")

    repo = FollowRepository(session)
    await repo.follow(alice.id, bob.id)
    await repo.follow(carol.id, bob.id)
    await session.commit()

    post = await _insert_post(session, bob.id, "hello followers")

    from app.feed.service import FeedService

    service = FeedService(session, redis_client)
    n = await service.fan_out_post(post_id=post.id, author_id=bob.id)
    # 2 followers (alice + carol) + bob himself (own posts go into own feed)
    assert n == 3

    # Redis cache populated for all three
    alice_feed = await redis_client.zrange(f"feed:{alice.id}", 0, -1)
    carol_feed = await redis_client.zrange(f"feed:{carol.id}", 0, -1)
    bob_feed = await redis_client.zrange(f"feed:{bob.id}", 0, -1)
    assert int(alice_feed[0]) == post.id
    assert int(carol_feed[0]) == post.id
    assert int(bob_feed[0]) == post.id

    # Postgres durable copy
    timeline = await TimelineRepository(session).list_post_ids_for_user(alice.id, limit=10)
    assert post.id in timeline


async def test_fan_out_with_no_followers_is_noop(session, redis_client):
    bob = await _make_user(session, "bob@x.com")
    post = await _insert_post(session, bob.id, "into the void")

    from app.feed.service import FeedService

    service = FeedService(session, redis_client)
    n = await service.fan_out_post(post_id=post.id, author_id=bob.id)
    # Bob himself still gets the post (so they see their own posts in feed)
    assert n == 1

    # Redis: bob's own feed has the post
    bob_feed = await redis_client.zrange(f"feed:{bob.id}", 0, -1)
    assert int(bob_feed[0]) == post.id
    # No other keys
    keys = await redis_client.keys("feed:*")
    assert len(keys) == 1


async def test_get_post_ids_uses_redis_when_present(session, redis_client):
    alice = await _make_user(session, "alice@x.com")
    bob = await _make_user(session, "bob@x.com")
    await session.commit()

    post1 = await _insert_post(session, bob.id, "post 1")
    post2 = await _insert_post(session, bob.id, "post 2")
    await session.commit()

    # Manually populate Redis with both post ids
    await redis_client.zadd(f"feed:{alice.id}", {str(post2.id): float(post2.id)})
    await redis_client.zadd(f"feed:{alice.id}", {str(post1.id): float(post1.id)})

    from app.feed.service import FeedService

    service = FeedService(session, redis_client)
    ids = await service.get_post_ids(alice.id, limit=10, before=None)
    # Newest first
    assert ids == [post2.id, post1.id]


async def test_get_post_ids_redis_cursor_excludes_previous(session, redis_client):
    alice = await _make_user(session, "alice@x.com")
    bob = await _make_user(session, "bob@x.com")
    await session.commit()

    p1 = await _insert_post(session, bob.id, "p1")
    p2 = await _insert_post(session, bob.id, "p2")
    p3 = await _insert_post(session, bob.id, "p3")
    await session.commit()

    await redis_client.zadd(f"feed:{alice.id}", {str(p1.id): float(p1.id)})
    await redis_client.zadd(f"feed:{alice.id}", {str(p2.id): float(p2.id)})
    await redis_client.zadd(f"feed:{alice.id}", {str(p3.id): float(p3.id)})

    from app.feed.service import FeedService

    service = FeedService(session, redis_client)
    # Page 1: all 3
    page1 = await service.get_post_ids(alice.id, limit=10, before=None)
    assert page1 == [p3.id, p2.id, p1.id]
    # Page 2: posts with id < p2.id (exclusive)
    page2 = await service.get_post_ids(alice.id, limit=10, before=p2.id)
    assert page2 == [p1.id]


async def test_get_post_ids_falls_back_to_postgres_on_cache_miss(session, redis_client):
    """When Redis is empty, we read from timeline_entries directly."""
    alice = await _make_user(session, "alice@x.com")
    bob = await _make_user(session, "bob@x.com")
    await session.commit()

    p1 = await _insert_post(session, bob.id, "p1")
    p2 = await _insert_post(session, bob.id, "p2")
    await session.commit()

    # Populate Postgres timeline but not Redis
    await TimelineRepository(session).insert_many([alice.id], p1.id)
    await TimelineRepository(session).insert_many([alice.id], p2.id)
    await session.commit()

    from app.feed.service import FeedService

    service = FeedService(session, redis_client)
    ids = await service.get_post_ids(alice.id, limit=10, before=None)
    assert ids == [p2.id, p1.id]


async def test_hydrate_loads_posts_authors_attachments(session, redis_client, storage):
    alice = await _make_user(session, "alice@x.com")
    bob = await _make_user(session, "bob@x.com")
    await session.commit()

    post = await _insert_post(session, bob.id, "with image")

    # Create a ready attachment owned by Bob
    from app.db.repository import AttachmentRepository, PostAttachmentRepository

    storage.put_bytes(f"attachments/{bob.id}/img.jpg", b"jpeg-bytes", "image/jpeg")
    att = await AttachmentRepository(session).create(
        owner_id=bob.id,
        content_type="image/jpeg",
        size_bytes=11,
        storage_key=f"attachments/{bob.id}/img.jpg",
    )
    await session.commit()
    storage.put_bytes(f"attachments/{bob.id}/img.jpg", b"jpeg-bytes", "image/jpeg")
    await AttachmentRepository(session).mark_ready(att.id)
    await session.commit()

    await PostAttachmentRepository(session).attach(post.id, att.id, position=0)
    await session.commit()

    from app.feed.service import FeedService

    service = FeedService(session, redis_client)
    items = await service.hydrate([post.id], storage)

    assert len(items) == 1
    item = items[0]
    assert item["id"] == post.id
    assert item["text"] == "with image"
    assert item["author"]["id"] == bob.id
    assert item["author"]["display_name"] == "bob"
    assert len(item["attachments"]) == 1
    assert item["attachments"][0]["content_type"] == "image/jpeg"
    # URL is a signed presigned URL
    assert "expires=" in item["attachments"][0]["url"]


async def test_hydrate_skips_posts_missing_author(session, redis_client, storage):
    """If a post's author was deleted but the post remains (race), skip it."""
    alice = await _make_user(session, "alice@x.com")
    bob = await _make_user(session, "bob@x.com")
    await session.commit()

    post = await _insert_post(session, bob.id, "orphan incoming")

    # Manually delete bob to leave an orphaned post
    from sqlalchemy import delete
    from app.db.models import User
    await session.execute(delete(User).where(User.id == bob.id))
    await session.commit()

    from app.feed.service import FeedService

    service = FeedService(session, redis_client)
    items = await service.hydrate([post.id], storage)
    assert items == []
