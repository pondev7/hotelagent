"""The call-task queue, over HTTP.

Read-only at S07. Claiming a task and recording its outcome are mutations with
an idempotency story of their own (invariant #5) and they belong with the queue
screen that will use them, in S10 — the service functions already exist and are
tested, so this is a routing decision rather than missing work.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.api.pagination import Page, page_of
from hotelagent.api.params import DEFAULT_PAGE_SIZE, CityId, Limit, Offset
from hotelagent.db.session import get_session
from hotelagent.errors import ERROR_RESPONSES
from hotelagent.modules.ops import service

# From `schemas`, never from `models` — see the note in the conversation router.
from hotelagent.modules.ops.schemas import CallTaskStatus, CallTaskSummary

router = APIRouter(prefix="/api/call-tasks", tags=["call-tasks"], responses=ERROR_RESPONSES)


@router.get("")
async def list_call_tasks(
    session: Annotated[AsyncSession, Depends(get_session)],
    city_id: CityId,
    status: Annotated[CallTaskStatus | None, Query(description="Filter by status.")] = None,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> Page[CallTaskSummary]:
    """The queue for one city, longest-waiting first."""
    tasks, total = await service.list_call_tasks(
        session, city_id=city_id, status=status, limit=limit, offset=offset
    )
    return page_of(tasks, total=total, limit=limit, offset=offset)
