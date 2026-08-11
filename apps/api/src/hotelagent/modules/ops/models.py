"""Ops tables: CallTask.

The Tier C loop made concrete. An operator picks up a task, telephones the
hotel, and logs the answer — and the speed of that round trip *is* our gross
margin at Tier C (`docs/vision.md` §3.5).
"""

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from hotelagent.db.base import Base
from hotelagent.db.mixins import CityScopedMixin, IdMixin, TimestampMixin


class CallTaskStatus(enum.StrEnum):
    OPEN = "open"
    CLAIMED = "claimed"  # an operator has it; nobody else should call the same hotel
    RESOLVED = "resolved"
    CANCELLED = "cancelled"  # the traveller went quiet or chose elsewhere
    EXPIRED = "expired"


class CallTaskOutcome(enum.StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NO_ANSWER = "no_answer"
    UNREACHABLE = "unreachable"


class CallTask(Base, IdMixin, CityScopedMixin, TimestampMixin):
    __tablename__ = "call_task"

    hotel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hotel.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversation.id", ondelete="SET NULL")
    )
    room_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("room_type.id", ondelete="SET NULL")
    )

    # What to ask. Held as columns rather than prose so the console can render a
    # script and the operator never has to compose the question.
    check_in: Mapped[date] = mapped_column(nullable=False)
    check_out: Mapped[date] = mapped_column(nullable=False)
    guests: Mapped[int] = mapped_column(nullable=False, default=2)
    notes: Mapped[str | None] = mapped_column(Text)

    status: Mapped[CallTaskStatus] = mapped_column(
        Enum(
            CallTaskStatus,
            name="call_task_status",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=CallTaskStatus.OPEN,
    )
    outcome: Mapped[CallTaskOutcome | None] = mapped_column(
        Enum(
            CallTaskOutcome,
            name="call_task_outcome",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        )
    )
    quoted_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    rooms_available: Mapped[int | None] = mapped_column()

    assigned_to: Mapped[str | None] = mapped_column(String(120))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # The queue view: open tasks in this city, oldest first.
        Index("ix_call_task_city_id_status_opened_at", "city_id", "status", "opened_at"),
    )
