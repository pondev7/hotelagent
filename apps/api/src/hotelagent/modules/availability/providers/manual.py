"""Tier C — an operator telephones reception.

The provider that runs the business today. `docs/vision.md` §1.5 found a
competitor sustaining paid Google Ads on exactly this, with no technology at
all, which is the strongest demand signal available and cost nothing to obtain.

It returns PENDING and puts a call on the queue. It does not wait — a phone
call takes minutes, and blocking a conversation for minutes would make the
whole system serial.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.enums import IntegrationTier
from hotelagent.logging import get_logger
from hotelagent.modules.availability.schemas import (
    AvailabilityRequest,
    AvailabilityResult,
    AvailabilityStatus,
)
from hotelagent.modules.inventory.schemas import HotelAvailabilityContext
from hotelagent.modules.ops import service as ops_service

log = get_logger(__name__)

# The honest quote. `docs/vision.md` §2.2 commits to confirming Tier C
# availability in under five minutes, and §4.1 insists the wait message be
# truthful — never fake instant availability we do not have.
ETA_SECONDS = 300


async def check(
    session: AsyncSession,
    request: AvailabilityRequest,
    hotel: HotelAvailabilityContext,
) -> AvailabilityResult:
    existing = await ops_service.find_open_task(
        session,
        hotel_id=request.hotel_id,
        check_in=request.check_in,
        check_out=request.check_out,
        conversation_id=request.conversation_id,
    )
    if existing is not None:
        # Someone is already asking this exact question. Reuse it rather than
        # making an operator ring the same hotel twice.
        return _pending(existing.call_task_id)

    call_task_id = await ops_service.open_call_task(
        session,
        city_id=hotel.city_id,
        hotel_id=request.hotel_id,
        check_in=request.check_in,
        check_out=request.check_out,
        guests=request.guests,
        conversation_id=request.conversation_id,
        room_type_id=request.room_type_id,
    )
    log.info(
        "availability.manual.call_raised",
        hotel_id=str(request.hotel_id),
        city_id=str(hotel.city_id),
        call_task_id=str(call_task_id),
        nights=len(request.nights),
    )
    return _pending(call_task_id)


def _pending(call_task_id: uuid.UUID) -> AvailabilityResult:
    return AvailabilityResult(
        status=AvailabilityStatus.PENDING,
        source_tier=IntegrationTier.MANUAL,
        eta_seconds=ETA_SECONDS,
        call_task_id=call_task_id,
        detail="checking with the hotel",
    )
