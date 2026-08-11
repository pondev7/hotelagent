"""S04's exit criterion, end to end.

A webhook POST with a valid signature persists exactly one normalised message.
The same payload delivered three times still persists one. A body with a bad
signature returns 403 and persists nothing.
"""

import hashlib
import hmac
import json
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.config import get_settings
from hotelagent.enums import Channel, MessageType
from hotelagent.modules.conversation.models import Conversation, Message, User

APP_SECRET = "test-app-secret"
VERIFY_TOKEN = "test-verify-token"


def _cloud_api_payload(message_id: str = "wamid.TEST1", text: str = "Need a room") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "PN-1"},
                            "contacts": [{"wa_id": "919812345678", "profile": {"name": "Anu"}}],
                            "messages": [
                                {
                                    "from": "919812345678",
                                    "id": message_id,
                                    "timestamp": "1786470000",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _signed(body: bytes, secret: str = APP_SECRET) -> dict[str, str]:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return {"X-Hub-Signature-256": f"sha256={digest}", "Content-Type": "application/json"}


@pytest.fixture
def cloud_api_mode(settings_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOTELAGENT_CHANNEL_ADAPTER", "cloud_api")
    monkeypatch.setenv("HOTELAGENT_WHATSAPP_APP_SECRET", APP_SECRET)
    monkeypatch.setenv("HOTELAGENT_WHATSAPP_VERIFY_TOKEN", VERIFY_TOKEN)
    get_settings.cache_clear()


async def _count(session: AsyncSession, model: Any) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_a_signed_delivery_persists_one_normalised_message(
    client: httpx.AsyncClient, session: AsyncSession, seeded_city: uuid.UUID, cloud_api_mode: None
) -> None:
    body = json.dumps(_cloud_api_payload()).encode()

    response = await client.post("/webhooks/whatsapp", content=body, headers=_signed(body))

    assert response.status_code == 200
    assert response.json() == {"received": 1, "duplicates": 0}

    message = await session.scalar(select(Message))
    assert message is not None
    assert message.body == "Need a room"
    assert message.message_type is MessageType.TEXT
    assert message.external_id == "wamid.TEST1"
    assert message.city_id == seeded_city, "invariant #1: every row carries the tenancy key"

    user = await session.scalar(select(User))
    assert user is not None
    assert user.external_id == "919812345678"
    assert user.display_name == "Anu"
    assert user.channel is Channel.WHATSAPP

    conversation = await session.scalar(select(Conversation))
    assert conversation is not None
    assert conversation.first_inbound_at is not None
    assert conversation.service_window_expires_at is not None, "24-hour window recorded"


async def test_redelivery_persists_exactly_one_message(
    client: httpx.AsyncClient, session: AsyncSession, seeded_city: uuid.UUID, cloud_api_mode: None
) -> None:
    """The exit criterion. WhatsApp redelivers whenever our 200 was slow."""
    body = json.dumps(_cloud_api_payload()).encode()
    headers = _signed(body)

    first = await client.post("/webhooks/whatsapp", content=body, headers=headers)
    second = await client.post("/webhooks/whatsapp", content=body, headers=headers)
    third = await client.post("/webhooks/whatsapp", content=body, headers=headers)

    assert first.json() == {"received": 1, "duplicates": 0}
    assert second.json() == {"received": 1, "duplicates": 1}
    assert third.json() == {"received": 1, "duplicates": 1}

    assert await _count(session, Message) == 1
    assert await _count(session, User) == 1
    assert await _count(session, Conversation) == 1


async def test_an_invalid_signature_is_rejected_and_persists_nothing(
    client: httpx.AsyncClient, session: AsyncSession, seeded_city: uuid.UUID, cloud_api_mode: None
) -> None:
    body = json.dumps(_cloud_api_payload()).encode()

    response = await client.post(
        "/webhooks/whatsapp", content=body, headers=_signed(body, "wrong-secret")
    )

    assert response.status_code == 403
    assert await _count(session, Message) == 0


async def test_a_tampered_body_is_rejected(
    client: httpx.AsyncClient, session: AsyncSession, seeded_city: uuid.UUID, cloud_api_mode: None
) -> None:
    """Sign one body, send another — the attack the signature exists to stop."""
    body = json.dumps(_cloud_api_payload()).encode()
    headers = _signed(body)
    tampered = json.dumps(_cloud_api_payload(text="Free room please")).encode()

    response = await client.post("/webhooks/whatsapp", content=tampered, headers=headers)

    assert response.status_code == 403
    assert await _count(session, Message) == 0


async def test_a_missing_signature_is_rejected(
    client: httpx.AsyncClient, session: AsyncSession, seeded_city: uuid.UUID, cloud_api_mode: None
) -> None:
    body = json.dumps(_cloud_api_payload()).encode()

    response = await client.post(
        "/webhooks/whatsapp", content=body, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 403
    assert await _count(session, Message) == 0


async def test_two_messages_in_one_delivery_are_both_stored(
    client: httpx.AsyncClient, session: AsyncSession, seeded_city: uuid.UUID, cloud_api_mode: None
) -> None:
    payload = _cloud_api_payload()
    payload["entry"][0]["changes"][0]["value"]["messages"].append(
        {
            "from": "919812345678",
            "id": "wamid.TEST2",
            "timestamp": "1786470005",
            "type": "text",
            "text": {"body": "sea view if possible"},
        }
    )
    body = json.dumps(payload).encode()

    response = await client.post("/webhooks/whatsapp", content=body, headers=_signed(body))

    assert response.json() == {"received": 2, "duplicates": 0}
    assert await _count(session, Message) == 2
    assert await _count(session, Conversation) == 1, "both turns join one thread"


async def test_the_subscription_handshake_echoes_the_challenge(
    client: httpx.AsyncClient, cloud_api_mode: None
) -> None:
    response = await client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "1158201444",
        },
    )

    assert response.status_code == 200
    assert response.text == "1158201444"


async def test_the_subscription_handshake_rejects_a_wrong_token(
    client: httpx.AsyncClient, cloud_api_mode: None
) -> None:
    response = await client.get(
        "/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "1158201444",
        },
    )

    assert response.status_code == 403


async def test_the_console_adapter_needs_no_signature(
    client: httpx.AsyncClient, session: AsyncSession, seeded_city: uuid.UUID
) -> None:
    """The whole flow is exercisable with no Meta account and no public URL,
    which is what unblocks this slice from the BSP-versus-Cloud-API decision."""
    response = await client.post(
        "/webhooks/whatsapp", json={"from": "dev-anu", "text": "hello from the console"}
    )

    assert response.status_code == 200
    assert response.json()["received"] == 1

    message = await session.scalar(select(Message))
    assert message is not None
    assert message.body == "hello from the console"


async def test_a_missing_city_is_reported_not_silently_dropped(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    """No `seeded_city` fixture here. Every conversation needs a city_id
    (invariant #1), so the gateway must refuse rather than invent one."""
    response = await client.post("/webhooks/whatsapp", json={"from": "dev", "text": "hi"})

    assert response.status_code == 503
    assert await _count(session, Message) == 0


async def test_an_unparseable_body_does_not_trigger_a_retry_loop(
    client: httpx.AsyncClient, seeded_city: uuid.UUID
) -> None:
    """Meta redelivers on any non-2xx. A body we can never parse would loop
    forever, so it is accepted and dropped."""
    response = await client.post(
        "/webhooks/whatsapp", content=b"{not json", headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 200
    assert response.json() == {"received": 0, "duplicates": 0}
