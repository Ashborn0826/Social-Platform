import pytest

from app.db.repository import EmailAlreadyExistsError, PostRepository, UserRepository


_DUMMY_HASH = "$2b$12$abcdefghijklmnopqrstuuW4MCKbvDxFC5mDb5n3qV7G"


async def test_user_create_and_get_by_id(session):
    repo = UserRepository(session)
    user = await repo.create(
        email="alice@example.com",
        password_hash=_DUMMY_HASH,
        display_name="Alice",
    )
    fetched = await repo.get_by_id(user.id)
    assert fetched is not None
    assert fetched.email == "alice@example.com"
    assert fetched.display_name == "Alice"


async def test_user_get_by_email(session):
    repo = UserRepository(session)
    user = await repo.create(
        email="alice@example.com",
        password_hash=_DUMMY_HASH,
        display_name="Alice",
    )
    fetched = await repo.get_by_email("alice@example.com")
    assert fetched is not None
    assert fetched.id == user.id


async def test_user_get_by_email_unknown_returns_none(session):
    repo = UserRepository(session)
    assert await repo.get_by_email("nobody@example.com") is None


async def test_user_get_by_id_unknown_returns_none(session):
    repo = UserRepository(session)
    assert await repo.get_by_id(99999) is None


async def test_user_duplicate_email_raises(session):
    repo = UserRepository(session)
    await repo.create(
        email="dup@example.com", password_hash=_DUMMY_HASH, display_name="Alice"
    )
    with pytest.raises(EmailAlreadyExistsError):
        await repo.create(
            email="dup@example.com", password_hash=_DUMMY_HASH, display_name="Bob"
        )


async def test_post_create_and_get_by_id(session):
    user_repo = UserRepository(session)
    user = await user_repo.create(
        email="alice@example.com", password_hash=_DUMMY_HASH, display_name="Alice"
    )
    post_repo = PostRepository(session)
    post = await post_repo.create(author_id=user.id, text="hello")
    fetched = await post_repo.get_by_id(post.id)
    assert fetched is not None
    assert fetched.text == "hello"
    assert fetched.author_id == user.id


async def test_post_get_by_id_unknown_returns_none(session):
    repo = PostRepository(session)
    assert await repo.get_by_id(99999) is None


async def test_post_list_by_author_cursor_pagination(session):
    user_repo = UserRepository(session)
    user = await user_repo.create(
        email="alice@example.com", password_hash=_DUMMY_HASH, display_name="Alice"
    )
    post_repo = PostRepository(session)
    for i in range(5):
        await post_repo.create(author_id=user.id, text=f"post {i}")

    page1 = await post_repo.list_by_author(author_id=user.id, limit=2)
    assert len(page1) == 2

    page2 = await post_repo.list_by_author(
        author_id=user.id, limit=2, before=page1[-1].id
    )
    assert len(page2) == 2

    all_ids = {p.id for p in page1} | {p.id for p in page2}
    assert len(all_ids) == 4


async def test_post_list_by_author_empty(session):
    user_repo = UserRepository(session)
    user = await user_repo.create(
        email="alice@example.com", password_hash=_DUMMY_HASH, display_name="Alice"
    )
    post_repo = PostRepository(session)
    posts = await post_repo.list_by_author(author_id=user.id)
    assert posts == []