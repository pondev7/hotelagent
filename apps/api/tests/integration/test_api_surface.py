"""The console's API, over real HTTP against a real database.

Two things are being specified here, and only one of them is "the endpoints
work".

The other is tenancy. `test_openapi_contract.py` proves every list endpoint
*asks* for a `city_id`; these tests prove it is actually applied to the query.
Both halves are needed — a required parameter the service then ignores is worse
than no parameter at all, because the schema now documents a guarantee that does
not hold.

Note what a cross-city read returns: 404, not 403. A 403 confirms the row
exists, which is itself the leak — "no such hotel" is the only answer that tells
an operator in Kanyakumari nothing whatsoever about Madurai's directory.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.enums import Channel, IntegrationTier, MessageType, SenderKind
from hotelagent.errors import NotFoundError
from hotelagent.modules.conversation.models import (
    Conversation,
    ConversationState,
    Message,
    MessageDirection,
    User,
)
from hotelagent.modules.inventory.models import City, Hotel
from hotelagent.modules.ops.models import CallTask, CallTaskStatus

SATURDAY = date(2026, 8, 15)
NOON = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


async def _city(session: AsyncSession, *, name: str, slug: str) -> uuid.UUID:
    city = City(name=name, slug=slug)
    session.add(city)
    await session.flush()
    return city.id


async def _hotel(
    session: AsyncSession,
    city_id: uuid.UUID,
    *,
    name: str = "Sea Breeze Residency",
    tier: IntegrationTier = IntegrationTier.MANUAL,
) -> uuid.UUID:
    hotel = Hotel(
        city_id=city_id,
        name=name,
        integration_tier=tier,
        reception_phone="+919800000000",
    )
    session.add(hotel)
    await session.flush()
    return hotel.id


async def _conversation(
    session: AsyncSession,
    city_id: uuid.UUID,
    *,
    external_id: str,
    state: ConversationState = ConversationState.ACTIVE,
    last_inbound_at: datetime = NOON,
) -> uuid.UUID:
    user = User(channel=Channel.WHATSAPP, external_id=external_id, display_name="Traveller")
    session.add(user)
    await session.flush()

    conversation = Conversation(
        city_id=city_id,
        user_id=user.id,
        channel=Channel.WHATSAPP,
        state=state,
        last_inbound_at=last_inbound_at,
    )
    session.add(conversation)
    await session.flush()
    return conversation.id


async def _message(
    session: AsyncSession,
    city_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    body: str,
    sent_at: datetime,
    direction: MessageDirection = MessageDirection.INBOUND,
) -> uuid.UUID:
    message = Message(
        city_id=city_id,
        conversation_id=conversation_id,
        direction=direction,
        sender_kind=SenderKind.CUSTOMER
        if direction is MessageDirection.INBOUND
        else SenderKind.OPERATOR,
        message_type=MessageType.TEXT,
        body=body,
        sent_at=sent_at,
    )
    session.add(message)
    await session.flush()
    return message.id


async def _call_task(
    session: AsyncSession,
    city_id: uuid.UUID,
    hotel_id: uuid.UUID,
    *,
    status: CallTaskStatus = CallTaskStatus.OPEN,
    opened_at: datetime = NOON,
) -> uuid.UUID:
    task = CallTask(
        city_id=city_id,
        hotel_id=hotel_id,
        check_in=SATURDAY,
        check_out=SATURDAY + timedelta(days=1),
        guests=2,
        status=status,
        opened_at=opened_at,
    )
    session.add(task)
    await session.flush()
    return task.id


# --------------------------------------------------------------------------
# Tenancy
# --------------------------------------------------------------------------


async def test_the_hotel_directory_shows_one_city_only(
    session: AsyncSession, seeded_city: uuid.UUID, client: httpx.AsyncClient
) -> None:
    """Invariant #1, applied rather than merely declared."""
    other_city = await _city(session, name="Madurai", slug="madurai")
    await _hotel(session, seeded_city, name="Sea Breeze Residency")
    await _hotel(session, other_city, name="Meenakshi Lodge")

    response = await client.get("/api/hotels", params={"city_id": str(seeded_city)})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["name"] for item in body["items"]] == ["Sea Breeze Residency"]
    assert body["items"][0]["city_id"] == str(seeded_city)


async def test_a_hotel_in_another_city_reads_as_absent(
    session: AsyncSession, seeded_city: uuid.UUID, client: httpx.AsyncClient
) -> None:
    """404 rather than 403 — see the module docstring."""
    other_city = await _city(session, name="Madurai", slug="madurai")
    hotel_id = await _hotel(session, other_city, name="Meenakshi Lodge")

    response = await client.get(f"/api/hotels/{hotel_id}", params={"city_id": str(seeded_city)})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "unknown_hotel"


async def test_conversations_are_scoped_to_a_city(
    session: AsyncSession, seeded_city: uuid.UUID, client: httpx.AsyncClient
) -> None:
    other_city = await _city(session, name="Madurai", slug="madurai")
    await _conversation(session, seeded_city, external_id="919800000001")
    await _conversation(session, other_city, external_id="919800000002")

    response = await client.get("/api/conversations", params={"city_id": str(seeded_city)})

    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_another_citys_transcript_is_not_readable(
    session: AsyncSession, seeded_city: uuid.UUID, client: httpx.AsyncClient
) -> None:
    """The nested-collection scoping check, with teeth.

    A conversation id is a UUID the operator never has a legitimate reason to
    hold across cities. Guessing one should not be enough, and neither should
    finding one in a log or a screenshot.
    """
    other_city = await _city(session, name="Madurai", slug="madurai")
    conversation_id = await _conversation(session, other_city, external_id="919800000002")
    await _message(session, other_city, conversation_id, body="vanakkam", sent_at=NOON)

    response = await client.get(
        f"/api/conversations/{conversation_id}/messages",
        params={"city_id": str(seeded_city)},
    )

    assert response.status_code == 404


async def test_the_call_task_queue_is_scoped_to_a_city(
    session: AsyncSession, seeded_city: uuid.UUID, client: httpx.AsyncClient
) -> None:
    other_city = await _city(session, name="Madurai", slug="madurai")
    await _call_task(session, seeded_city, await _hotel(session, seeded_city))
    await _call_task(session, other_city, await _hotel(session, other_city, name="Meenakshi"))

    response = await client.get("/api/call-tasks", params={"city_id": str(seeded_city)})

    assert response.status_code == 200
    assert response.json()["total"] == 1


# --------------------------------------------------------------------------
# Pagination and ordering
# --------------------------------------------------------------------------


async def test_a_page_reports_the_total_beyond_it(
    session: AsyncSession, seeded_city: uuid.UUID, client: httpx.AsyncClient
) -> None:
    """`total` is the count of matching rows, not the count returned.

    The console needs it to render "showing 2 of 3" and to decide whether to
    draw a next-page control at all. Returning the page length instead is the
    classic version of this bug, and it only shows up once there is a second
    page — which in a five-hotel city means it shows up in production.
    """
    for index in range(3):
        await _hotel(session, seeded_city, name=f"Hotel {index}")

    first = await client.get(
        "/api/hotels", params={"city_id": str(seeded_city), "limit": 2, "offset": 0}
    )
    second = await client.get(
        "/api/hotels", params={"city_id": str(seeded_city), "limit": 2, "offset": 2}
    )

    assert first.status_code == 200
    assert first.json()["total"] == 3
    assert first.json()["limit"] == 2
    assert first.json()["offset"] == 0
    assert len(first.json()["items"]) == 2

    assert len(second.json()["items"]) == 1
    assert second.json()["total"] == 3

    seen = [item["hotel_id"] for item in first.json()["items"] + second.json()["items"]]
    assert len(set(seen)) == 3, "the two pages overlap — the ordering is not deterministic"


async def test_an_oversized_limit_is_refused(
    seeded_city: uuid.UUID, client: httpx.AsyncClient
) -> None:
    """A cap, so no caller can ask for the whole table by accident.

    `?limit=100000` from a console bug is a slow query, a large JSON encode and
    a browser tab that stops responding. Refusing it is cheaper than surviving
    it.
    """
    response = await client.get(
        "/api/hotels", params={"city_id": str(seeded_city), "limit": 10_000}
    )

    assert response.status_code == 422


async def test_a_transcript_reads_oldest_first(
    session: AsyncSession, seeded_city: uuid.UUID, client: httpx.AsyncClient
) -> None:
    """Chronological, because it is a conversation.

    The inbox lists conversations newest-first and the messages inside one
    oldest-first. Those orderings genuinely differ, which is why both are
    pinned here rather than left to whatever the database returns.
    """
    conversation_id = await _conversation(session, seeded_city, external_id="919800000001")
    await _message(session, seeded_city, conversation_id, body="second", sent_at=NOON)
    await _message(
        session,
        seeded_city,
        conversation_id,
        body="first",
        sent_at=NOON - timedelta(minutes=5),
    )

    response = await client.get(
        f"/api/conversations/{conversation_id}/messages",
        params={"city_id": str(seeded_city)},
    )

    assert response.status_code == 200
    assert [item["body"] for item in response.json()["items"]] == ["first", "second"]


async def test_the_inbox_lists_the_most_recent_conversation_first(
    session: AsyncSession, seeded_city: uuid.UUID, client: httpx.AsyncClient
) -> None:
    """Because the response-time contract is the product (`docs/vision.md` §2.2).

    An operator working top-down must be working the person who has been
    waiting on us, not the oldest thread in the city.
    """
    await _conversation(
        session,
        seeded_city,
        external_id="919800000001",
        last_inbound_at=NOON - timedelta(hours=2),
    )
    recent = await _conversation(
        session, seeded_city, external_id="919800000002", last_inbound_at=NOON
    )

    response = await client.get("/api/conversations", params={"city_id": str(seeded_city)})

    assert response.status_code == 200
    assert response.json()["items"][0]["conversation_id"] == str(recent)


async def test_the_queue_lists_the_longest_waiting_call_first(
    session: AsyncSession, seeded_city: uuid.UUID, client: httpx.AsyncClient
) -> None:
    """The opposite order, and deliberately so.

    A call task is a promise already made to a traveller who was told five
    minutes. Newest-first on this queue means the person who has waited longest
    waits longest.
    """
    hotel_id = await _hotel(session, seeded_city)
    oldest = await _call_task(
        session, seeded_city, hotel_id, opened_at=NOON - timedelta(minutes=10)
    )
    await _call_task(session, seeded_city, hotel_id, opened_at=NOON)

    response = await client.get("/api/call-tasks", params={"city_id": str(seeded_city)})

    assert response.status_code == 200
    assert response.json()["items"][0]["call_task_id"] == str(oldest)


# --------------------------------------------------------------------------
# Filtering
# --------------------------------------------------------------------------


async def test_conversations_filter_by_state(
    session: AsyncSession, seeded_city: uuid.UUID, client: httpx.AsyncClient
) -> None:
    active = await _conversation(session, seeded_city, external_id="919800000001")
    await _conversation(
        session, seeded_city, external_id="919800000002", state=ConversationState.CLOSED
    )

    response = await client.get(
        "/api/conversations", params={"city_id": str(seeded_city), "state": "active"}
    )

    assert response.status_code == 200
    assert [item["conversation_id"] for item in response.json()["items"]] == [str(active)]


async def test_call_tasks_filter_by_status(
    session: AsyncSession, seeded_city: uuid.UUID, client: httpx.AsyncClient
) -> None:
    """The queue an operator works is `open` plus `claimed`, never `resolved`.

    Left unfiltered, this endpoint becomes slower every day the desk operates
    while the screen it feeds shows the same handful of rows.
    """
    hotel_id = await _hotel(session, seeded_city)
    open_task = await _call_task(session, seeded_city, hotel_id)
    await _call_task(session, seeded_city, hotel_id, status=CallTaskStatus.RESOLVED)

    response = await client.get(
        "/api/call-tasks", params={"city_id": str(seeded_city), "status": "open"}
    )

    assert response.status_code == 200
    assert [item["call_task_id"] for item in response.json()["items"]] == [str(open_task)]


async def test_an_unknown_state_is_a_validation_error(
    seeded_city: uuid.UUID, client: httpx.AsyncClient
) -> None:
    """Filters are enums, not free text.

    `?state=activee` silently matching nothing is a support ticket about missing
    conversations. Rejecting it is the difference between a typo and a mystery.
    """
    response = await client.get(
        "/api/conversations", params={"city_id": str(seeded_city), "state": "activee"}
    )

    assert response.status_code == 422


# --------------------------------------------------------------------------
# Error mapping
# --------------------------------------------------------------------------


async def test_a_missing_city_id_is_refused_in_our_envelope(
    client: httpx.AsyncClient,
) -> None:
    """FastAPI's own validation failures wear our error shape.

    Out of the box this returns `{"detail": [...]}`, a second error format the
    console would have to understand. One envelope for every non-2xx is what
    lets the generated client expose a single typed failure.
    """
    response = await client.get("/api/hotels")

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["message"]


async def test_a_domain_error_reaches_the_client_as_its_own_status(
    seeded_city: uuid.UUID, client: httpx.AsyncClient
) -> None:
    """`UnknownHotelError` is raised in a service and translated once.

    No `except` clause in the router, no status code chosen at the transport
    layer — the whole argument of `errors.py` in one request.
    """
    response = await client.get(f"/api/hotels/{uuid.uuid4()}", params={"city_id": str(seeded_city)})

    assert response.status_code == 404

    error = response.json()["error"]
    assert set(error) == {"code", "message", "detail"}
    assert error["code"] == "unknown_hotel"


async def test_replying_on_an_unknown_conversation_raises_a_typed_error(
    session: AsyncSession,
) -> None:
    """The last bare `ValueError` in a service, retyped.

    `conversation.record_outbound` currently raises `ValueError` for a
    conversation that does not exist, which no caller can distinguish from a
    programming mistake. As a `NotFoundError` it means exactly one thing, and
    the API maps it without knowing which module raised it.
    """
    from hotelagent.modules.conversation import service as conversation_service

    with pytest.raises(NotFoundError):
        await conversation_service.record_outbound(
            session,
            conversation_id=uuid.uuid4(),
            sender_kind=SenderKind.OPERATOR,
            text="hello",
        )
