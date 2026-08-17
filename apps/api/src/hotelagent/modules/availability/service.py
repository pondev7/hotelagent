"""Public surface of the availability module.

Two responsibilities:

1. **Answer "is there a room?"** through whichever provider the hotel's tier
   selects, without the caller knowing which.
2. **Write down every answer**, whatever its source — invariant #8, and the
   only genuinely defensible asset in the business (`docs/vision.md` §2.4).

On the dependency direction: this module calls `ops` to raise and resolve call
tasks. `ops` does not call back. Ops owns the *work* — which hotel to ring, who
has it — while the meaning of the answer belongs here, so the resolution path
lives here too. One direction only, and no cycle.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.enums import CallOutcome, IntegrationTier
from hotelagent.errors import NotFoundError
from hotelagent.logging import get_logger
from hotelagent.modules.availability.models import AvailabilityObservation
from hotelagent.modules.availability.router import provider_for
from hotelagent.modules.availability.schemas import (
    AvailabilityRequest,
    AvailabilityResult,
    AvailabilityStatus,
)
from hotelagent.modules.inventory import service as inventory_service

# Imported, not redefined. Inventory owns hotels, so it owns the meaning of
# "there is no such hotel"; this module raises it, which is a normal thing to do
# with another module's public error and the reason `errors.py` is shared.
from hotelagent.modules.inventory.service import UnknownHotelError as UnknownHotelError
from hotelagent.modules.ops import service as ops_service

log = get_logger(__name__)

# How a call outcome becomes an availability answer. NO_ANSWER and UNREACHABLE
# map to UNKNOWN rather than UNAVAILABLE: "we could not ask" is not "there is
# no room", and recording it as the latter would teach the M5 prediction model
# something false about a hotel that may have been half empty.
_OUTCOME_TO_STATUS: dict[CallOutcome, AvailabilityStatus] = {
    CallOutcome.AVAILABLE: AvailabilityStatus.AVAILABLE,
    CallOutcome.UNAVAILABLE: AvailabilityStatus.UNAVAILABLE,
    CallOutcome.NO_ANSWER: AvailabilityStatus.UNKNOWN,
    CallOutcome.UNREACHABLE: AvailabilityStatus.UNKNOWN,
}


class UnknownCallTaskError(NotFoundError):
    """Raised when resolving a call task that does not exist."""

    code = "unknown_call_task"


async def check_availability(
    session: AsyncSession, request: AvailabilityRequest
) -> AvailabilityResult:
    """Ask whether a room is free, by whatever means this hotel supports.

    The caller gets the same shape whichever tier answered. Only `eta_seconds`
    and `status` differ, and those are exactly what the wait message needs.
    """
    hotel = await inventory_service.get_hotel_for_availability(session, request.hotel_id)
    if hotel is None or not hotel.is_active:
        raise UnknownHotelError(f"hotel {request.hotel_id} is unknown or inactive")

    provider = provider_for(hotel.integration_tier)
    result = await provider.check(session, request, hotel)

    # A provider that answered immediately has produced an observation-worthy
    # fact. A PENDING one has not yet — its observation is written when the
    # call, or the bot, comes back.
    if result.status in (AvailabilityStatus.AVAILABLE, AvailabilityStatus.UNAVAILABLE):
        await record_observations(
            session,
            request=request,
            city_id=hotel.city_id,
            source_tier=result.source_tier,
            available=result.status is AvailabilityStatus.AVAILABLE,
            quoted_price=result.price,
            rooms_available=result.rooms_available,
        )

    return result


async def record_observations(
    session: AsyncSession,
    *,
    request: AvailabilityRequest,
    city_id: uuid.UUID,
    source_tier: IntegrationTier,
    available: bool,
    quoted_price: Decimal | None = None,
    rooms_available: int | None = None,
    operator_id: str | None = None,
    call_task_id: uuid.UUID | None = None,
) -> int:
    """Invariant #8 — write the answer down, whatever produced it.

    One row per **night**, because a night is what a hotel sells and what the
    M5 prediction model will need to reason about. A Saturday-to-Monday stay
    confirmed as available tells us both Saturday and Sunday were free.

    This runs for manual phone calls exactly as it does for a live calendar
    read. The phone calls are the whole point: after one season, hotel × date ×
    room type × available × price is enough to skip the call on high-confidence
    nights, and that dataset cannot be backfilled.
    """
    observed_at = datetime.now(UTC)
    nights = request.nights
    for night in nights:
        session.add(
            AvailabilityObservation(
                city_id=city_id,
                hotel_id=request.hotel_id,
                room_type_id=request.room_type_id,
                stay_date=night,
                observed_at=observed_at,
                source_tier=source_tier,
                available=available,
                rooms_available=rooms_available,
                quoted_price=quoted_price,
                operator_id=operator_id,
                call_task_id=call_task_id,
            )
        )
    await session.flush()

    log.info(
        "availability.observed",
        hotel_id=str(request.hotel_id),
        city_id=str(city_id),
        source_tier=source_tier.value,
        available=available,
        nights=len(nights),
    )
    return len(nights)


async def resolve_manual_check(
    session: AsyncSession,
    *,
    call_task_id: uuid.UUID,
    outcome: CallOutcome,
    quoted_price: Decimal | None = None,
    rooms_available: int | None = None,
    operator: str | None = None,
) -> AvailabilityResult:
    """An operator has rung the hotel. Close the loop.

    Three things happen together, in one transaction: the task is marked
    resolved, the observation is written, and the answer is returned for the
    conversation that was waiting. Splitting them across callers is how you end
    up with resolved tasks that produced no dataset row.
    """
    task = await ops_service.get_call_task(session, call_task_id)
    if task is None:
        raise UnknownCallTaskError(f"call task {call_task_id} does not exist")

    already_resolved = task.resolved_at is not None
    updated = await ops_service.record_call_outcome(
        session,
        call_task_id=call_task_id,
        outcome=outcome,
        quoted_price=quoted_price,
        rooms_available=rooms_available,
        operator=operator,
    )
    assert updated is not None  # get_call_task above proved it exists

    status = _OUTCOME_TO_STATUS[outcome]
    request = AvailabilityRequest(
        hotel_id=task.hotel_id,
        check_in=task.check_in,
        check_out=task.check_out,
        guests=task.guests,
        room_type_id=task.room_type_id,
        conversation_id=task.conversation_id,
    )

    # Only a real answer is worth recording. "Nobody picked up" is not a fact
    # about the hotel's occupancy, and writing it as one would corrupt the
    # dataset with our own operational failures.
    if not already_resolved and status in (
        AvailabilityStatus.AVAILABLE,
        AvailabilityStatus.UNAVAILABLE,
    ):
        await record_observations(
            session,
            request=request,
            city_id=task.city_id,
            source_tier=IntegrationTier.MANUAL,
            available=status is AvailabilityStatus.AVAILABLE,
            quoted_price=quoted_price,
            rooms_available=rooms_available,
            operator_id=operator,
            call_task_id=call_task_id,
        )

    return AvailabilityResult(
        status=status,
        source_tier=IntegrationTier.MANUAL,
        price=quoted_price,
        rooms_available=rooms_available,
        call_task_id=call_task_id,
    )


async def count_observations(session: AsyncSession, *, hotel_id: uuid.UUID) -> int:
    """Size of the dataset for one hotel. The moat, measured."""
    total: int | None = await session.scalar(
        select(func.count())
        .select_from(AvailabilityObservation)
        .where(AvailabilityObservation.hotel_id == hotel_id)
    )
    return total or 0
