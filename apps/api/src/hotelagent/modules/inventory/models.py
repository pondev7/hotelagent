"""Inventory tables: City and Hotel.

These are ORM models, and per the module boundary rule they are **private to
this module**. No other module may import them; cross-module data crosses as
Pydantic schemas returned from `service.py`.
"""

import enum
from decimal import Decimal

from sqlalchemy import CheckConstraint, Enum, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hotelagent.db.base import Base
from hotelagent.db.mixins import CityScopedMixin, IdMixin, TimestampMixin


class IntegrationTier(enum.StrEnum):
    """How we learn whether a room is free (`docs/vision.md` §2.4).

    Every hotel launches at MANUAL. Commission is the incentive to climb, and
    our cost falls exactly where our margin improves.
    """

    LIVE = "live"  # Tier A — calendar in our dashboard or a PMS. Instant, 11%.
    BOT = "bot"  # Tier B — hotelier WhatsApp bot. 1-3 min, 13%.
    MANUAL = "manual"  # Tier C — an operator telephones reception. 5-15 min, 15%.


class VerificationStatus(enum.StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class City(Base, IdMixin, TimestampMixin):
    """A market. City is the tenancy root, so it carries no `city_id` itself."""

    __tablename__ = "city"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    state: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, default="IN")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")

    # Language packs and city quirks are data, not code — adding a city must
    # never require a deployment (`docs/milestones.md` M6).
    active_languages: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=lambda: ["en"]
    )
    config: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)


class Hotel(Base, IdMixin, CityScopedMixin, TimestampMixin):
    __tablename__ = "hotel"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    # The number an operator actually rings at Tier C. This single column is
    # the entire "integration" for a Tier C hotel.
    reception_phone: Mapped[str | None] = mapped_column(String(32))

    # values_callable matters: by default SQLAlchemy stores an enum's *names*
    # ("MANUAL"), not its values ("manual"). We want the lowercase values in
    # the database, so we say so explicitly.
    integration_tier: Mapped[IntegrationTier] = mapped_column(
        Enum(
            IntegrationTier,
            name="integration_tier",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=IntegrationTier.MANUAL,
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(
            VerificationStatus,
            name="verification_status",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=VerificationStatus.PENDING,
    )

    # Percent, e.g. 15.00. Numeric because money and rates are never floats:
    # 0.1 + 0.2 != 0.3 in binary floating point, and that error compounds
    # through a ledger.
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("15.00")
    )
    trust_score: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), nullable=False, default=Decimal("0.00")
    )

    policies: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "commission_rate >= 0 AND commission_rate <= 100",
            name="commission_rate_is_a_percentage",
        ),
    )
