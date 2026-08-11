"""Payment tables: LedgerEntry.

A **ledger**, not a payments report. The distinction matters: a report is
derived and can be regenerated; a ledger is the record itself and cannot be
rebuilt retrospectively (`docs/milestones.md` M4).

At M1 collection is still a static UPI QR and entries are recorded by hand in
the reconciliation screen. The shape is the same one the gateway will write to
at M4, which is the entire reason it is built now.
"""

import enum
import uuid
from datetime import datetime
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
from hotelagent.db.mixins import CityScopedMixin, IdMixin
from hotelagent.events.append_only import AppendOnlyMixin


class LedgerAccount(enum.StrEnum):
    """The accounts money moves between.

    We collect from the customer and settle net to the hotel
    (`docs/vision.md` §2.6), so every booking touches at least
    CUSTOMER_RECEIPTS, COMMISSION_INCOME and HOTEL_PAYABLE.
    """

    CUSTOMER_RECEIPTS = "customer_receipts"
    HOTEL_PAYABLE = "hotel_payable"
    COMMISSION_INCOME = "commission_income"
    GATEWAY_FEES = "gateway_fees"
    REFUNDS = "refunds"
    SETTLEMENT_CLEARING = "settlement_clearing"


class LedgerDirection(enum.StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class LedgerEntryStatus(enum.StrEnum):
    PENDING = "pending"
    SETTLED = "settled"
    FAILED = "failed"
    REVERSED = "reversed"


class LedgerEntry(Base, IdMixin, CityScopedMixin, AppendOnlyMixin):
    """Append-only. A mistake is corrected by a reversing entry, never by an
    UPDATE — which is how accounting has worked for six hundred years and why
    an auditable trail survives at all."""

    __tablename__ = "ledger_entry"

    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("booking.id", ondelete="RESTRICT"), index=True
    )
    hotel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hotel.id", ondelete="RESTRICT"))

    account: Mapped[LedgerAccount] = mapped_column(
        Enum(
            LedgerAccount,
            name="ledger_account",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    direction: Mapped[LedgerDirection] = mapped_column(
        Enum(
            LedgerDirection,
            name="ledger_direction",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    # Always positive. Which way it moves is `direction`'s job — signed amounts
    # plus a direction column is how you end up double-negating a refund.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")

    status: Mapped[LedgerEntryStatus] = mapped_column(
        Enum(
            LedgerEntryStatus,
            name="ledger_entry_status",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=LedgerEntryStatus.PENDING,
    )

    # The gateway's or bank's own reference (a UPI transaction id at M1).
    gateway_ref: Mapped[str | None] = mapped_column(String(128))
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_is_not_negative"),
        # The same gateway reference must never be booked twice — the database
        # half of invariant #5, alongside the idempotency key table.
        UniqueConstraint("gateway_ref", "account", name="uq_ledger_entry_gateway_ref_account"),
        Index("ix_ledger_entry_city_id_occurred_at", "city_id", "occurred_at"),
    )
