"""The contract every availability provider satisfies.

Invariant #3: *"The availability router exists at M1, with only the manual
provider implemented. One interface, three provider slots."*

The reason this matters more than it looks: the agent's conversation flow is
identical in all three cases. Retrofitting a router around hardcoded calendar
reads later is a rewrite of the agent's core flow, whereas filling in a stub
is an afternoon. The seam costs days now and months later — which is the whole
organising principle of `docs/milestones.md`.
"""

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.modules.availability.schemas import AvailabilityRequest, AvailabilityResult
from hotelagent.modules.inventory.schemas import HotelAvailabilityContext


class AvailabilityProvider(Protocol):
    """A way of finding out whether a room is free.

    Structural, like `ChannelAdapter` in S05 — providers are modules, and a
    module with the right functions satisfies this without inheriting or
    registering anything.
    """

    async def check(
        self,
        session: AsyncSession,
        request: AvailabilityRequest,
        hotel: HotelAvailabilityContext,
    ) -> AvailabilityResult:
        """Answer, or start the process of answering.

        May return `PENDING` — that is the point. A provider that must block
        until it knows would force the whole conversation to block with it,
        and a phone call takes minutes.
        """
        ...
