"""Public surface of the inventory module.

Other modules call these functions and nothing else. In particular, nobody
outside this module imports `models.py` — cross-module data leaves here as
Pydantic schemas or plain values, never as ORM instances.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.modules.inventory.models import City, Hotel
from hotelagent.modules.inventory.schemas import HotelAvailabilityContext


async def get_city_id_by_slug(session: AsyncSession, slug: str) -> uuid.UUID | None:
    """Resolve a city slug to its id.

    The channel gateway needs a `city_id` for every conversation (invariant #1)
    and must not reach into inventory's tables to get one. This function is
    that boundary.
    """
    # Assigned to a typed name rather than returned directly: session.scalar()
    # is typed as returning Any, and mypy's --strict rejects returning Any from
    # a function that declares a concrete type.
    city_id: uuid.UUID | None = await session.scalar(
        select(City.id).where(City.slug == slug, City.is_active)
    )
    return city_id


async def get_hotel_for_availability(
    session: AsyncSession, hotel_id: uuid.UUID
) -> HotelAvailabilityContext | None:
    """The narrow view of a hotel that the availability router needs.

    Returns a Pydantic schema, never the ORM object — the router must not be
    able to reach the rest of the hotel record, let alone mutate it.
    """
    hotel = await session.get(Hotel, hotel_id)
    if hotel is None:
        return None
    return HotelAvailabilityContext(
        hotel_id=hotel.id,
        city_id=hotel.city_id,
        name=hotel.name,
        integration_tier=hotel.integration_tier,
        reception_phone=hotel.reception_phone,
        is_active=hotel.is_active,
    )
