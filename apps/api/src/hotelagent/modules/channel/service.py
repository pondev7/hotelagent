"""Public surface of the channel module.

Owns the boundary: raw provider payload in, normalised `InboundMessage` out,
handed to the conversation module through *its* public functions. Note what
this file does not do — it never imports another module's models, and no
WhatsApp vocabulary survives past the adapter call.
"""

import uuid
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.adapters.channel import cloud_api, console
from hotelagent.adapters.channel.base import ChannelAdapter
from hotelagent.config import get_settings
from hotelagent.enums import MessageType, SenderKind
from hotelagent.logging import body_shape, get_logger
from hotelagent.modules.channel.schemas import InboundBatch, ReplyButton
from hotelagent.modules.conversation import service as conversation_service
from hotelagent.modules.conversation.schemas import RecordedMessage
from hotelagent.modules.inventory import service as inventory_service

log = get_logger(__name__)


class ChannelError(RuntimeError):
    """Base for problems the gateway reports in its own vocabulary.

    Services never raise HTTPException — that would tie them to being called
    from a web request, and make them unusable from a worker or a CLI. The
    router translates these into status codes.
    """


class ChannelConfigurationError(ChannelError):
    """Raised when the gateway cannot do its job because config is missing."""


class UnknownConversationError(ChannelError):
    """Raised when asked to reply on a conversation that does not exist."""


class ServiceWindowExpiredError(ChannelError):
    """Raised when a free-form reply is no longer permitted."""


def parse_payload(payload: dict[str, Any]) -> InboundBatch:
    """Normalise a provider payload using the configured adapter."""
    if get_settings().channel_adapter == "cloud_api":
        return cloud_api.parse_webhook(payload)
    return console.parse_webhook(payload)


def verify_inbound_signature(*, raw_body: bytes, header: str | None) -> bool:
    """Whether this request is authentic.

    The console adapter has no signature to verify and is development-only, so
    it accepts. `cloud_api` fails closed on a missing secret.
    """
    settings = get_settings()
    if settings.channel_adapter != "cloud_api":
        return True
    return cloud_api.verify_signature(
        raw_body=raw_body, header=header, app_secret=settings.whatsapp_app_secret
    )


def verify_subscription(
    *, mode: str | None, token: str | None, challenge: str | None
) -> str | None:
    settings = get_settings()
    return cloud_api.verify_subscription(
        mode=mode, token=token, challenge=challenge, verify_token=settings.whatsapp_verify_token
    )


async def handle_inbound(session: AsyncSession, batch: InboundBatch) -> list[RecordedMessage]:
    """Persist every message in a delivery.

    Providers batch several messages into one webhook, so this loops. Each is
    recorded idempotently, which is what makes the whole endpoint safe to
    redeliver (invariant #5).
    """
    settings = get_settings()
    city_id = await inventory_service.get_city_id_by_slug(session, settings.default_city_slug)
    if city_id is None:
        raise ChannelConfigurationError(
            f"no active city with slug {settings.default_city_slug!r}; "
            "every conversation needs a city_id (invariant #1)"
        )

    recorded: list[RecordedMessage] = []
    for message in batch.messages:
        recorded.append(
            await conversation_service.record_inbound(
                session,
                city_id=city_id,
                channel=message.channel,
                external_user_id=message.external_user_id,
                external_message_id=message.external_message_id,
                message_type=message.message_type,
                text=message.text,
                attachments=[a.model_dump(mode="json") for a in message.attachments],
                sent_at=message.sent_at,
                profile_name=message.profile_name,
            )
        )
    return recorded


def get_adapter() -> ChannelAdapter:
    """The configured adapter.

    Returns the *module* — Python modules satisfy a Protocol structurally, so
    `cloud_api` and `console` are valid `ChannelAdapter`s without either
    inheriting anything. The caller depends on the protocol, never on which
    module came back.
    """
    if get_settings().channel_adapter == "cloud_api":
        return cast(ChannelAdapter, cloud_api)
    return cast(ChannelAdapter, console)


async def send_reply(
    session: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    text: str,
    sender_kind: SenderKind = SenderKind.OPERATOR,
    buttons: list[ReplyButton] | None = None,
) -> RecordedMessage:
    """Send a reply on a conversation and record it.

    The order matters: send first, then record what happened. Recording first
    would leave a message in the transcript that the traveller never received,
    which is worse than the reverse — an operator can see a failed send and
    retry, but cannot see a message that claims to have been delivered.
    """
    recipient = await conversation_service.get_recipient(session, conversation_id)
    if recipient is None:
        raise UnknownConversationError(f"conversation {conversation_id} has no recipient")

    if not await conversation_service.is_within_service_window(session, conversation_id):
        # Outside the 24-hour window only approved templates may be sent, and
        # we have none at M1. Refuse clearly rather than let the provider
        # reject it and call that an error.
        raise ServiceWindowExpiredError(
            "the 24-hour service window has closed; a template is required"
        )

    adapter = get_adapter()
    if buttons:
        result = await adapter.send_buttons(to=recipient, text=text, buttons=buttons)
    else:
        result = await adapter.send_text(to=recipient, text=text)

    log.info(
        "channel.reply",
        conversation_id=str(conversation_id),
        accepted=result.accepted,
        sender_kind=sender_kind.value,
        **body_shape(text),
    )

    return await conversation_service.record_outbound(
        session,
        conversation_id=conversation_id,
        sender_kind=sender_kind,
        message_type=MessageType.INTERACTIVE if buttons else MessageType.TEXT,
        text=text,
        attachments=[{"buttons": [b.model_dump() for b in buttons]}] if buttons else None,
        external_message_id=result.external_message_id,
        failed_reason=None if result.accepted else (result.error or "send failed"),
    )


async def handle_statuses(session: AsyncSession, batch: InboundBatch) -> int:
    """Apply delivery receipts carried on an inbound delivery."""
    applied = 0
    for status in batch.statuses:
        matched = await conversation_service.apply_delivery_status(
            session,
            external_message_id=status.external_message_id,
            state=status.state,
            occurred_at=status.occurred_at,
            error=status.error,
        )
        applied += int(matched)
    return applied
