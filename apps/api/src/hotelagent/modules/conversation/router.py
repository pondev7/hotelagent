"""The unified inbox and its transcripts, over HTTP.

`state` is typed as the enum rather than as a string, so `?state=activee` is a
422 from FastAPI before any handler runs. A free-text filter that silently
matches nothing is a support ticket about missing conversations; this is the
difference between a typo and a mystery.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.api.pagination import Page, page_of
from hotelagent.api.params import DEFAULT_PAGE_SIZE, CityId, Limit, Offset
from hotelagent.db.session import get_session
from hotelagent.errors import ERROR_RESPONSES
from hotelagent.modules.conversation import service

# `ConversationState` comes from `schemas`, not from `models`, even though this
# is the router of the module that owns both. `test_routers_do_not_import_models`
# bans the import unconditionally, and rightly: "it is only an enum" is exactly
# how a model import gets into a router, and the next one is a query.
from hotelagent.modules.conversation.schemas import (
    ConversationState,
    ConversationSummary,
    MessageOut,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"], responses=ERROR_RESPONSES)


@router.get("")
async def list_conversations(
    session: Annotated[AsyncSession, Depends(get_session)],
    city_id: CityId,
    state: Annotated[ConversationState | None, Query(description="Filter by state.")] = None,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> Page[ConversationSummary]:
    """The inbox for one city, most recently active first."""
    conversations, total = await service.list_conversations(
        session, city_id=city_id, state=state, limit=limit, offset=offset
    )
    return page_of(conversations, total=total, limit=limit, offset=offset)


@router.get("/{conversation_id}")
async def get_conversation(
    session: Annotated[AsyncSession, Depends(get_session)],
    conversation_id: uuid.UUID,
    city_id: CityId,
) -> ConversationSummary:
    """One conversation, scoped to the asking city."""
    return await service.get_conversation(session, conversation_id=conversation_id, city_id=city_id)


@router.get("/{conversation_id}/messages")
async def list_messages(
    session: Annotated[AsyncSession, Depends(get_session)],
    conversation_id: uuid.UUID,
    city_id: CityId,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> Page[MessageOut]:
    """One transcript, oldest first.

    `city_id` is required here too, even though the conversation id already
    implies a city. The redundancy is the point: it stops a guessed or leaked
    UUID from reading another city's message history, and it keeps the scoping
    rule one rule applied everywhere rather than a judgement made per endpoint.
    """
    messages, total = await service.list_messages(
        session,
        conversation_id=conversation_id,
        city_id=city_id,
        limit=limit,
        offset=offset,
    )
    return page_of(messages, total=total, limit=limit, offset=offset)
