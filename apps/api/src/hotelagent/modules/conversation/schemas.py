"""Public data shapes for the conversation module.

These cross module boundaries. ORM instances never do — an ORM object carries a
session, lazy-loading behaviour and a mutation surface, and handing one to
another module makes the boundary decorative.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from hotelagent.enums import AutomationLevel, Channel, MessageType, SenderKind
from hotelagent.modules.conversation.models import ConversationState, MessageDirection

# Re-exported deliberately. `ConversationState` and `MessageDirection` are this
# module's vocabulary but they live next to the tables that constrain them, and
# `models.py` is not importable from outside — not even by our own router. Naming
# them here makes `schemas` the single public surface mypy will let anyone read
# (strict mode forbids implicit re-export, so the `__all__` is load-bearing).
__all__ = [
    "ConversationState",
    "ConversationSummary",
    "MessageDirection",
    "MessageOut",
    "RecordedMessage",
]


class RecordedMessage(BaseModel):
    """The outcome of recording one inbound message."""

    model_config = ConfigDict(frozen=True)

    message_id: uuid.UUID
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    is_duplicate: bool
    """True when this provider message id had already been recorded — the
    webhook was redelivered and nothing new was written (invariant #5)."""


class ConversationSummary(BaseModel):
    """One row of the unified inbox.

    Carries `automation_level` even though nothing reads it until M2. The
    Automation Governor is invariant #4, and the inbox is where an operator will
    eventually see — and override — which conversations the agent is fronting.
    Publishing the field now means the console's type does not change when it
    starts to matter.
    """

    model_config = ConfigDict(frozen=True)

    conversation_id: uuid.UUID
    city_id: uuid.UUID
    user_id: uuid.UUID
    channel: Channel
    state: ConversationState
    automation_level: AutomationLevel
    language: str | None = None
    current_intent: str | None = None

    display_name: str | None = None
    last_inbound_at: datetime | None = None
    last_outbound_at: datetime | None = None
    service_window_expires_at: datetime | None = None


class MessageOut(BaseModel):
    """One turn of a transcript, as the console renders it.

    The delivery timestamps are all four published deliberately. "Sent but not
    delivered" is a different operational situation from "delivered but not
    read", and an operator deciding whether to ring a traveller needs to tell
    them apart (`docs/vision.md` §3.8).
    """

    model_config = ConfigDict(frozen=True)

    message_id: uuid.UUID
    conversation_id: uuid.UUID
    direction: MessageDirection
    sender_kind: SenderKind
    message_type: MessageType
    body: str | None = None
    attachments: list[dict[str, object]] = Field(default_factory=list)

    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    failed_reason: str | None = None
