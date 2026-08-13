"""Public data shapes for the availability module.

The router's whole promise is in `AvailabilityResult`: **callers cannot tell
which tier answered.** The agent's conversation flow is identical whether a
calendar was read in 40 milliseconds or an operator is about to pick up a
phone — only the wait message differs (`docs/vision.md` §3.4).
"""

import enum
import uuid
from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from hotelagent.enums import IntegrationTier


class AvailabilityStatus(enum.StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    PENDING = "pending"
    """We have asked, and do not know yet. Tier B and Tier C always start here."""
    UNKNOWN = "unknown"
    """We could not ask at all — nobody answered the phone, the hotel is
    inactive. Deliberately distinct from UNAVAILABLE: "we could not find out"
    is not the same fact as "there is no room", and conflating the two would
    teach the M5 prediction model something false."""


class AvailabilityRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    hotel_id: uuid.UUID
    check_in: date
    check_out: date
    guests: int = 2
    room_type_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None

    @property
    def nights(self) -> list[date]:
        """Every night the stay covers.

        A stay from Saturday to Sunday is one night, not two dates. The
        dataset records nights, because a night is what a hotel sells.
        """
        span = (self.check_out - self.check_in).days
        return [self.check_in + timedelta(days=n) for n in range(span)]


class AvailabilityResult(BaseModel):
    """What the router returns, whatever answered."""

    model_config = ConfigDict(frozen=True)

    status: AvailabilityStatus
    source_tier: IntegrationTier
    price: Decimal | None = None
    rooms_available: int | None = None

    eta_seconds: int | None = None
    """How long until we expect to know. Powers the honest wait message —
    "Checking with the hotel — about 2 minutes" — which `docs/vision.md` §4.1
    insists on: never fake instant availability we do not have."""

    call_task_id: uuid.UUID | None = None
    """Set when a human was asked, so the resolution can find its way back."""

    detail: str | None = None
