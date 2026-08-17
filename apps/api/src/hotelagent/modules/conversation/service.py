"""Public surface of the conversation module.

The channel gateway calls `record_inbound`. It cannot reach `models.py`, so
everything a message needs — finding the traveller, finding or opening the
thread, storing the turn idempotently — happens behind this one function.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.db.idempotency import run_once
from hotelagent.enums import Channel, MessageType, SenderKind
from hotelagent.errors import NotFoundError
from hotelagent.modules.conversation.models import (
    Conversation,
    ConversationState,
    Message,
    MessageDirection,
    User,
)
from hotelagent.modules.conversation.schemas import (
    ConversationSummary,
    MessageOut,
    RecordedMessage,
)


class UnknownConversationError(NotFoundError):
    """Raised when asked about a conversation that does not exist here.

    "Here" includes the city: a conversation belonging to another city is
    reported absent rather than forbidden, because a 403 would confirm it exists.

    Defined in this module because conversation owns the entity. The channel
    gateway imports it — it raises the same error when asked to reply on a
    thread it cannot find, and two classes for one condition would give the
    console two codes to handle for one situation.
    """

    code = "unknown_conversation"


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
        raise UnknownConversationError(f"conversation {conversation_id} does not exist")

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


def _summary(conversation: Conversation, display_name: str | None) -> ConversationSummary:
    return ConversationSummary(
        conversation_id=conversation.id,
        city_id=conversation.city_id,
        user_id=conversation.user_id,
        channel=conversation.channel,
        state=conversation.state,
        automation_level=conversation.automation_level,
        language=conversation.language,
        current_intent=conversation.current_intent,
        display_name=display_name,
        last_inbound_at=conversation.last_inbound_at,
        last_outbound_at=conversation.last_outbound_at,
        service_window_expires_at=conversation.service_window_expires_at,
    )


def _out(message: Message) -> MessageOut:
    return MessageOut(
        message_id=message.id,
        conversation_id=message.conversation_id,
        direction=message.direction,
        sender_kind=message.sender_kind,
        message_type=message.message_type,
        body=message.body,
        attachments=message.attachments,
        sent_at=message.sent_at,
        delivered_at=message.delivered_at,
        read_at=message.read_at,
        failed_reason=message.failed_reason,
    )


async def list_conversations(
    session: AsyncSession,
    *,
    city_id: uuid.UUID,
    limit: int,
    offset: int,
    state: ConversationState | None = None,
) -> tuple[list[ConversationSummary], int]:
    """The unified inbox for one city, most recently active first.

    That ordering is the product, not a preference. HotelAgent is specified as a
    response-time contract (`docs/vision.md` §2.2), so an operator working the
    list top-down must be working the person who is currently waiting on us —
    not the oldest thread in the city. Note the call-task queue in `ops` sorts
    the opposite way, and for the same underlying reason.

    Joined to `User` for the display name: the inbox is unusable if every row
    reads as a UUID, and one join here saves the console N follow-up requests.
    """
    scope = [Conversation.city_id == city_id]
    if state is not None:
        scope.append(Conversation.state == state)

    total = await session.scalar(select(func.count()).select_from(Conversation).where(*scope)) or 0
    rows = (
        await session.execute(
            select(Conversation, User.display_name)
            .join(User, User.id == Conversation.user_id)
            .where(*scope)
            # `id` breaks the tie. Without it two conversations sharing a
            # timestamp can land on both page one and page two, or on neither.
            .order_by(Conversation.last_inbound_at.desc().nullslast(), Conversation.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return [_summary(conversation, display_name) for conversation, display_name in rows], total


async def list_messages(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    city_id: uuid.UUID,
    limit: int,
    offset: int,
) -> tuple[list[MessageOut], int]:
    """One transcript, oldest first — because it is a conversation.

    The city is checked before the messages are read, and an out-of-city
    conversation raises rather than returning an empty page. Empty would be
    indistinguishable from a thread with no messages yet, which is a real state,
    and it would quietly hide a scoping bug instead of surfacing it.
    """
    owner_city = await session.scalar(
        select(Conversation.city_id).where(Conversation.id == conversation_id)
    )
    if owner_city is None or owner_city != city_id:
        raise UnknownConversationError(f"conversation {conversation_id} is not in city {city_id}")

    scope = Message.conversation_id == conversation_id

    total = await session.scalar(select(func.count()).select_from(Message).where(scope)) or 0
    messages = (
        await session.scalars(
            select(Message)
            .where(scope)
            .order_by(Message.sent_at.asc().nullslast(), Message.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()

    return [_out(message) for message in messages], total


async def get_conversation(
    session: AsyncSession, *, conversation_id: uuid.UUID, city_id: uuid.UUID
) -> ConversationSummary:
    """One conversation, scoped to the asking city."""
    row = (
        await session.execute(
            select(Conversation, User.display_name)
            .join(User, User.id == Conversation.user_id)
            .where(Conversation.id == conversation_id, Conversation.city_id == city_id)
        )
    ).first()
    if row is None:
        raise UnknownConversationError(f"conversation {conversation_id} is not in city {city_id}")

    conversation, display_name = row
    return _summary(conversation, display_name)


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
