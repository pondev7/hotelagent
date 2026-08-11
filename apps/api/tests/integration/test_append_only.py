"""Invariant #6: the event log is append-only, and that is enforced."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.enums import Channel
from hotelagent.events import AppendOnlyError
from hotelagent.modules.booking.models import (
    Booking,
    BookingEvent,
    BookingEventType,
    BookingStatus,
)
from hotelagent.modules.conversation.models import User
from hotelagent.modules.inventory.models import City, Hotel


async def _booking_with_event(session: AsyncSession) -> tuple[Booking, BookingEvent]:
    city = City(name="Kanyakumari", slug=f"kk-{uuid.uuid4().hex[:6]}")
    session.add(city)
    await session.flush()

    hotel = Hotel(city_id=city.id, name="Sea Breeze Residency")
    user = User(external_id=f"wa-{uuid.uuid4().hex[:8]}", channel=Channel.WHATSAPP)
    session.add_all([hotel, user])
    await session.flush()

    today = datetime.now(UTC).date()
    booking = Booking(
        city_id=city.id,
        hotel_id=hotel.id,
        user_id=user.id,
        reference=f"KK-{uuid.uuid4().hex[:6].upper()}",
        check_in=today,
        check_out=today + timedelta(days=1),
        guests=2,
        amount=Decimal("2600.00"),
        commission_rate=Decimal("15.00"),
        commission_amount=Decimal("390.00"),
        status=BookingStatus.HELD,
    )
    session.add(booking)
    await session.flush()

    event = BookingEvent(
        city_id=city.id,
        booking_id=booking.id,
        event_type=BookingEventType.CREATED,
        payload={"source": "test"},
        actor="system",
        occurred_at=datetime.now(UTC),
    )
    session.add(event)
    await session.flush()
    return booking, event


async def test_events_can_be_written(session: AsyncSession) -> None:
    _, event = await _booking_with_event(session)
    assert event.id is not None


async def test_an_event_cannot_be_updated(session: AsyncSession) -> None:
    _, event = await _booking_with_event(session)

    event.actor = "someone-else"

    with pytest.raises(AppendOnlyError, match="cannot be updated"):
        await session.flush()


async def test_an_event_cannot_be_deleted(session: AsyncSession) -> None:
    _, event = await _booking_with_event(session)

    await session.delete(event)

    with pytest.raises(AppendOnlyError, match="cannot be deleted"):
        await session.flush()


async def test_the_mutable_booking_row_is_still_mutable(session: AsyncSession) -> None:
    """Only the log is frozen. The booking's own status column is meant to
    change — the pair is the point (invariant #6)."""
    booking, _ = await _booking_with_event(session)

    booking.status = BookingStatus.CONFIRMED
    await session.flush()

    assert booking.status is BookingStatus.CONFIRMED
