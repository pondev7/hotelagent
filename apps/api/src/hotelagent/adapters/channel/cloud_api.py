"""WhatsApp Cloud API adapter.

The only file in the codebase that knows what a Meta payload looks like, in
either direction (invariant #9). Everything past this boundary sees
`InboundMessage`, `OutboundResult` and `DeliveryStatus`.
"""

import asyncio
import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any, Literal

import httpx

from hotelagent.config import get_settings
from hotelagent.enums import Channel, MessageType
from hotelagent.logging import get_logger, redact_identifier
from hotelagent.modules.channel.schemas import (
    DeliveryStatus,
    InboundAttachment,
    InboundBatch,
    InboundMessage,
    OutboundResult,
    ReplyButton,
)

DeliveryState = Literal["sent", "delivered", "read", "failed"]

log = get_logger(__name__)

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


_STATUS_MAP: dict[str, DeliveryState] = {
    "sent": "sent",
    "delivered": "delivered",
    "read": "read",
    "failed": "failed",
}


def _delivery_status(status: dict[str, Any]) -> DeliveryStatus | None:
    external_id = status.get("id")
    state = _STATUS_MAP.get(str(status.get("status") or ""))
    if not external_id or state is None:
        return None

    errors = status.get("errors") or []
    detail = None
    if errors and isinstance(errors[0], dict):
        detail = errors[0].get("title") or errors[0].get("message")

    return DeliveryStatus(
        external_message_id=str(external_id),
        state=state,
        occurred_at=_timestamp(status.get("timestamp")),
        error=str(detail) if detail else None,
    )


def parse_webhook(payload: dict[str, Any]) -> InboundBatch:
    """Turn a Cloud API webhook body into our own types.

    Meta's envelope nests four levels deep — entry -> changes -> value ->
    messages — and every level is a list. Tolerance matters here: a webhook
    that we fail to parse is retried by Meta and then dropped, so unknown
    shapes are skipped rather than raised on.
    """
    messages: list[InboundMessage] = []
    statuses: list[DeliveryStatus] = []

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
                parsed = _delivery_status(status)
                if parsed is not None:
                    statuses.append(parsed)

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


# --- Sending ---------------------------------------------------------------
#
# Retrying a send is not free, because sending is **not idempotent**. The Cloud
# API has no idempotency key, so a retry after a request that actually
# succeeded delivers the message twice — and the traveller sees us say the same
# thing again.
#
# So the retry policy is decided by *what we know*, not by what failed:
#
#   ConnectError / ConnectTimeout  -> retry. The request never reached Meta,
#                                     so it cannot have been processed.
#   429, 500-504                   -> retry. Meta is explicitly telling us it
#                                     did not handle this one.
#   ReadTimeout                    -> DO NOT retry. We sent the request and
#                                     never heard back; it may well have been
#                                     delivered. A duplicate message is worse
#                                     than a missing one here, because the
#                                     missing one is visible to an operator in
#                                     the console and the duplicate is not.
#   other 4xx                      -> do not retry. It will fail identically.
#
# That ReadTimeout line is the interesting one, and it is a judgement about
# *this* product rather than a general rule.

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_BACKOFF_BASE_SECONDS = 0.5


def _endpoint() -> str:
    settings = get_settings()
    return (
        f"{settings.whatsapp_api_base_url.rstrip('/')}"
        f"/{settings.whatsapp_api_version}"
        f"/{settings.whatsapp_phone_number_id}/messages"
    )


async def _post(payload: dict[str, Any], *, to: str) -> OutboundResult:
    settings = get_settings()
    if not settings.whatsapp_access_token or not settings.whatsapp_phone_number_id:
        return OutboundResult(accepted=False, error="whatsapp credentials not configured")

    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    last_error = "send failed"

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        for attempt in range(1, max(1, settings.http_max_attempts) + 1):
            try:
                response = await client.post(_endpoint(), json=payload, headers=headers)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                # Never reached Meta — safe to retry.
                last_error = f"connect: {type(exc).__name__}"
            except httpx.ReadTimeout:
                # Ambiguous. Deliberately not retried; see the note above.
                log.warning("channel.send.read_timeout", to=redact_identifier(to), attempt=attempt)
                return OutboundResult(accepted=False, error="read timeout, delivery unknown")
            else:
                if response.status_code < 300:
                    body = response.json()
                    messages = body.get("messages") or [{}]
                    return OutboundResult(external_message_id=messages[0].get("id"))
                if response.status_code not in _RETRY_STATUS:
                    return OutboundResult(accepted=False, error=f"http {response.status_code}")
                last_error = f"http {response.status_code}"

            if attempt < settings.http_max_attempts:
                # Exponential backoff: 0.5s, 1s, 2s. Retrying immediately just
                # adds load to something already struggling.
                await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))

    log.warning("channel.send.failed", to=redact_identifier(to), error=last_error)
    return OutboundResult(accepted=False, error=last_error)


async def send_text(*, to: str, text: str) -> OutboundResult:
    return await _post(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        },
        to=to,
    )


async def send_buttons(*, to: str, text: str, buttons: list[ReplyButton]) -> OutboundResult:
    return await _post(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": b.id, "title": b.title}}
                        for b in buttons[:3]  # Meta permits at most three
                    ]
                },
            },
        },
        to=to,
    )
