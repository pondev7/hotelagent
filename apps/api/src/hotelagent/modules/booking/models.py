"""Booking tables: Booking and BookingEvent.

`Booking` is the mutable current state. `BookingEvent` is the append-only
history (invariant #6). Both exist deliberately: the status column answers
"where is this booking now?", and only the event log answers "how did it get
here, and who did what, when?" — which is what a dispute, an audit or an
analytics question actually needs.
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hotelagent.db.base import Base
from hotelagent.db.mixins import CityScopedMixin, IdMixin, TimestampMixin
from hotelagent.events.append_only import AppendOnlyMixin


class BookingStatus(enum.StrEnum):
    HELD = "held"  # soft hold, not yet paid (M4)
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    EXPIRED = "expired"


class BookingEventType(enum.StrEnum):
    CREATED = "created"
    HELD = "held"
    HOLD_EXPIRED = "hold_expired"
    PAYMENT_INITIATED = "payment_initiated"
    PAYMENT_RECEIVED = "payment_received"
    CONFIRMED = "confirmed"
    MODIFIED = "modified"
    CANCELLED = "cancelled"
    CHECKED_IN = "checked_in"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    REFUNDED = "refunded"


class Booking(Base, IdMixin, CityScopedMixin, TimestampMixin):
    __tablename__ = "booking"

    hotel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hotel.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    room_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("room_type.id", ondelete="SET NULL")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversation.id", ondelete="SET NULL")
    )

    # Human-facing reference, e.g. KK-4821. Unique so it can be quoted in chat
    # and searched in the console.
    reference: Mapped[str] = mapped_column(String(32), nullable=False)

    check_in: Mapped[date] = mapped_column(nullable=False)
    check_out: Mapped[date] = mapped_column(nullable=False)
    guests: Mapped[int] = mapped_column(nullable=False, default=2)

    # Money, all Numeric(12, 2), all INR. commission_rate is copied onto the
    # booking rather than read from the hotel: a rate change must never rewrite
    # the economics of bookings already taken.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    commission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    commission_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    status: Mapped[BookingStatus] = mapped_column(
        Enum(
            BookingStatus,
            name="booking_status",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=BookingStatus.HELD,
    )
    payment_ref: Mapped[str | None] = mapped_column(String(128))

    __table_args__ = (
        UniqueConstraint("reference", name="uq_booking_reference"),
        CheckConstraint("check_out > check_in", name="stay_is_at_least_one_night"),
        CheckConstraint("guests > 0", name="guests_is_positive"),
        CheckConstraint("amount >= 0", name="amount_is_not_negative"),
        CheckConstraint(
            "commission_amount >= 0 AND commission_amount <= amount",
            name="commission_is_within_amount",
        ),
        Index("ix_booking_city_id_status", "city_id", "status"),
    )


class BookingEvent(Base, IdMixin, CityScopedMixin, AppendOnlyMixin):
    """Append-only. One row per state change, never updated, never deleted.

    No `TimestampMixin`: an event has one time, `occurred_at`. An `updated_at`
    on an immutable row would be a contradiction.
    """

    __tablename__ = "booking_event"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("booking.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[BookingEventType] = mapped_column(
        Enum(
            BookingEventType,
            name="booking_event_type",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)

    # Who caused it: an operator id, "agent", or "system".
    actor: Mapped[str | None] = mapped_column(String(120))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_booking_event_booking_id_occurred_at", "booking_id", "occurred_at"),
    )
