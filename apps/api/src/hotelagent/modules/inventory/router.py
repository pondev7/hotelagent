"""The hotel directory, over HTTP.

Thin by rule: parse, call `service.py`, serialise. Every handler here is three
lines, and that is the target rather than an accident — there is no `try`, no
status code and no query in this file. A service raises `UnknownHotelError`;
`errors.py` decides that means 404, once, for every endpoint in the system.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.api.pagination import Page, page_of
from hotelagent.api.params import DEFAULT_PAGE_SIZE, CityId, Limit, Offset
from hotelagent.db.session import get_session
from hotelagent.enums import IntegrationTier
from hotelagent.errors import ERROR_RESPONSES
from hotelagent.modules.inventory import service
from hotelagent.modules.inventory.schemas import CitySummary, HotelSummary

router = APIRouter(prefix="/api/hotels", tags=["hotels"], responses=ERROR_RESPONSES)


@router.get("")
async def list_hotels(
    session: Annotated[AsyncSession, Depends(get_session)],
    city_id: CityId,
    tier: Annotated[
        IntegrationTier | None, Query(description="Filter by integration tier.")
    ] = None,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> Page[HotelSummary]:
    """The directory for one city, optionally narrowed to one tier."""
    hotels, total = await service.list_hotels(
        session, city_id=city_id, tier=tier, limit=limit, offset=offset
    )
    return page_of(hotels, total=total, limit=limit, offset=offset)


@router.get("/{hotel_id}")
async def get_hotel(
    session: Annotated[AsyncSession, Depends(get_session)],
    hotel_id: uuid.UUID,
    city_id: CityId,
) -> HotelSummary:
    """One hotel, scoped to the asking city."""
    return await service.get_hotel(session, hotel_id=hotel_id, city_id=city_id)


# A second router rather than a second app: cities and hotels are both inventory,
# and splitting a module across two files of wiring buys nothing. It is separate
# only because the prefix differs.
#
# Note what it does *not* have: a `city_id` parameter. This is the tenancy root,
# and the only endpoint in the system for which that is true — see
# `service.list_cities` and `tests/unit/test_openapi_contract.py`.
cities_router = APIRouter(prefix="/api/cities", tags=["cities"], responses=ERROR_RESPONSES)


@cities_router.get("")
async def list_cities(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CitySummary]:
    """Every city an operator may be scoped to.

    Returns a bare list, not a `Page`. Every other collection paginates, and
    this one deliberately does not: there is nothing here to page through, and
    staying out of the page envelope keeps this endpoint outside the check that
    every paginated collection is city-scoped — which it cannot be.
    """
    return await service.list_cities(session)
