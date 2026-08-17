"""The hotel directory, over HTTP.

Thin by rule: parse, call `service.py`, serialise. Every handler here is three
lines, and that is the target rather than an accident — there is no `try`, no
status code and no query in this file. A service raises `UnknownHotelError`;
`errors.py` decides that means 404, once, for every endpoint in the system.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.api.pagination import Page, page_of
from hotelagent.api.params import DEFAULT_PAGE_SIZE, CityId, Limit, Offset
from hotelagent.db.session import get_session
from hotelagent.errors import ERROR_RESPONSES
from hotelagent.modules.inventory import service
from hotelagent.modules.inventory.schemas import HotelSummary

router = APIRouter(prefix="/api/hotels", tags=["hotels"], responses=ERROR_RESPONSES)


@router.get("")
async def list_hotels(
    session: Annotated[AsyncSession, Depends(get_session)],
    city_id: CityId,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> Page[HotelSummary]:
    """The directory for one city."""
    hotels, total = await service.list_hotels(session, city_id=city_id, limit=limit, offset=offset)
    return page_of(hotels, total=total, limit=limit, offset=offset)


@router.get("/{hotel_id}")
async def get_hotel(
    session: Annotated[AsyncSession, Depends(get_session)],
    hotel_id: uuid.UUID,
    city_id: CityId,
) -> HotelSummary:
    """One hotel, scoped to the asking city."""
    return await service.get_hotel(session, hotel_id=hotel_id, city_id=city_id)
