"""Public surface of the conversation module.

The channel gateway calls `record_inbound`. It cannot reach `models.py`, so
everything a message needs — finding the traveller, finding or opening the
thread, storing the turn idempotently — happens behind this one function.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.db.idempotency import run_once
from hotelagent.enums import Channel, MessageType, SenderKind
from hotelagent.modules.conversation.models import (
    Conversation,
    ConversationState,
    Message,
    MessageDirection,
    User,
)
from hotelagent.modules.conversation.schemas import RecordedMessage

# WhatsApp permits free-form replies for 24 hours after the customer's last
# message; outside it, only paid templates (`docs/vision.md` §3.8). Stored on
# the conversation so the rule is data rather than a constant buried in code.
SERVICE_WINDOW = timedelta(hours=24)

IDEMPOTENCY_SCOPE = "inbound_message"


async def _find_or_create_user(
    session: AsyncSession, *, channel: Channel, external_user_id: str, profile_name: str | None
) -> User:
    """Concurrency-safe upsert.

    Two webhooks from a first-time traveller can arrive together. A
    select-then-insert would let both find nothing and both insert; the unique
    constraint on (channel, external_id) plus ON CONFLICT DO NOTHING makes the
    database decide.
    """
    await session.execute(
        pg_insert(User)
        .values(
            id=uuid.uuid4(),
            channel=channel,
            external_id=external_user_id,
            display_name=profile_name,
        )
        .on_conflict_do_nothing(index_elements=["channel", "external_id"])
    )
    user = await session.scalar(
        select(User).where(User.channel == channel, User.external_id == external_user_id)
    )
    if user is None:  # pragma: no cover - the insert above guarantees a row
        raise RuntimeError("user upsert did not produce a row")

    if profile_name and not user.display_name:
        user.display_name = profile_name
    return user


async def _find_or_open_conversation(
    session: AsyncSession, *, city_id: uuid.UUID, user: User, channel: Channel
) -> Conversation:
    conversation = await session.scalar(
        select(Conversation)
        .where(
            Conversation.user_id == user.id,
            Conversation.city_id == city_id,
            Conversation.state != ConversationState.CLOSED,
        )
        .order_by(Conversation.created_at.desc())
        .limit(1)
    )
    if conversation is not None:
        return conversation

    conversation = Conversation(city_id=city_id, user_id=user.id, channel=channel)
    session.add(conversation)
    await session.flush()
    return conversation


async def record_inbound(
    session: AsyncSession,
    *,
    city_id: uuid.UUID,
    channel: Channel,
    external_user_id: str,
    external_message_id: str,
    message_type: MessageType,
    text: str | None = None,
    attachments: list[dict[str, object]] | None = None,
    sent_at: datetime | None = None,
    profile_name: str | None = None,
) -> RecordedMessage:
    """Record one inbound message, exactly once.

    Safe to call repeatedly with the same `external_message_id`: the second and
    later calls write nothing and report `is_duplicate=True`.
    """
    user = await _find_or_create_user(
        session, channel=channel, external_user_id=external_user_id, profile_name=profile_name
    )
    conversation = await _find_or_open_conversation(
        session, city_id=city_id, user=user, channel=channel
    )
    occurred = sent_at or datetime.now(UTC)

    async def store() -> uuid.UUID:
        message = Message(
            city_id=city_id,
            conversation_id=conversation.id,
            direction=MessageDirection.INBOUND,
            sender_kind=SenderKind.CUSTOMER,
            message_type=message_type,
            body=text,
            attachments=attachments or [],
            external_id=external_message_id,
            sent_at=occurred,
        )
        session.add(message)
        await session.flush()
        return message.id

    result = await run_once(
        session,
        scope=IDEMPOTENCY_SCOPE,
        key=f"{channel.value}:{external_message_id}",
        operation=store,
        resource_type="message",
    )

    if not result.is_replay:
        if conversation.first_inbound_at is None:
            conversation.first_inbound_at = occurred
        conversation.last_inbound_at = occurred
        conversation.service_window_expires_at = occurred + SERVICE_WINDOW
        await session.flush()

    if result.resource_id is None:  # pragma: no cover - defensive
        raise RuntimeError("idempotent store returned no message id")

    return RecordedMessage(
        message_id=result.resource_id,
        conversation_id=conversation.id,
        user_id=user.id,
        is_duplicate=result.is_replay,
    )


async def record_outbound(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    sender_kind: SenderKind,
    message_type: MessageType = MessageType.TEXT,
    text: str | None = None,
    attachments: list[dict[str, object]] | None = None,
    external_message_id: str | None = None,
    failed_reason: str | None = None,
) -> RecordedMessage:
    """Record a message we sent.

    Called after the adapter has accepted it, so `external_message_id` is
    available to match delivery receipts against. A send that failed is still
    recorded, with `failed_reason` — an operator needs to see that we tried and
    could not, which is precisely the case where silence is worst.
    """
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise ValueError(f"conversation {conversation_id} does not exist")

    now = datetime.now(UTC)
    message = Message(
        city_id=conversation.city_id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND,
        sender_kind=sender_kind,
        message_type=message_type,
        body=text,
        attachments=attachments or [],
        external_id=external_message_id,
        sent_at=None if failed_reason else now,
        failed_reason=failed_reason,
    )
    session.add(message)

    if not failed_reason:
        conversation.last_outbound_at = now
    await session.flush()

    return RecordedMessage(
        message_id=message.id,
        conversation_id=conversation.id,
        user_id=conversation.user_id,
        is_duplicate=False,
    )


async def get_recipient(session: AsyncSession, conversation_id: uuid.UUID) -> str | None:
    """The channel-level identity to send a reply to."""
    recipient: str | None = await session.scalar(
        select(User.external_id)
        .join(Conversation, Conversation.user_id == User.id)
        .where(Conversation.id == conversation_id)
    )
    return recipient


async def is_within_service_window(session: AsyncSession, conversation_id: uuid.UUID) -> bool:
    """Whether a free-form reply is still permitted.

    WhatsApp allows free-form replies for 24 hours after the customer's last
    message; outside it only paid templates are permitted (`docs/vision.md`
    §3.8). We have no approved templates at M1, so outside the window we cannot
    reply at all — which the caller must handle rather than discover as a
    provider error.
    """
    expires_at = await session.scalar(
        select(Conversation.service_window_expires_at).where(Conversation.id == conversation_id)
    )
    return expires_at is not None and expires_at > datetime.now(UTC)


async def apply_delivery_status(
    session: AsyncSession,
    *,
    external_message_id: str,
    state: str,
    occurred_at: datetime,
    error: str | None = None,
) -> bool:
    """Record a receipt against the message it refers to.

    Receipts arrive out of order and are redelivered, so this is written to be
    safe to apply repeatedly: each field is only ever set forward, never
    cleared. Returns False when the message is unknown, which happens routinely
    for messages sent before this system existed.
    """
    message = await session.scalar(
        select(Message).where(Message.external_id == external_message_id)
    )
    if message is None:
        return False

    if state == "sent" and message.sent_at is None:
        message.sent_at = occurred_at
    elif state == "delivered" and message.delivered_at is None:
        message.delivered_at = occurred_at
    elif state == "read" and message.read_at is None:
        message.read_at = occurred_at
    elif state == "failed":
        message.failed_reason = error or "delivery failed"

    await session.flush()
    return True


async def set_language(session: AsyncSession, *, conversation_id: uuid.UUID, language: str) -> None:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is not None:
        conversation.language = language
        await session.flush()


async def set_state(
    session: AsyncSession, *, conversation_id: uuid.UUID, state: ConversationState
) -> None:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is not None:
        conversation.state = state
        await session.flush()
