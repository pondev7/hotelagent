"""Normalisation: a Meta payload in, our own types out.

The assertion running through every test here is invariant #2 — nothing
downstream should be able to tell which provider this came from.
"""

from typing import Any

from hotelagent.adapters.channel.cloud_api import parse_webhook
from hotelagent.enums import Channel, MessageType


def _envelope(*messages: dict[str, Any], contacts: list[dict[str, Any]] | None = None) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "919000000000",
                                "phone_number_id": "PN-1",
                            },
                            "contacts": contacts or [],
                            "messages": list(messages),
                        },
                    }
                ],
            }
        ],
    }


def test_a_text_message_is_normalised() -> None:
    payload = _envelope(
        {
            "from": "919812345678",
            "id": "wamid.ABC",
            "timestamp": "1786470000",
            "type": "text",
            "text": {"body": "Need a room this weekend"},
        },
        contacts=[{"wa_id": "919812345678", "profile": {"name": "Anu"}}],
    )

    batch = parse_webhook(payload)

    assert len(batch.messages) == 1
    message = batch.messages[0]
    assert message.channel is Channel.WHATSAPP
    assert message.message_type is MessageType.TEXT
    assert message.text == "Need a room this weekend"
    assert message.external_message_id == "wamid.ABC"
    assert message.external_user_id == "919812345678"
    assert message.external_account_id == "PN-1"
    assert message.profile_name == "Anu"
    assert message.sent_at.tzinfo is not None


def test_several_messages_in_one_delivery_are_all_parsed() -> None:
    """Providers batch. Handling only the first would silently drop messages."""
    payload = _envelope(
        {
            "from": "91981",
            "id": "wamid.1",
            "timestamp": "1786470000",
            "type": "text",
            "text": {"body": "one"},
        },
        {
            "from": "91982",
            "id": "wamid.2",
            "timestamp": "1786470001",
            "type": "text",
            "text": {"body": "two"},
        },
    )

    batch = parse_webhook(payload)

    assert [m.external_message_id for m in batch.messages] == ["wamid.1", "wamid.2"]


def test_an_interactive_reply_carries_the_button_id() -> None:
    payload = _envelope(
        {
            "from": "91981",
            "id": "wamid.BTN",
            "timestamp": "1786470000",
            "type": "interactive",
            "interactive": {
                "type": "button_reply",
                "button_reply": {"id": "check_availability", "title": "Yes, check"},
            },
        }
    )

    message = parse_webhook(payload).messages[0]

    assert message.message_type is MessageType.INTERACTIVE
    assert message.text == "Yes, check"
    assert message.attachments[0].data["reply_id"] == "check_availability"


def test_an_image_becomes_a_reference_not_bytes() -> None:
    payload = _envelope(
        {
            "from": "91981",
            "id": "wamid.IMG",
            "timestamp": "1786470000",
            "type": "image",
            "image": {"id": "MEDIA-9", "mime_type": "image/jpeg", "caption": "the room"},
        }
    )

    message = parse_webhook(payload).messages[0]

    assert message.message_type is MessageType.IMAGE
    assert message.attachments[0].external_media_id == "MEDIA-9"
    assert message.attachments[0].caption == "the room"


def test_an_unknown_type_is_recorded_not_dropped() -> None:
    """A message we cannot render is still a message the traveller sent."""
    payload = _envelope(
        {"from": "91981", "id": "wamid.X", "timestamp": "1786470000", "type": "reaction"}
    )

    message = parse_webhook(payload).messages[0]

    assert message.message_type is MessageType.UNSUPPORTED


def test_malformed_entries_are_skipped_rather_than_raising() -> None:
    """A parse failure means a non-2xx, which means Meta retries and then gives
    up — so tolerance here protects real messages."""
    payload = _envelope(
        {"type": "text", "text": {"body": "no id, no sender"}},
        {
            "from": "91981",
            "id": "wamid.OK",
            "timestamp": "1786470000",
            "type": "text",
            "text": {"body": "fine"},
        },
    )

    batch = parse_webhook(payload)

    assert [m.external_message_id for m in batch.messages] == ["wamid.OK"]


def test_an_empty_payload_yields_nothing() -> None:
    assert parse_webhook({}).messages == []
    assert parse_webhook({"entry": []}).messages == []


def test_status_receipts_are_carried_separately() -> None:
    payload = _envelope()
    payload["entry"][0]["changes"][0]["value"]["statuses"] = [
        {"id": "wamid.ABC", "status": "delivered", "timestamp": "1786470000"}
    ]

    batch = parse_webhook(payload)

    assert batch.messages == []
    assert batch.statuses[0].external_message_id == "wamid.ABC"
    assert batch.statuses[0].state == "delivered"
