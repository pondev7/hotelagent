"""entity set, event log, idempotency

Revision ID: 79eda7594cc1
Revises: 0001
Create Date: 2026-08-11 19:08:35.311582+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Enum types, declared once. create_type=False stops create_table emitting
# CREATE TYPE implicitly — which would fail for a type used by two tables
# (channel) or already created by an earlier migration (integration_tier).
channel_enum = postgresql.ENUM(
    "whatsapp", "sms", "instagram", "web", "console", name="channel", create_type=False
)
conversation_state_enum = postgresql.ENUM(
    "active",
    "waiting_on_hotel",
    "waiting_on_customer",
    "escalated",
    "closed",
    name="conversation_state",
    create_type=False,
)
automation_level_enum = postgresql.ENUM(
    "l0", "l1", "l2", "l3", name="automation_level", create_type=False
)
message_direction_enum = postgresql.ENUM(
    "inbound", "outbound", name="message_direction", create_type=False
)
sender_kind_enum = postgresql.ENUM(
    "customer", "operator", "agent", "system", name="sender_kind", create_type=False
)
message_type_enum = postgresql.ENUM(
    "text",
    "image",
    "audio",
    "document",
    "location",
    "interactive",
    "template",
    "system",
    name="message_type",
    create_type=False,
)
integration_tier_enum = postgresql.ENUM(
    "live", "bot", "manual", name="integration_tier", create_type=False
)
booking_status_enum = postgresql.ENUM(
    "held",
    "pending_payment",
    "confirmed",
    "checked_in",
    "completed",
    "cancelled",
    "no_show",
    "expired",
    name="booking_status",
    create_type=False,
)
call_task_status_enum = postgresql.ENUM(
    "open",
    "claimed",
    "resolved",
    "cancelled",
    "expired",
    name="call_task_status",
    create_type=False,
)
call_task_outcome_enum = postgresql.ENUM(
    "available",
    "unavailable",
    "no_answer",
    "unreachable",
    name="call_task_outcome",
    create_type=False,
)
booking_event_type_enum = postgresql.ENUM(
    "created",
    "held",
    "hold_expired",
    "payment_initiated",
    "payment_received",
    "confirmed",
    "modified",
    "cancelled",
    "checked_in",
    "completed",
    "no_show",
    "refunded",
    name="booking_event_type",
    create_type=False,
)
ledger_account_enum = postgresql.ENUM(
    "customer_receipts",
    "hotel_payable",
    "commission_income",
    "gateway_fees",
    "refunds",
    "settlement_clearing",
    name="ledger_account",
    create_type=False,
)
ledger_direction_enum = postgresql.ENUM(
    "debit", "credit", name="ledger_direction", create_type=False
)
ledger_entry_status_enum = postgresql.ENUM(
    "pending", "settled", "failed", "reversed", name="ledger_entry_status", create_type=False
)

# Owned by this migration, so created and dropped here.
NEW_ENUMS = [
    channel_enum,
    conversation_state_enum,
    automation_level_enum,
    message_direction_enum,
    sender_kind_enum,
    message_type_enum,
    booking_status_enum,
    call_task_status_enum,
    call_task_outcome_enum,
    booking_event_type_enum,
    ledger_account_enum,
    ledger_direction_enum,
    ledger_entry_status_enum,
]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in NEW_ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "app_user",
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("channel", channel_enum, nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("language_pref", sa.String(length=16), nullable=True),
        sa.Column("trust_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prior_bookings", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_user")),
        sa.UniqueConstraint("channel", "external_id", name="uq_app_user_channel_external_id"),
    )
    op.create_table(
        "idempotency_key",
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_key")),
        sa.UniqueConstraint("scope", "key", name="uq_idempotency_key_scope_key"),
    )
    op.create_table(
        "conversation",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("channel", channel_enum, nullable=False),
        sa.Column("state", conversation_state_enum, nullable=False),
        sa.Column("automation_level", automation_level_enum, nullable=False),
        sa.Column("current_intent", sa.String(length=64), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("slots", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("first_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("service_window_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("city_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["city_id"], ["city.id"], name=op.f("fk_conversation_city_id_city"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_conversation_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation")),
    )
    op.create_index(op.f("ix_conversation_city_id"), "conversation", ["city_id"], unique=False)
    op.create_index(
        "ix_conversation_city_id_state", "conversation", ["city_id", "state"], unique=False
    )
    op.create_index(op.f("ix_conversation_user_id"), "conversation", ["user_id"], unique=False)
    op.create_table(
        "message",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("direction", message_direction_enum, nullable=False),
        sa.Column("sender_kind", sender_kind_enum, nullable=False),
        sa.Column("message_type", message_type_enum, nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("attachments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_reason", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("city_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["city_id"], ["city.id"], name=op.f("fk_message_city_id_city"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name=op.f("fk_message_conversation_id_conversation"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message")),
        sa.UniqueConstraint("external_id", name="uq_message_external_id"),
    )
    op.create_index(op.f("ix_message_city_id"), "message", ["city_id"], unique=False)
    op.create_index(
        op.f("ix_message_conversation_id"), "message", ["conversation_id"], unique=False
    )
    op.create_index(
        "ix_message_conversation_id_created_at",
        "message",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "room_type",
        sa.Column("hotel_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("base_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("total_rooms", sa.Integer(), nullable=False),
        sa.Column("amenities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("city_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("base_price >= 0", name=op.f("ck_room_type_base_price_is_not_negative")),
        sa.CheckConstraint("capacity > 0", name=op.f("ck_room_type_capacity_is_positive")),
        sa.ForeignKeyConstraint(
            ["city_id"], ["city.id"], name=op.f("fk_room_type_city_id_city"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["hotel_id"], ["hotel.id"], name=op.f("fk_room_type_hotel_id_hotel"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_room_type")),
    )
    op.create_index(op.f("ix_room_type_city_id"), "room_type", ["city_id"], unique=False)
    op.create_index(op.f("ix_room_type_hotel_id"), "room_type", ["hotel_id"], unique=False)
    op.create_table(
        "availability_observation",
        sa.Column("hotel_id", sa.Uuid(), nullable=False),
        sa.Column("room_type_id", sa.Uuid(), nullable=True),
        sa.Column("stay_date", sa.Date(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_tier", integration_tier_enum, nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("rooms_available", sa.Integer(), nullable=True),
        sa.Column("quoted_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("operator_id", sa.Text(), nullable=True),
        sa.Column("call_task_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("city_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quoted_price IS NULL OR quoted_price >= 0",
            name=op.f("ck_availability_observation_quoted_price_is_valid"),
        ),
        sa.CheckConstraint(
            "rooms_available IS NULL OR rooms_available >= 0",
            name=op.f("ck_availability_observation_rooms_available_is_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["city_id"],
            ["city.id"],
            name=op.f("fk_availability_observation_city_id_city"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["hotel_id"],
            ["hotel.id"],
            name=op.f("fk_availability_observation_hotel_id_hotel"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["room_type_id"],
            ["room_type.id"],
            name=op.f("fk_availability_observation_room_type_id_room_type"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_availability_observation")),
    )
    op.create_index(
        op.f("ix_availability_observation_city_id"),
        "availability_observation",
        ["city_id"],
        unique=False,
    )
    op.create_index(
        "ix_availability_observation_hotel_id_stay_date",
        "availability_observation",
        ["hotel_id", "stay_date"],
        unique=False,
    )
    op.create_table(
        "booking",
        sa.Column("hotel_id", sa.Uuid(), nullable=False),
        sa.Column("room_type_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("reference", sa.String(length=32), nullable=False),
        sa.Column("check_in", sa.Date(), nullable=False),
        sa.Column("check_out", sa.Date(), nullable=False),
        sa.Column("guests", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("commission_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("commission_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", booking_status_enum, nullable=False),
        sa.Column("payment_ref", sa.String(length=128), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("city_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount >= 0", name=op.f("ck_booking_amount_is_not_negative")),
        sa.CheckConstraint(
            "check_out > check_in", name=op.f("ck_booking_stay_is_at_least_one_night")
        ),
        sa.CheckConstraint(
            "commission_amount >= 0 AND commission_amount <= amount",
            name=op.f("ck_booking_commission_is_within_amount"),
        ),
        sa.CheckConstraint("guests > 0", name=op.f("ck_booking_guests_is_positive")),
        sa.ForeignKeyConstraint(
            ["city_id"], ["city.id"], name=op.f("fk_booking_city_id_city"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name=op.f("fk_booking_conversation_id_conversation"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["hotel_id"], ["hotel.id"], name=op.f("fk_booking_hotel_id_hotel"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["room_type_id"],
            ["room_type.id"],
            name=op.f("fk_booking_room_type_id_room_type"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_booking_user_id_app_user"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking")),
        sa.UniqueConstraint("reference", name="uq_booking_reference"),
    )
    op.create_index(op.f("ix_booking_city_id"), "booking", ["city_id"], unique=False)
    op.create_index("ix_booking_city_id_status", "booking", ["city_id", "status"], unique=False)
    op.create_index(op.f("ix_booking_hotel_id"), "booking", ["hotel_id"], unique=False)
    op.create_index(op.f("ix_booking_user_id"), "booking", ["user_id"], unique=False)
    op.create_table(
        "call_task",
        sa.Column("hotel_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("room_type_id", sa.Uuid(), nullable=True),
        sa.Column("check_in", sa.Date(), nullable=False),
        sa.Column("check_out", sa.Date(), nullable=False),
        sa.Column("guests", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", call_task_status_enum, nullable=False),
        sa.Column("outcome", call_task_outcome_enum, nullable=True),
        sa.Column("quoted_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("rooms_available", sa.Integer(), nullable=True),
        sa.Column("assigned_to", sa.String(length=120), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("city_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["city_id"], ["city.id"], name=op.f("fk_call_task_city_id_city"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            name=op.f("fk_call_task_conversation_id_conversation"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["hotel_id"], ["hotel.id"], name=op.f("fk_call_task_hotel_id_hotel"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["room_type_id"],
            ["room_type.id"],
            name=op.f("fk_call_task_room_type_id_room_type"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_call_task")),
    )
    op.create_index(op.f("ix_call_task_city_id"), "call_task", ["city_id"], unique=False)
    op.create_index(
        "ix_call_task_city_id_status_opened_at",
        "call_task",
        ["city_id", "status", "opened_at"],
        unique=False,
    )
    op.create_index(op.f("ix_call_task_hotel_id"), "call_task", ["hotel_id"], unique=False)
    op.create_table(
        "booking_event",
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", booking_event_type_enum, nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("city_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["booking.id"],
            name=op.f("fk_booking_event_booking_id_booking"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["city_id"],
            ["city.id"],
            name=op.f("fk_booking_event_city_id_city"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_event")),
    )
    op.create_index(
        op.f("ix_booking_event_booking_id"), "booking_event", ["booking_id"], unique=False
    )
    op.create_index(
        "ix_booking_event_booking_id_occurred_at",
        "booking_event",
        ["booking_id", "occurred_at"],
        unique=False,
    )
    op.create_index(op.f("ix_booking_event_city_id"), "booking_event", ["city_id"], unique=False)
    op.create_table(
        "ledger_entry",
        sa.Column("booking_id", sa.Uuid(), nullable=True),
        sa.Column("hotel_id", sa.Uuid(), nullable=True),
        sa.Column("account", ledger_account_enum, nullable=False),
        sa.Column("direction", ledger_direction_enum, nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", ledger_entry_status_enum, nullable=False),
        sa.Column("gateway_ref", sa.String(length=128), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("city_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("amount >= 0", name=op.f("ck_ledger_entry_amount_is_not_negative")),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["booking.id"],
            name=op.f("fk_ledger_entry_booking_id_booking"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["city_id"], ["city.id"], name=op.f("fk_ledger_entry_city_id_city"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["hotel_id"],
            ["hotel.id"],
            name=op.f("fk_ledger_entry_hotel_id_hotel"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ledger_entry")),
        sa.UniqueConstraint("gateway_ref", "account", name="uq_ledger_entry_gateway_ref_account"),
    )
    op.create_index(
        op.f("ix_ledger_entry_booking_id"), "ledger_entry", ["booking_id"], unique=False
    )
    op.create_index(op.f("ix_ledger_entry_city_id"), "ledger_entry", ["city_id"], unique=False)
    op.create_index(
        "ix_ledger_entry_city_id_occurred_at",
        "ledger_entry",
        ["city_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drops the enum types too. DROP TABLE does not remove them, and a
    downgrade that forgets makes the next upgrade fail with
    "type already exists"."""

    op.drop_index("ix_ledger_entry_city_id_occurred_at", table_name="ledger_entry")
    op.drop_index(op.f("ix_ledger_entry_city_id"), table_name="ledger_entry")
    op.drop_index(op.f("ix_ledger_entry_booking_id"), table_name="ledger_entry")
    op.drop_table("ledger_entry")
    op.drop_index(op.f("ix_booking_event_city_id"), table_name="booking_event")
    op.drop_index("ix_booking_event_booking_id_occurred_at", table_name="booking_event")
    op.drop_index(op.f("ix_booking_event_booking_id"), table_name="booking_event")
    op.drop_table("booking_event")
    op.drop_index(op.f("ix_call_task_hotel_id"), table_name="call_task")
    op.drop_index("ix_call_task_city_id_status_opened_at", table_name="call_task")
    op.drop_index(op.f("ix_call_task_city_id"), table_name="call_task")
    op.drop_table("call_task")
    op.drop_index(op.f("ix_booking_user_id"), table_name="booking")
    op.drop_index(op.f("ix_booking_hotel_id"), table_name="booking")
    op.drop_index("ix_booking_city_id_status", table_name="booking")
    op.drop_index(op.f("ix_booking_city_id"), table_name="booking")
    op.drop_table("booking")
    op.drop_index(
        "ix_availability_observation_hotel_id_stay_date", table_name="availability_observation"
    )
    op.drop_index(
        op.f("ix_availability_observation_city_id"), table_name="availability_observation"
    )
    op.drop_table("availability_observation")
    op.drop_index(op.f("ix_room_type_hotel_id"), table_name="room_type")
    op.drop_index(op.f("ix_room_type_city_id"), table_name="room_type")
    op.drop_table("room_type")
    op.drop_index("ix_message_conversation_id_created_at", table_name="message")
    op.drop_index(op.f("ix_message_conversation_id"), table_name="message")
    op.drop_index(op.f("ix_message_city_id"), table_name="message")
    op.drop_table("message")
    op.drop_index(op.f("ix_conversation_user_id"), table_name="conversation")
    op.drop_index("ix_conversation_city_id_state", table_name="conversation")
    op.drop_index(op.f("ix_conversation_city_id"), table_name="conversation")
    op.drop_table("conversation")
    op.drop_table("idempotency_key")
    op.drop_table("app_user")

    bind = op.get_bind()
    for enum_type in reversed(NEW_ENUMS):
        enum_type.drop(bind, checkfirst=True)
