"""Tier B — the hotelier WhatsApp bot. Not implemented until M3.

The slot exists now, and that is the entire point of invariant #3. When M3
ships the hotelier bot, this file gains a body: send a structured prompt with
Yes/No buttons, return PENDING with a shorter ETA, resolve on the reply. The
router, the agent flow, the observation writing and the conversation states
all stay exactly as they are.

It raises rather than quietly returning UNKNOWN. A stub that fails silently is
worse than no stub: it would let a hotel be moved to Tier B in the database and
produce plausible wrong answers instead of an obvious error.
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
        "Tier B (hotelier bot) arrives at M3. "
        f"Hotel {request.hotel_id} is marked 'bot' but no bot provider exists yet."
    )
