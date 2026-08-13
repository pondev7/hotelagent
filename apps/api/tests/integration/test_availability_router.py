"""S06's exit criterion.

A check against a Tier C hotel returns PENDING and creates exactly one
CallTask. Logging the outcome resolves it and writes exactly one observation.
"""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.enums import CallOutcome, IntegrationTier
from hotelagent.modules.availability import service as availability
from hotelagent.modules.availability.models import AvailabilityObservation
from hotelagent.modules.availability.providers import bot, live, manual
from hotelagent.modules.availability.router import provider_for
from hotelagent.modules.availability.schemas import AvailabilityRequest, AvailabilityStatus
from hotelagent.modules.inventory.models import Hotel
from hotelagent.modules.ops.models import CallTask, CallTaskStatus

SATURDAY = date(2026, 8, 15)


async def _hotel(
    session: AsyncSession, city_id: uuid.UUID, tier: IntegrationTier = IntegrationTier.MANUAL
) -> uuid.UUID:
    hotel = Hotel(
        city_id=city_id,
        name="Sea Breeze Residency",
        integration_tier=tier,
        reception_phone="+919800000000",
    )
    session.add(hotel)
    await session.flush()
    return hotel.id


def _request(hotel_id: uuid.UUID, nights: int = 1) -> AvailabilityRequest:
    return AvailabilityRequest(
        hotel_id=hotel_id,
        check_in=SATURDAY,
        check_out=SATURDAY + timedelta(days=nights),
        guests=2,
    )


async def _count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_a_tier_c_check_returns_pending_and_raises_one_call_task(
    session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    """The first half of the exit criterion."""
    hotel_id = await _hotel(session, seeded_city)

    result = await availability.check_availability(session, _request(hotel_id))

    assert result.status is AvailabilityStatus.PENDING
    assert result.source_tier is IntegrationTier.MANUAL
    assert result.eta_seconds == 300, "the honest wait quote, per vision §2.2"
    assert result.call_task_id is not None

    assert await _count(session, CallTask) == 1
    task = await session.scalar(select(CallTask))
    assert task is not None
    assert task.status is CallTaskStatus.OPEN
    assert task.hotel_id == hotel_id
    assert task.check_in == SATURDAY

    assert await _count(session, AvailabilityObservation) == 0, (
        "a pending check has learned nothing yet"
    )


async def test_resolving_the_call_writes_exactly_one_observation(
    session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    """The second half. Invariant #8: the phone call becomes a datapoint."""
    hotel_id = await _hotel(session, seeded_city)
    pending = await availability.check_availability(session, _request(hotel_id))
    assert pending.call_task_id is not None

    result = await availability.resolve_manual_check(
        session,
        call_task_id=pending.call_task_id,
        outcome=CallOutcome.AVAILABLE,
        quoted_price=Decimal("2600.00"),
        rooms_available=2,
        operator="ravi",
    )

    assert result.status is AvailabilityStatus.AVAILABLE
    assert result.price == Decimal("2600.00")

    assert await _count(session, AvailabilityObservation) == 1
    observation = await session.scalar(select(AvailabilityObservation))
    assert observation is not None
    assert observation.hotel_id == hotel_id
    assert observation.stay_date == SATURDAY
    assert observation.source_tier is IntegrationTier.MANUAL, "manual calls are data too"
    assert observation.available is True
    assert observation.quoted_price == Decimal("2600.00")
    assert observation.operator_id == "ravi"
    assert observation.call_task_id == pending.call_task_id
    assert observation.city_id == seeded_city

    task = await session.scalar(select(CallTask))
    assert task is not None
    assert task.status is CallTaskStatus.RESOLVED
    assert task.resolved_at is not None


async def test_an_unavailable_answer_is_recorded_too(
    session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    """ "No rooms" is as valuable to the dataset as "yes"."""
    hotel_id = await _hotel(session, seeded_city)
    pending = await availability.check_availability(session, _request(hotel_id))
    assert pending.call_task_id is not None

    result = await availability.resolve_manual_check(
        session, call_task_id=pending.call_task_id, outcome=CallOutcome.UNAVAILABLE
    )

    assert result.status is AvailabilityStatus.UNAVAILABLE
    observation = await session.scalar(select(AvailabilityObservation))
    assert observation is not None and observation.available is False


@pytest.mark.parametrize("outcome", [CallOutcome.NO_ANSWER, CallOutcome.UNREACHABLE])
async def test_a_failed_call_is_unknown_and_writes_no_observation(
    session: AsyncSession, seeded_city: uuid.UUID, outcome: CallOutcome
) -> None:
    """ "Nobody picked up" is not a fact about occupancy.

    Recording it as unavailable would teach the M5 prediction model something
    false about a hotel that may well have been half empty.
    """
    hotel_id = await _hotel(session, seeded_city)
    pending = await availability.check_availability(session, _request(hotel_id))
    assert pending.call_task_id is not None

    result = await availability.resolve_manual_check(
        session, call_task_id=pending.call_task_id, outcome=outcome
    )

    assert result.status is AvailabilityStatus.UNKNOWN
    assert await _count(session, AvailabilityObservation) == 0

    task = await session.scalar(select(CallTask))
    assert task is not None and task.status is CallTaskStatus.RESOLVED


async def test_a_multi_night_stay_records_one_observation_per_night(
    session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    """A night is what a hotel sells, and what the prediction model needs."""
    hotel_id = await _hotel(session, seeded_city)
    pending = await availability.check_availability(session, _request(hotel_id, nights=3))
    assert pending.call_task_id is not None

    await availability.resolve_manual_check(
        session, call_task_id=pending.call_task_id, outcome=CallOutcome.AVAILABLE
    )

    dates = sorted((await session.scalars(select(AvailabilityObservation.stay_date))).all())
    assert dates == [SATURDAY, SATURDAY + timedelta(days=1), SATURDAY + timedelta(days=2)]


async def test_asking_the_same_question_twice_does_not_raise_a_second_call(
    session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    """An operator must not ring the same hotel twice about one question."""
    hotel_id = await _hotel(session, seeded_city)

    first = await availability.check_availability(session, _request(hotel_id))
    second = await availability.check_availability(session, _request(hotel_id))

    assert first.call_task_id == second.call_task_id
    assert await _count(session, CallTask) == 1


async def test_resolving_twice_does_not_double_the_dataset(
    session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    """Operators double-click, and the console will retry."""
    hotel_id = await _hotel(session, seeded_city)
    pending = await availability.check_availability(session, _request(hotel_id))
    assert pending.call_task_id is not None

    for _ in range(3):
        await availability.resolve_manual_check(
            session,
            call_task_id=pending.call_task_id,
            outcome=CallOutcome.AVAILABLE,
            quoted_price=Decimal("2600.00"),
        )

    assert await _count(session, AvailabilityObservation) == 1


async def test_an_unknown_hotel_is_refused(session: AsyncSession, seeded_city: uuid.UUID) -> None:
    with pytest.raises(availability.UnknownHotelError):
        await availability.check_availability(session, _request(uuid.uuid4()))


async def test_an_inactive_hotel_is_refused(session: AsyncSession, seeded_city: uuid.UUID) -> None:
    hotel_id = await _hotel(session, seeded_city)
    hotel = await session.get(Hotel, hotel_id)
    assert hotel is not None
    hotel.is_active = False
    await session.flush()

    with pytest.raises(availability.UnknownHotelError):
        await availability.check_availability(session, _request(hotel_id))


async def test_resolving_an_unknown_call_task_is_refused(
    session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    with pytest.raises(availability.UnknownCallTaskError):
        await availability.resolve_manual_check(
            session, call_task_id=uuid.uuid4(), outcome=CallOutcome.AVAILABLE
        )


# --- Invariant #3: the slots exist and fail loudly -------------------------


def test_every_tier_has_a_provider_slot() -> None:
    """One interface, three slots. Adding the other two later is filling in a
    stub, not restructuring the agent's core flow."""
    assert provider_for(IntegrationTier.MANUAL) is manual
    assert provider_for(IntegrationTier.BOT) is bot
    assert provider_for(IntegrationTier.LIVE) is live


async def test_the_bot_provider_fails_loudly(session: AsyncSession, seeded_city: uuid.UUID) -> None:
    """A stub that quietly returns "unknown" would let a hotel be moved to
    Tier B in the database and produce plausible wrong answers."""
    hotel_id = await _hotel(session, seeded_city, tier=IntegrationTier.BOT)

    with pytest.raises(NotImplementedError, match="M3"):
        await availability.check_availability(session, _request(hotel_id))


async def test_the_live_provider_fails_loudly(
    session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    hotel_id = await _hotel(session, seeded_city, tier=IntegrationTier.LIVE)

    with pytest.raises(NotImplementedError, match="M4"):
        await availability.check_availability(session, _request(hotel_id))
