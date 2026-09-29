import pytest

from app.db.repository import ChatRepository, UserRepository


_DUMMY_HASH = "$2b$12$abcdefghijklmnopqrstuuW4MCKbvDxFC5mDb5n3qV7G"


async def _make_user(session, email: str):
    u = await UserRepository(session).create(
        email=email, password_hash=_DUMMY_HASH, display_name=email.split("@")[0]
    )
    await session.commit()
    return u


async def test_get_or_create_chat_creates_new(session):
    a = await _make_user(session, "a@x.com")
    b = await _make_user(session, "b@x.com")
    await session.commit()

    repo = ChatRepository(session)
    chat = await repo.get_or_create_chat(a.id, b.id)
    assert chat.id > 0
    assert await repo.is_participant(chat.id, a.id)
    assert await repo.is_participant(chat.id, b.id)


async def test_get_or_create_chat_returns_existing(session):
    a = await _make_user(session, "a@x.com")
    b = await _make_user(session, "b@x.com")
    await session.commit()

    repo = ChatRepository(session)
    chat1 = await repo.get_or_create_chat(a.id, b.id)
    chat2 = await repo.get_or_create_chat(a.id, b.id)
    assert chat1.id == chat2.id


async def test_get_or_create_chat_different_direction_finds_same(session):
    """(a, b) and (b, a) should return the same chat."""
    a = await _make_user(session, "a@x.com")
    b = await _make_user(session, "b@x.com")
    await session.commit()

    repo = ChatRepository(session)
    chat_ab = await repo.get_or_create_chat(a.id, b.id)
    chat_ba = await repo.get_or_create_chat(b.id, a.id)
    assert chat_ab.id == chat_ba.id


async def test_get_or_create_chat_self_raises(session):
    a = await _make_user(session, "a@x.com")
    await session.commit()
    repo = ChatRepository(session)
    with pytest.raises(ValueError):
        await repo.get_or_create_chat(a.id, a.id)


async def test_is_participant_returns_false_for_non_participant(session):
    a = await _make_user(session, "a@x.com")
    b = await _make_user(session, "b@x.com")
    c = await _make_user(session, "c@x.com")
    await session.commit()

    repo = ChatRepository(session)
    chat = await repo.get_or_create_chat(a.id, b.id)

    assert await repo.is_participant(chat.id, c.id) is False


async def test_get_participant_ids_returns_both(session):
    a = await _make_user(session, "a@x.com")
    b = await _make_user(session, "b@x.com")
    await session.commit()

    repo = ChatRepository(session)
    chat = await repo.get_or_create_chat(a.id, b.id)
    ids = await repo.get_participant_ids(chat.id)
    assert sorted(ids) == sorted([a.id, b.id])


async def test_create_message_persists_text(session):
    a = await _make_user(session, "a@x.com")
    b = await _make_user(session, "b@x.com")
    await session.commit()
    repo = ChatRepository(session)
    chat = await repo.get_or_create_chat(a.id, b.id)

    msg = await repo.create_message(chat.id, a.id, "hello")
    assert msg.id > 0
    assert msg.text == "hello"
    assert msg.sender_id == a.id
    assert msg.chat_id == chat.id


async def test_list_messages_cursor_pagination(session):
    a = await _make_user(session, "a@x.com")
    b = await _make_user(session, "b@x.com")
    await session.commit()
    repo = ChatRepository(session)
    chat = await repo.get_or_create_chat(a.id, b.id)

    msg_ids = []
    for i in range(5):
        m = await repo.create_message(chat.id, a.id, f"msg {i}")
        msg_ids.append(m.id)

    page1 = await repo.list_messages(chat.id, limit=2)
    assert len(page1) == 2
    assert page1[0].id == msg_ids[-1]  # newest first

    page2 = await repo.list_messages(chat.id, limit=2, before=page1[-1].id)
    assert len(page2) == 2
    assert page2[0].id == msg_ids[-3]


async def test_list_chats_for_user_returns_each_chat_with_peer(session):
    a = await _make_user(session, "a@x.com")
    b = await _make_user(session, "b@x.com")
    c = await _make_user(session, "c@x.com")
    await session.commit()
    repo = ChatRepository(session)

    chat_ab = await repo.get_or_create_chat(a.id, b.id)
    chat_ac = await repo.get_or_create_chat(a.id, c.id)
    await repo.create_message(chat_ab.id, a.id, "hi b")
    await repo.create_message(chat_ac.id, a.id, "hi c")

    rows = await repo.list_chats_for_user(a.id)
    assert len(rows) == 2
    by_chat = {r["chat_id"]: r for r in rows}
    assert by_chat[chat_ab.id]["peer"]["id"] == b.id
    assert by_chat[chat_ac.id]["peer"]["id"] == c.id
    assert by_chat[chat_ab.id]["last_message"]["text"] == "hi b"
    assert by_chat[chat_ac.id]["last_message"]["text"] == "hi c"


async def test_list_chats_for_user_no_chats(session):
    a = await _make_user(session, "a@x.com")
    await session.commit()
    repo = ChatRepository(session)
    assert await repo.list_chats_for_user(a.id) == []
