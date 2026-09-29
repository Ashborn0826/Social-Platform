"""Chat REST endpoints: create-or-get chat, list chats, list messages.

WebSocket endpoints live in app.realtime.ws.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import current_user
from app.db.models import User
from app.db.repository import ChatRepository, UserRepository
from app.db.session import get_session
from app.schemas import (
    ChatHistoryResponse,
    ChatListResponse,
    ChatPeerInfo,
    ChatSummary,
    CreateChatResponse,
    MessageInfo,
)

router = APIRouter(prefix="/api/chats", tags=["chats"])


@router.post("/{peer_user_id}", response_model=CreateChatResponse, status_code=201)
async def create_or_get_chat(
    peer_user_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> CreateChatResponse:
    if peer_user_id == user.id:
        # Don't allow self-chats (would just create a chat with one user
        # that's blocked by the HAVING COUNT=2 check anyway, but reject
        # earlier for clarity).
        raise HTTPException(status_code=400, detail="cannot_chat_with_self") from None

    peer = await UserRepository(session).get_by_id(peer_user_id)
    if peer is None:
        raise HTTPException(status_code=404, detail="not_found") from None

    chat = await ChatRepository(session).get_or_create_chat(
        user_a_id=user.id, user_b_id=peer_user_id
    )
    return CreateChatResponse(chat_id=chat.id)


@router.get("", response_model=ChatListResponse)
async def list_chats(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> ChatListResponse:
    rows = await ChatRepository(session).list_chats_for_user(user.id)
    items: list[ChatSummary] = []
    for row in rows:
        peer = ChatPeerInfo(**row["peer"])
        last_msg = None
        if row["last_message"] is not None:
            last_msg = MessageInfo(
                chat_id=row["chat_id"],
                **row["last_message"],
            )
        items.append(
            ChatSummary(
                chat_id=row["chat_id"],
                peer=peer,
                last_message=last_msg,
            )
        )
    return ChatListResponse(chats=items)


@router.get("/{chat_id}/messages", response_model=ChatHistoryResponse)
async def list_chat_messages(
    chat_id: int,
    limit: int = Query(50, ge=1, le=100),
    before: int | None = Query(None),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
) -> ChatHistoryResponse:
    repo = ChatRepository(session)
    if not await repo.is_participant(chat_id, user.id):
        raise HTTPException(status_code=403, detail="not_participant") from None

    messages = await repo.list_messages(chat_id, limit=limit, before=before)
    items = [
        MessageInfo(
            id=m.id,
            chat_id=m.chat_id,
            sender_id=m.sender_id,
            text=m.text,
            created_at=m.created_at,
        )
        for m in messages
    ]
    return ChatHistoryResponse(messages=items)