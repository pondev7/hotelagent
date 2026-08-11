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
from hotelagent.modules.channel.schemas import InboundBatch, InboundMessage


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
