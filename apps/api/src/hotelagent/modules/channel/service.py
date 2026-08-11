"""Public surface of the channel module.

Owns the boundary: raw provider payload in, normalised `InboundMessage` out,
handed to the conversation module through *its* public functions. Note what
this file does not do — it never imports another module's models, and no
WhatsApp vocabulary survives past the adapter call.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.adapters.channel import cloud_api, console
from hotelagent.config import get_settings
from hotelagent.modules.channel.schemas import InboundBatch
from hotelagent.modules.conversation import service as conversation_service
from hotelagent.modules.conversation.schemas import RecordedMessage
from hotelagent.modules.inventory import service as inventory_service


class ChannelConfigurationError(RuntimeError):
    """Raised when the gateway cannot do its job because config is missing."""


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
