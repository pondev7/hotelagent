"""Public data shapes for the inventory module."""

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from hotelagent.enums import IntegrationTier
from hotelagent.modules.inventory.models import VerificationStatus


class HotelAvailabilityContext(BaseModel):
    """What the availability router needs to know about a hotel.

    Deliberately narrow. The router needs the tier to choose a provider and the
    reception number for the operator to ring — not the whole hotel record. A
    schema that returns everything is a schema that couples everything.
    """

    model_config = ConfigDict(frozen=True)

    hotel_id: uuid.UUID
    city_id: uuid.UUID
    name: str
    integration_tier: IntegrationTier
    reception_phone: str | None = None
    is_active: bool = True


class HotelSummary(BaseModel):
    """A hotel as the ops console's directory shows it.

    A second schema over the same table, and worth the duplication: the two
    consumers want genuinely different things. `HotelAvailabilityContext` is
    narrowed to what the availability router may see, while the directory is a
    human-facing screen that needs the commission rate and the verification
    state to be useful. Widening the first to serve the second would hand the
    availability router the whole hotel record it was deliberately denied.
    """

    model_config = ConfigDict(frozen=True)

    hotel_id: uuid.UUID
    city_id: uuid.UUID
    name: str
    address: str | None = None
    reception_phone: str | None = None
    integration_tier: IntegrationTier
    verification_status: VerificationStatus
    commission_rate: Decimal
    is_active: bool = True
