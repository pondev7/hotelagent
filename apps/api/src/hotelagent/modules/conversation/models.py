"""Conversation tables: User, Conversation, Message.

Note what is *not* here: any WhatsApp vocabulary. `Message` is the
channel-agnostic internal schema of invariant #2 — the provider payload is
normalised at the gateway boundary and never reaches this table.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hotelagent.db.base import Base
from hotelagent.db.mixins import CityScopedMixin, IdMixin, TimestampMixin
from hotelagent.enums import AutomationLevel, Channel


class ConversationState(enum.StrEnum):
    ACTIVE = "active"
    WAITING_ON_HOTEL = "waiting_on_hotel"  # a CallTask or bot ping is outstanding
    WAITING_ON_CUSTOMER = "waiting_on_customer"
    ESCALATED = "escalated"
    CLOSED = "closed"


class MessageDirection(enum.StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageType(enum.StrEnum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"
    LOCATION = "location"
    INTERACTIVE = "interactive"  # buttons and list replies
    TEMPLATE = "template"
    SYSTEM = "system"


class SenderKind(enum.StrEnum):
    """Who composed an outbound message.

    This is an internal fact and never surfaces to the traveller — the persona
    is single and constant (`docs/vision.md` §4.1). It exists because the share
    of messages sent by AGENT versus OPERATOR is the containment metric the
    whole automation ladder is measured by.
    """

    CUSTOMER = "customer"
    OPERATOR = "operator"
    AGENT = "agent"
    SYSTEM = "system"


class User(Base, IdMixin, TimestampMixin):
    """A traveller.

    Deliberately **not** city-scoped. A traveller may book in Kanyakumari this
    month and Rameswaram next; scoping them to a city would fragment their
    history exactly where repeat-booking value lives. Conversations are
    city-scoped; people are not.
    """

    __tablename__ = "app_user"  # "user" is reserved in PostgreSQL

    # The channel-level identity (a WhatsApp id). Never logged in full.
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[Channel] = mapped_column(
        Enum(
            Channel,
            name="channel",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=Channel.WHATSAPP,
    )
    display_name: Mapped[str | None] = mapped_column(String(200))
    language_pref: Mapped[str | None] = mapped_column(String(16))
    trust_flags: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    prior_bookings: Mapped[int] = mapped_column(nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("channel", "external_id", name="uq_app_user_channel_external_id"),
    )


class Conversation(Base, IdMixin, CityScopedMixin, TimestampMixin):
    __tablename__ = "conversation"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel: Mapped[Channel] = mapped_column(
        Enum(
            Channel,
            name="channel",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=Channel.WHATSAPP,
    )
    state: Mapped[ConversationState] = mapped_column(
        Enum(
            ConversationState,
            name="conversation_state",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ConversationState.ACTIVE,
    )

    # Invariant #4's seam. Nothing reads this until M2, but the column exists
    # now because by then the table will already have rows.
    automation_level: Mapped[AutomationLevel] = mapped_column(
        Enum(
            AutomationLevel,
            name="automation_level",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=AutomationLevel.L0,
    )

    current_intent: Mapped[str | None] = mapped_column(String(64))
    language: Mapped[str | None] = mapped_column(String(16))
    slots: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)

    first_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_outbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # WhatsApp's 24-hour service window, as data rather than as a rule buried in
    # code. Free-form replies are only permitted before this instant
    # (`docs/vision.md` §3.8) — and replying promptly is also our SLA.
    service_window_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_conversation_city_id_state", "city_id", "state"),)


class Message(Base, IdMixin, CityScopedMixin, TimestampMixin):
    """One turn. Channel-agnostic by construction (invariant #2)."""

    __tablename__ = "message"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(
            MessageDirection,
            name="message_direction",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    sender_kind: Mapped[SenderKind] = mapped_column(
        Enum(
            SenderKind,
            name="sender_kind",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    message_type: Mapped[MessageType] = mapped_column(
        Enum(
            MessageType,
            name="message_type",
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=MessageType.TEXT,
    )

    body: Mapped[str | None] = mapped_column(Text)
    # Structured content for interactive messages, media references, and the
    # like — normalised, never the raw provider payload.
    attachments: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    # The provider's own message id. Unique per channel, which is what makes a
    # redelivered webhook a no-op rather than a duplicate row (invariant #5).
    external_id: Mapped[str | None] = mapped_column(String(128))

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # PostgreSQL allows many NULLs in a unique column, so outbound messages
        # that do not yet have a provider id coexist happily, while a
        # redelivered inbound message is rejected by the index.
        UniqueConstraint("external_id", name="uq_message_external_id"),
        Index("ix_message_conversation_id_created_at", "conversation_id", "created_at"),
    )
