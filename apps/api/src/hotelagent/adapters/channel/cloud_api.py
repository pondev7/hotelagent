"""WhatsApp Cloud API adapter — inbound half.

The only file in the codebase that knows what a Meta webhook payload looks
like (invariant #9). Everything past this boundary sees `InboundMessage`.
"""

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any

from hotelagent.enums import Channel, MessageType
from hotelagent.modules.channel.schemas import InboundAttachment, InboundBatch, InboundMessage

_SIGNATURE_PREFIX = "sha256="

# Meta's message "type" strings mapped into our vocabulary. Anything absent is
# recorded as UNSUPPORTED rather than dropped — a message we cannot render is
# still a message the traveller sent, and losing it silently is worse than
# showing an operator "unsupported attachment".
_TYPE_MAP: dict[str, MessageType] = {
    "text": MessageType.TEXT,
    "image": MessageType.IMAGE,
    "audio": MessageType.AUDIO,
    "voice": MessageType.AUDIO,
    "video": MessageType.DOCUMENT,
    "document": MessageType.DOCUMENT,
    "sticker": MessageType.IMAGE,
    "location": MessageType.LOCATION,
    "interactive": MessageType.INTERACTIVE,
    "button": MessageType.INTERACTIVE,
    "template": MessageType.TEMPLATE,
    "system": MessageType.SYSTEM,
}


def verify_signature(*, raw_body: bytes, header: str | None, app_secret: str) -> bool:
    """Verify Meta's `X-Hub-Signature-256` header.

    Meta signs the request body with the app secret. Recomputing that HMAC and
    comparing proves two things at once: the request really came from someone
    holding the secret, and the body was not altered in transit.

    Three details that are each a vulnerability if skipped:

    1. **The raw bytes.** The signature covers the body exactly as sent.
       Parsing JSON and re-serialising changes whitespace and key order, and
       the signature will never match again.
    2. **`hmac.compare_digest`.** A plain `==` on strings returns as soon as it
       finds a differing byte, so how long it takes leaks how much of the
       prefix was right. Repeated over many requests that is enough to
       reconstruct a valid signature. `compare_digest` takes the same time
       whatever the input.
    3. **An empty secret fails closed.** A missing configuration value must
       never mean "accept everything".
    """
    if not app_secret or not header:
        return False
    if not header.startswith(_SIGNATURE_PREFIX):
        return False

    provided = header[len(_SIGNATURE_PREFIX) :]
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided, expected)


def verify_subscription(
    *, mode: str | None, token: str | None, challenge: str | None, verify_token: str
) -> str | None:
    """Meta's one-time GET handshake when a webhook URL is subscribed.

    Meta calls the URL with a token it was configured with; echo the challenge
    back if it matches. Compared in constant time for the same reason as above.
    """
    if mode != "subscribe" or challenge is None or token is None or not verify_token:
        return None
    if not hmac.compare_digest(token, verify_token):
        return None
    return challenge


def _timestamp(raw: Any) -> datetime:
    """Meta sends seconds since the epoch, as a string."""
    try:
        return datetime.fromtimestamp(int(raw), tz=UTC)
    except (TypeError, ValueError):
        return datetime.now(UTC)


def _interactive_payload(message: dict[str, Any]) -> dict[str, object]:
    interactive = message.get("interactive") or {}
    for key in ("button_reply", "list_reply"):
        reply = interactive.get(key)
        if isinstance(reply, dict):
            return {"reply_id": reply.get("id"), "title": reply.get("title"), "kind": key}
    button = message.get("button") or {}
    if button:
        return {"reply_id": button.get("payload"), "title": button.get("text"), "kind": "button"}
    return {}


def _attachment(message: dict[str, Any], kind: MessageType) -> InboundAttachment | None:
    for media_key in ("image", "audio", "voice", "video", "document", "sticker"):
        media = message.get(media_key)
        if isinstance(media, dict):
            return InboundAttachment(
                kind=kind,
                external_media_id=media.get("id"),
                mime_type=media.get("mime_type"),
                caption=media.get("caption"),
            )
    location = message.get("location")
    if isinstance(location, dict):
        return InboundAttachment(kind=MessageType.LOCATION, data=dict(location))
    if kind is MessageType.INTERACTIVE:
        payload = _interactive_payload(message)
        if payload:
            return InboundAttachment(kind=kind, data=payload)
    return None


def parse_webhook(payload: dict[str, Any]) -> InboundBatch:
    """Turn a Cloud API webhook body into our own types.

    Meta's envelope nests four levels deep — entry -> changes -> value ->
    messages — and every level is a list. Tolerance matters here: a webhook
    that we fail to parse is retried by Meta and then dropped, so unknown
    shapes are skipped rather than raised on.
    """
    messages: list[InboundMessage] = []
    statuses: list[dict[str, object]] = []

    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            account_id = metadata.get("phone_number_id")

            profiles: dict[str, str] = {}
            for contact in value.get("contacts") or []:
                wa_id = contact.get("wa_id")
                name = (contact.get("profile") or {}).get("name")
                if wa_id and name:
                    profiles[wa_id] = name

            for status in value.get("statuses") or []:
                statuses.append(dict(status))

            for message in value.get("messages") or []:
                external_id = message.get("id")
                sender = message.get("from")
                if not external_id or not sender:
                    continue

                raw_type = str(message.get("type") or "text")
                kind = _TYPE_MAP.get(raw_type, MessageType.UNSUPPORTED)

                text = None
                if kind is MessageType.TEXT:
                    text = (message.get("text") or {}).get("body")
                elif kind is MessageType.INTERACTIVE:
                    text = str(_interactive_payload(message).get("title") or "") or None

                attachment = _attachment(message, kind)
                context = message.get("context") or {}

                messages.append(
                    InboundMessage(
                        channel=Channel.WHATSAPP,
                        external_message_id=str(external_id),
                        external_user_id=str(sender),
                        external_account_id=str(account_id) if account_id else None,
                        profile_name=profiles.get(str(sender)),
                        message_type=kind,
                        text=text,
                        attachments=[attachment] if attachment else [],
                        sent_at=_timestamp(message.get("timestamp")),
                        replies_to_external_id=context.get("id"),
                    )
                )

    return InboundBatch(messages=messages, statuses=statuses)
