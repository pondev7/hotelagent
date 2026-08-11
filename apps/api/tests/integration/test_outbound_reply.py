"""S05's exit criterion.

A message received through the console adapter can be replied to, and both
turns appear on one conversation in the right order.
"""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.adapters.channel import console
from hotelagent.enums import MessageType, SenderKind
from hotelagent.modules.channel import service as channel_service
from hotelagent.modules.channel.schemas import ReplyButton
from hotelagent.modules.conversation import service as conversation_service
from hotelagent.modules.conversation.models import Conversation, ConversationState, Message


@pytest.fixture(autouse=True)
def _clear_console() -> None:
    console.clear_sent()


async def test_a_received_message_can_be_replied_to(
    client: httpx.AsyncClient, session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    """The exit criterion, end to end."""
    await client.post("/webhooks/whatsapp", json={"from": "919812345678", "text": "Need a room"})

    conversation = await session.scalar(select(Conversation))
    assert conversation is not None

    await channel_service.send_reply(
        session,
        conversation_id=conversation.id,
        text="Vanakkam! Which dates are you looking at?",
        sender_kind=SenderKind.OPERATOR,
    )

    turns = (
        await session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at, Message.id)
        )
    ).all()

    assert len(turns) == 2
    assert turns[0].direction.value == "inbound"
    assert turns[0].body == "Need a room"
    assert turns[1].direction.value == "outbound"
    assert turns[1].body == "Vanakkam! Which dates are you looking at?"
    assert turns[1].sender_kind is SenderKind.OPERATOR
    assert turns[1].sent_at is not None
    assert turns[1].external_id is not None, "needed to match delivery receipts later"

    assert console.sent_messages()[0]["text"] == "Vanakkam! Which dates are you looking at?"


async def test_the_reply_updates_last_outbound_at(
    client: httpx.AsyncClient, session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    await client.post("/webhooks/whatsapp", json={"from": "919812345678", "text": "hi"})
    conversation = await session.scalar(select(Conversation))
    assert conversation is not None and conversation.last_outbound_at is None

    await channel_service.send_reply(session, conversation_id=conversation.id, text="hello")

    await session.refresh(conversation)
    assert conversation.last_outbound_at is not None


async def test_a_reply_with_buttons_is_recorded_as_interactive(
    client: httpx.AsyncClient, session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    await client.post("/webhooks/whatsapp", json={"from": "919812345678", "text": "hi"})
    conversation = await session.scalar(select(Conversation))
    assert conversation is not None

    await channel_service.send_reply(
        session,
        conversation_id=conversation.id,
        text="Which language?",
        buttons=[ReplyButton(id="en", title="English"), ReplyButton(id="ta", title="தமிழ்")],
    )

    message = await session.scalar(
        select(Message).where(Message.message_type == MessageType.INTERACTIVE)
    )
    assert message is not None
    assert console.sent_messages()[0]["buttons"][1]["title"] == "தமிழ்"


async def test_replying_outside_the_service_window_is_refused(
    client: httpx.AsyncClient, session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    """WhatsApp permits free-form replies for 24 hours. We have no approved
    templates at M1, so outside the window we must refuse clearly rather than
    let Meta reject it."""
    await client.post("/webhooks/whatsapp", json={"from": "919812345678", "text": "hi"})
    conversation = await session.scalar(select(Conversation))
    assert conversation is not None

    conversation.service_window_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await session.flush()

    with pytest.raises(channel_service.ServiceWindowExpiredError):
        await channel_service.send_reply(session, conversation_id=conversation.id, text="too late")

    assert console.sent_messages() == [], "nothing should have been sent"


async def test_a_failed_send_is_still_recorded(
    client: httpx.AsyncClient,
    session: AsyncSession,
    seeded_city: uuid.UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator must be able to see that we tried and could not. Silence is
    the worst outcome here."""
    from hotelagent.modules.channel.schemas import OutboundResult

    await client.post("/webhooks/whatsapp", json={"from": "919812345678", "text": "hi"})
    conversation = await session.scalar(select(Conversation))
    assert conversation is not None

    async def failing_send(*, to: str, text: str) -> OutboundResult:
        return OutboundResult(accepted=False, error="http 503")

    monkeypatch.setattr(console, "send_text", failing_send)

    await channel_service.send_reply(session, conversation_id=conversation.id, text="hello")

    message = await session.scalar(
        select(Message).where(Message.direction == "outbound")  # type: ignore[arg-type]
    )
    assert message is not None
    assert message.failed_reason == "http 503"
    assert message.sent_at is None


async def test_delivery_receipts_are_applied_to_the_message(
    client: httpx.AsyncClient, session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    await client.post("/webhooks/whatsapp", json={"from": "919812345678", "text": "hi"})
    conversation = await session.scalar(select(Conversation))
    assert conversation is not None

    recorded = await channel_service.send_reply(
        session, conversation_id=conversation.id, text="hello"
    )
    message = await session.get(Message, recorded.message_id)
    assert message is not None and message.external_id is not None

    now = datetime.now(UTC)
    for state in ("delivered", "read"):
        applied = await conversation_service.apply_delivery_status(
            session, external_message_id=message.external_id, state=state, occurred_at=now
        )
        assert applied is True

    await session.refresh(message)
    assert message.delivered_at is not None
    assert message.read_at is not None


async def test_a_receipt_for_an_unknown_message_is_ignored(
    session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    """Receipts arrive for messages sent before this system existed."""
    applied = await conversation_service.apply_delivery_status(
        session,
        external_message_id="wamid.NEVER-SEEN",
        state="delivered",
        occurred_at=datetime.now(UTC),
    )
    assert applied is False


async def test_receipts_are_idempotent(
    client: httpx.AsyncClient, session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    """Receipts are redelivered and arrive out of order, so each field is only
    ever set forward, never cleared."""
    await client.post("/webhooks/whatsapp", json={"from": "919812345678", "text": "hi"})
    conversation = await session.scalar(select(Conversation))
    assert conversation is not None
    recorded = await channel_service.send_reply(
        session, conversation_id=conversation.id, text="hello"
    )
    message = await session.get(Message, recorded.message_id)
    assert message is not None and message.external_id is not None

    first = datetime.now(UTC)
    later = first + timedelta(seconds=30)
    for occurred in (first, later, first):
        await conversation_service.apply_delivery_status(
            session,
            external_message_id=message.external_id,
            state="delivered",
            occurred_at=occurred,
        )

    await session.refresh(message)
    assert message.delivered_at == first, "the first receipt wins; later ones do not overwrite"


async def test_conversation_state_and_language_can_be_set(
    client: httpx.AsyncClient, session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    await client.post("/webhooks/whatsapp", json={"from": "919812345678", "text": "hi"})
    conversation = await session.scalar(select(Conversation))
    assert conversation is not None

    await conversation_service.set_language(session, conversation_id=conversation.id, language="ta")
    await conversation_service.set_state(
        session, conversation_id=conversation.id, state=ConversationState.WAITING_ON_HOTEL
    )

    await session.refresh(conversation)
    assert conversation.language == "ta"
    assert conversation.state is ConversationState.WAITING_ON_HOTEL
