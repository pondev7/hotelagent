"""Availability tables: AvailabilityObservation.

Invariant #8: **every** availability answer is written here, regardless of tier
— including the manual phone calls. `docs/vision.md` §2.4 calls this the only
genuinely defensible asset in the business: after one season, hotel x date x
room type x available x price quoted is enough to predict availability well
enough to skip the call on high-confidence nights.

It starts accruing before anything reads it. That is the point — this dataset
cannot be backfilled.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from hotelagent.db.base import Base
from hotelagent.db.mixins import CityScopedMixin, IdMixin, TimestampMixin
from hotelagent.enums import IntegrationTier


class AvailabilityObservation(Base, IdMixin, CityScopedMixin, TimestampMixin):
    __tablename__ = "availability_observation"

    hotel_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hotel.id", ondelete="CASCADE"), nullable=False
    )
    room_type_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("room_type.id", ondelete="SET NULL")
    )

    # The night being asked about, not the day we asked.
    stay_date: Mapped[date] = mapped_column(nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Which tier produced this answer. A manual phone call is as much a
    # datapoint as a live calendar read.
    source_tier: Mapped[IntegrationTier] = mapped_column(
        Enum(
            IntegrationTier,
            name="integration_tier",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )

    available: Mapped[bool] = mapped_column(nullable=False)
    rooms_available: Mapped[int | None] = mapped_column()
    quoted_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    # Who or what produced it: an operator id at Tier C, null otherwise.
    operator_id: Mapped[str | None] = mapped_column(Text)
    call_task_id: Mapped[uuid.UUID | None] = mapped_column()

    __table_args__ = (
        CheckConstraint("quoted_price IS NULL OR quoted_price >= 0", name="quoted_price_is_valid"),
        CheckConstraint(
            "rooms_available IS NULL OR rooms_available >= 0", name="rooms_available_is_valid"
        ),
        # The query the prediction model will run: this hotel, these nights.
        Index("ix_availability_observation_hotel_id_stay_date", "hotel_id", "stay_date"),
    )
