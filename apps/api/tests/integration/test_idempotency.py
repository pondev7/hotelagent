"""Invariant #5, as tests.

The exit criterion for this slice: calling the same mutation twice with one key
produces exactly one row.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.db.idempotency import IdempotencyKey, run_once
from hotelagent.modules.inventory.models import City


async def _make_city(session: AsyncSession, name: str) -> uuid.UUID:
    city = City(name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}")
    session.add(city)
    await session.flush()
    return city.id


async def test_first_call_runs_the_operation(session: AsyncSession) -> None:
    calls = 0

    async def operation() -> uuid.UUID:
        nonlocal calls
        calls += 1
        return await _make_city(session, "Kanyakumari")

    result = await run_once(
        session, scope="test", key="k-1", operation=operation, resource_type="city"
    )

    assert calls == 1
    assert result.is_replay is False
    assert result.resource_id is not None


async def test_replay_does_not_run_the_operation_again(session: AsyncSession) -> None:
    """The webhook-redelivery case. WhatsApp resends; we must not double-write."""
    calls = 0

    async def operation() -> uuid.UUID:
        nonlocal calls
        calls += 1
        return await _make_city(session, "Rameswaram")

    first = await run_once(session, scope="webhook", key="wamid.ABC", operation=operation)
    second = await run_once(session, scope="webhook", key="wamid.ABC", operation=operation)

    assert calls == 1, "the operation ran twice for one key"
    assert first.is_replay is False
    assert second.is_replay is True
    assert second.resource_id == first.resource_id

    # The actual exit criterion: one key, one row.
    cities = await session.scalar(select(func.count()).select_from(City))
    assert cities == 1


async def test_scope_namespaces_the_key(session: AsyncSession) -> None:
    """A WhatsApp message id and a payment gateway event id may be the same
    string. Scope is what stops them colliding."""

    async def make_a() -> uuid.UUID:
        return await _make_city(session, "Alpha")

    async def make_b() -> uuid.UUID:
        return await _make_city(session, "Beta")

    first = await run_once(session, scope="webhook", key="shared-id", operation=make_a)
    second = await run_once(session, scope="payment", key="shared-id", operation=make_b)

    assert first.is_replay is False
    assert second.is_replay is False
    assert first.resource_id != second.resource_id

    cities = await session.scalar(select(func.count()).select_from(City))
    assert cities == 2


async def test_a_failed_operation_does_not_poison_the_key(session: AsyncSession) -> None:
    """If the work fails, the claim must roll back with it — otherwise a
    transient error would permanently block a legitimate retry."""

    async def failing() -> uuid.UUID:
        raise RuntimeError("gateway timeout")

    try:
        await run_once(session, scope="payment", key="retry-me", operation=failing)
    except RuntimeError:
        await session.rollback()

    keys = await session.scalar(select(func.count()).select_from(IdempotencyKey))
    assert keys == 0

    async def succeeding() -> uuid.UUID:
        return await _make_city(session, "Retried")

    result = await run_once(session, scope="payment", key="retry-me", operation=succeeding)
    assert result.is_replay is False
