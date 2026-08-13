"""Public data shapes for the inventory module."""

import uuid

from pydantic import BaseModel, ConfigDict

from hotelagent.enums import IntegrationTier


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
