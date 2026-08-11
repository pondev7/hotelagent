"""Development channel adapter.

Produces the same `InboundMessage` the Cloud API adapter does, from a trivial
payload, with no signature and no Meta account.

This is not a testing convenience bolted on afterwards — it is why the whole
inbound path can be built and verified now, while "BSP versus direct Cloud
API" is still an open question in `docs/vision.md` §6. The decision blocks the
real adapter; it does not block the gateway, the schema, the service or the
tests. That is invariant #9 paying for itself in the first slice that needs it.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from hotelagent.enums import Channel, MessageType
from hotelagent.logging import body_shape, get_logger, redact_identifier
from hotelagent.modules.channel.schemas import (
    InboundBatch,
    InboundMessage,
    OutboundResult,
    ReplyButton,
)

log = get_logger(__name__)


def parse_webhook(payload: dict[str, Any]) -> InboundBatch:
    """Accept a minimal dev payload: `{"from": "...", "text": "..."}`.

    Anything omitted is filled in, so poking at the endpoint by hand is a
    one-line curl.
    """
    sender = str(payload.get("from") or "dev-user")
    text = payload.get("text")

    message = InboundMessage(
        channel=Channel.CONSOLE,
        external_message_id=str(payload.get("id") or f"console-{uuid4().hex}"),
        external_user_id=sender,
        external_account_id=payload.get("to"),
        profile_name=payload.get("name"),
        message_type=MessageType.TEXT,
        text=str(text) if text is not None else None,
        sent_at=datetime.now(UTC),
    )
    return InboundBatch(messages=[message])


# --- Sending ---------------------------------------------------------------
#
# "Sending" in development means recording. Outbound messages are appended to
# a module-level list and logged, so a test or a curl session can see exactly
# what would have gone to the traveller without a Meta account, a token, or a
# public URL.

_SENT: list[dict[str, Any]] = []


def sent_messages() -> list[dict[str, Any]]:
    """Everything the console adapter has "sent" this process."""
    return list(_SENT)


def clear_sent() -> None:
    _SENT.clear()


async def send_text(*, to: str, text: str) -> OutboundResult:
    record = {"to": to, "type": "text", "text": text}
    _SENT.append(record)
    log.info("channel.console.send", to=redact_identifier(to), **body_shape(text))
    return OutboundResult(external_message_id=f"console-out-{uuid4().hex}")


async def send_buttons(*, to: str, text: str, buttons: list[ReplyButton]) -> OutboundResult:
    record = {
        "to": to,
        "type": "interactive",
        "text": text,
        "buttons": [b.model_dump() for b in buttons],
    }
    _SENT.append(record)
    log.info(
        "channel.console.send",
        to=redact_identifier(to),
        button_count=len(buttons),
        **body_shape(text),
    )
    return OutboundResult(external_message_id=f"console-out-{uuid4().hex}")
