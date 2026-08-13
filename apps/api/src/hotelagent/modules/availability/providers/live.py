"""Tier A — a live calendar we can read. Not implemented until M4.

Fails loudly for the same reason as the bot provider: a hotel set to Tier A
before the calendar exists must produce an obvious error, not a confident
guess about a room we cannot see.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.modules.availability.schemas import AvailabilityRequest, AvailabilityResult
from hotelagent.modules.inventory.schemas import HotelAvailabilityContext


async def check(
    session: AsyncSession,
    request: AvailabilityRequest,
    hotel: HotelAvailabilityContext,
) -> AvailabilityResult:
    raise NotImplementedError(
        "Tier A (live calendar) arrives at M4. "
        f"Hotel {request.hotel_id} is marked 'live' but no calendar provider exists yet."
    )
