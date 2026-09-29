import pytest

from app.db.repository import (
    AlreadyFollowingError,
    FollowRepository,
    NotFollowingError,
    UserRepository,
)


_DUMMY_HASH = "$2b$12$abcdefghijklmnopqrstuuW4MCKbvDxFC5mDb5n3qV7G"


async def test_follow_creates_row(session):
    a = await UserRepository(session).create(email="a@x.com", password_hash=_DUMMY_HASH, display_name="A")
    b = await UserRepository(session).create(email="b@x.com", password_hash=_DUMMY_HASH, display_name="B")
    await session.commit()

    repo = FollowRepository(session)
    f = await repo.follow(follower_id=a.id, followee_id=b.id)
    assert f.follower_id == a.id
    assert f.followee_id == b.id


async def test_duplicate_follow_raises(session):
    a = await UserRepository(session).create(email="a@x.com", password_hash=_DUMMY_HASH, display_name="A")
    b = await UserRepository(session).create(email="b@x.com", password_hash=_DUMMY_HASH, display_name="B")
    await session.commit()

    repo = FollowRepository(session)
    await repo.follow(a.id, b.id)
    with pytest.raises(AlreadyFollowingError):
        await repo.follow(a.id, b.id)


async def test_unfollow_removes_row(session):
    a = await UserRepository(session).create(email="a@x.com", password_hash=_DUMMY_HASH, display_name="A")
    b = await UserRepository(session).create(email="b@x.com", password_hash=_DUMMY_HASH, display_name="B")
    await session.commit()

    repo = FollowRepository(session)
    await repo.follow(a.id, b.id)
    await repo.unfollow(a.id, b.id)

    assert await repo.is_following(a.id, b.id) is False


async def test_unfollow_not_following_raises(session):
    a = await UserRepository(session).create(email="a@x.com", password_hash=_DUMMY_HASH, display_name="A")
    b = await UserRepository(session).create(email="b@x.com", password_hash=_DUMMY_HASH, display_name="B")
    await session.commit()

    repo = FollowRepository(session)
    with pytest.raises(NotFollowingError):
        await repo.unfollow(a.id, b.id)


async def test_is_following_returns_true_for_existing(session):
    a = await UserRepository(session).create(email="a@x.com", password_hash=_DUMMY_HASH, display_name="A")
    b = await UserRepository(session).create(email="b@x.com", password_hash=_DUMMY_HASH, display_name="B")
    await session.commit()

    repo = FollowRepository(session)
    await repo.follow(a.id, b.id)
    assert await repo.is_following(a.id, b.id) is True
    assert await repo.is_following(b.id, a.id) is False  # direction matters


async def test_list_follower_ids_of_returns_correct_set(session):
    a = await UserRepository(session).create(email="a@x.com", password_hash=_DUMMY_HASH, display_name="A")
    b = await UserRepository(session).create(email="b@x.com", password_hash=_DUMMY_HASH, display_name="B")
    c = await UserRepository(session).create(email="c@x.com", password_hash=_DUMMY_HASH, display_name="C")
    await session.commit()

    repo = FollowRepository(session)
    # A and C follow B; B follows nobody
    await repo.follow(a.id, b.id)
    await repo.follow(c.id, b.id)

    followers = await repo.list_follower_ids_of(b.id)
    assert sorted(followers) == sorted([a.id, c.id])
    assert await repo.list_follower_ids_of(a.id) == []
