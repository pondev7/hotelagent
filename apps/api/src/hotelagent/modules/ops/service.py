"""Public surface of the ops module.

Ops owns human work: which hotel to ring, who is doing it, what they learned.
It deliberately knows nothing about *why* a call was raised — the availability
router owns that meaning. Ops just represents the task.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.enums import CallOutcome
from hotelagent.modules.ops.models import CallTask, CallTaskStatus
from hotelagent.modules.ops.schemas import CallTaskSummary

# Statuses that mean "this task is still someone's problem".
OPEN_STATUSES = (CallTaskStatus.OPEN, CallTaskStatus.CLAIMED)


def _summary(task: CallTask) -> CallTaskSummary:
    return CallTaskSummary(
        call_task_id=task.id,
        city_id=task.city_id,
        hotel_id=task.hotel_id,
        conversation_id=task.conversation_id,
        room_type_id=task.room_type_id,
        check_in=task.check_in,
        check_out=task.check_out,
        guests=task.guests,
        status=task.status,
        outcome=task.outcome,
        quoted_price=task.quoted_price,
        rooms_available=task.rooms_available,
        assigned_to=task.assigned_to,
        opened_at=task.opened_at,
        claimed_at=task.claimed_at,
        resolved_at=task.resolved_at,
    )


async def find_open_task(
    session: AsyncSession,
    *,
    hotel_id: uuid.UUID,
    check_in: date,
    check_out: date,
    conversation_id: uuid.UUID | None,
) -> CallTaskSummary | None:
    """An outstanding task asking the same question.

    Two travellers asking about the same hotel and dates within minutes should
    not produce two phone calls — the operator would ask the same question
    twice and the hotel would rightly find it odd.
    """
    task = await session.scalar(
        select(CallTask)
        .where(
            CallTask.hotel_id == hotel_id,
            CallTask.check_in == check_in,
            CallTask.check_out == check_out,
            CallTask.conversation_id == conversation_id,
            CallTask.status.in_(OPEN_STATUSES),
        )
        .order_by(CallTask.opened_at.desc())
        .limit(1)
    )
    return _summary(task) if task is not None else None


async def open_call_task(
    session: AsyncSession,
    *,
    city_id: uuid.UUID,
    hotel_id: uuid.UUID,
    check_in: date,
    check_out: date,
    guests: int,
    conversation_id: uuid.UUID | None = None,
    room_type_id: uuid.UUID | None = None,
    notes: str | None = None,
) -> uuid.UUID:
    """Put a call on the queue. Returns the task id."""
    task = CallTask(
        city_id=city_id,
        hotel_id=hotel_id,
        conversation_id=conversation_id,
        room_type_id=room_type_id,
        check_in=check_in,
        check_out=check_out,
        guests=guests,
        notes=notes,
        status=CallTaskStatus.OPEN,
        opened_at=datetime.now(UTC),
    )
    session.add(task)
    await session.flush()
    return task.id


async def get_call_task(session: AsyncSession, call_task_id: uuid.UUID) -> CallTaskSummary | None:
    task = await session.get(CallTask, call_task_id)
    return _summary(task) if task is not None else None


async def claim_call_task(session: AsyncSession, *, call_task_id: uuid.UUID, operator: str) -> bool:
    """Take ownership of a task.

    Returns False if someone already has it. Two operators must never ring the
    same hotel about the same question — the claim is what prevents it, and
    the check is done against the current row rather than the one the console
    rendered a minute ago.
    """
    task = await session.get(CallTask, call_task_id)
    if task is None or task.status is not CallTaskStatus.OPEN:
        return False

    task.status = CallTaskStatus.CLAIMED
    task.assigned_to = operator
    task.claimed_at = datetime.now(UTC)
    await session.flush()
    return True


async def record_call_outcome(
    session: AsyncSession,
    *,
    call_task_id: uuid.UUID,
    outcome: CallOutcome,
    quoted_price: Decimal | None = None,
    rooms_available: int | None = None,
    operator: str | None = None,
) -> CallTaskSummary | None:
    """Mark a task resolved with what the operator learned.

    Ops records the fact. Turning it into an availability answer is the
    availability router's job, which is why this returns the summary rather
    than acting on it.
    """
    task = await session.get(CallTask, call_task_id)
    if task is None:
        return None
    if task.status in (CallTaskStatus.RESOLVED, CallTaskStatus.CANCELLED):
        return _summary(task)

    task.status = CallTaskStatus.RESOLVED
    task.outcome = outcome
    task.quoted_price = quoted_price
    task.rooms_available = rooms_available
    task.resolved_at = datetime.now(UTC)
    if operator:
        task.assigned_to = operator
    await session.flush()
    return _summary(task)


async def list_open_tasks(
    session: AsyncSession, *, city_id: uuid.UUID, limit: int = 50
) -> list[CallTaskSummary]:
    """The queue, oldest first — the order an operator should work it."""
    tasks = (
        await session.scalars(
            select(CallTask)
            .where(CallTask.city_id == city_id, CallTask.status.in_(OPEN_STATUSES))
            .order_by(CallTask.opened_at)
            .limit(limit)
        )
    ).all()
    return [_summary(t) for t in tasks]


async def list_call_tasks(
    session: AsyncSession,
    *,
    city_id: uuid.UUID,
    limit: int,
    offset: int,
    status: CallTaskStatus | None = None,
) -> tuple[list[CallTaskSummary], int]:
    """The console's view of the queue: paginated, filterable, oldest first.

    Oldest first, and deliberately the opposite of the inbox in
    `conversation.list_conversations`. A call task is a promise already made to
    a traveller who was told five minutes (`docs/vision.md` §2.2) — newest-first
    here would mean the person who has waited longest waits longest.

    Unfiltered, `status=None` returns resolved tasks too, which is what a
    reconciliation or an audit wants. The console passes `open`, because a queue
    that accumulates every call the desk has ever made gets slower every day
    while showing the same handful of actionable rows.
    """
    scope = [CallTask.city_id == city_id]
    if status is not None:
        scope.append(CallTask.status == status)

    total = await session.scalar(select(func.count()).select_from(CallTask).where(*scope)) or 0
    tasks = (
        await session.scalars(
            select(CallTask)
            .where(*scope)
            .order_by(CallTask.opened_at.asc().nullslast(), CallTask.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return [_summary(task) for task in tasks], total
