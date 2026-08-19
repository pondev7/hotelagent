"""Public data shapes for the inventory module."""

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from hotelagent.enums import IntegrationTier
from hotelagent.modules.inventory.models import VerificationStatus


class CitySummary(BaseModel):
    """A market, as the console's city switcher shows it.

    The console needs this because every other collection requires a `city_id`
    and there is no way to guess one: ids are uuid7 values minted when a city
    row is created, so they differ between a laptop, CI and production. Baking
    one into the frontend build would make the console environment-specific,
    which is how a staging console ends up pointed at a production city.

    `timezone` travels with the city rather than being a console constant.
    Kanyakumari and Madurai share one today; the check-in time an operator reads
    off a screen must be the hotel's local time, not the browser's.
    """

    model_config = ConfigDict(frozen=True)

    city_id: uuid.UUID
    name: str
    slug: str
    timezone: str


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
