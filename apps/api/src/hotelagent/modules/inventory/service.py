"""Public surface of the inventory module.

Other modules call these functions and nothing else. In particular, nobody
outside this module imports `models.py` — cross-module data leaves here as
Pydantic schemas or plain values, never as ORM instances.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.enums import IntegrationTier
from hotelagent.errors import NotFoundError
from hotelagent.modules.inventory.models import City, Hotel
from hotelagent.modules.inventory.schemas import (
    CitySummary,
    HotelAvailabilityContext,
    HotelSummary,
)


class UnknownHotelError(NotFoundError):
    """Raised when asked about a hotel that does not exist or is inactive.

    Lives here rather than in `availability`, which is where it was first
    written: inventory owns hotels, so it owns the meaning of "there is no such
    hotel". `availability` imports it, which is also why the code is
    `unknown_hotel` and not the inherited `not_found` — the console can
    distinguish this from a missing conversation or a missing call task.
    """

    code = "unknown_hotel"


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


async def list_cities(session: AsyncSession) -> list[CitySummary]:
    """Every city an operator may be scoped to.

    The one collection in the API that takes no `city_id`, because it is the
    tenancy root — asking "which cities exist, in city X?" is circular. That
    makes it the natural place for the scoping rule to be accidentally widened
    later, so `tests/unit/test_openapi_contract.py` asserts the exception
    explicitly rather than leaving it to be noticed.

    Unpaginated for the same reason it is unscoped: this is a bounded set. One
    row today and a handful ever, ordered by name so the switcher does not
    reshuffle itself as cities are added.
    """
    cities = (
        await session.scalars(select(City).where(City.is_active).order_by(City.name, City.id))
    ).all()

    return [
        CitySummary(city_id=city.id, name=city.name, slug=city.slug, timezone=city.timezone)
        for city in cities
    ]


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


def _summary(hotel: Hotel) -> HotelSummary:
    return HotelSummary(
        hotel_id=hotel.id,
        city_id=hotel.city_id,
        name=hotel.name,
        address=hotel.address,
        reception_phone=hotel.reception_phone,
        integration_tier=hotel.integration_tier,
        verification_status=hotel.verification_status,
        commission_rate=hotel.commission_rate,
        is_active=hotel.is_active,
    )


async def list_hotels(
    session: AsyncSession,
    *,
    city_id: uuid.UUID,
    tier: IntegrationTier | None = None,
    limit: int,
    offset: int,
) -> tuple[list[HotelSummary], int]:
    """The directory for one city, and the count of rows behind it.

    Ordered by name because this screen is read by a human looking for a hotel
    they can already name. Ordering by `created_at` would be marginally cheaper
    and would reshuffle the list every time a hotel is signed.

    `city_id` is a parameter and not a default: every caller must say which city
    it means (invariant #1), and there is no code path that can forget to.

    `tier` filters in SQL, and both predicates are applied to the count as well
    as to the page. Filtering in the console instead would hide rows from the
    current page while still reporting the unfiltered `total` — a bug that is
    invisible in a five-hotel city and obvious in a fifty-hotel one.
    """
    predicates = [Hotel.city_id == city_id]
    if tier is not None:
        predicates.append(Hotel.integration_tier == tier)

    total = await session.scalar(select(func.count()).select_from(Hotel).where(*predicates)) or 0
    hotels = (
        await session.scalars(
            select(Hotel)
            .where(*predicates)
            .order_by(Hotel.name, Hotel.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return [_summary(hotel) for hotel in hotels], total


async def get_hotel(
    session: AsyncSession, *, hotel_id: uuid.UUID, city_id: uuid.UUID
) -> HotelSummary:
    """One hotel, if it belongs to the asking city.

    A hotel in another city raises `UnknownHotelError` — the same error as one
    that does not exist at all. That is not laziness: answering "forbidden"
    would confirm the row exists, and an operator in Kanyakumari must learn
    nothing whatsoever about Madurai's directory from a guessed UUID.
    """
    hotel = await session.get(Hotel, hotel_id)
    if hotel is None or hotel.city_id != city_id:
        raise UnknownHotelError(f"hotel {hotel_id} is not in city {city_id}")
    return _summary(hotel)
