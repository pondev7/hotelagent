"""Webhook endpoints.

Thin by rule: parse, call `service.py`, serialise. No business logic and no ORM
queries here. `HTTPException` is raised only at this layer — services signal
failure by raising their own errors or returning values.

**On the Meta-specific names in this file.** `X-Hub-Signature-256` and the
`hub.*` query parameters are Meta's, and they appear here rather than in
`adapters/`. That is deliberate, not a leak of invariant #2: the route is
`/webhooks/whatsapp`, a provider-specific endpoint, and each provider's
handshake and header conventions differ enough that a second channel wants its
own route rather than a contorted shared one. What invariant #2 forbids is the
provider's *message shape* travelling inwards — and it does not. Everything
past `service.parse_payload` is `InboundMessage`.
"""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from hotelagent.db.session import get_session
from hotelagent.modules.channel import service

router = APIRouter(prefix="/webhooks", tags=["channel"])


@router.get("/whatsapp", response_class=PlainTextResponse)
async def verify_webhook_subscription(
    mode: Annotated[str | None, Query(alias="hub.mode")] = None,
    token: Annotated[str | None, Query(alias="hub.verify_token")] = None,
    challenge: Annotated[str | None, Query(alias="hub.challenge")] = None,
) -> str:
    """Meta's one-time subscription handshake.

    Meta GETs this URL with a token; echo the challenge back verbatim to prove
    the endpoint is ours. The odd `hub.` parameter names are Meta's.
    """
    result = service.verify_subscription(mode=mode, token=token, challenge=challenge)
    if result is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="verification failed")
    return result


@router.post("/whatsapp", status_code=status.HTTP_200_OK)
async def receive_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    signature: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
) -> dict[str, Any]:
    """Receive a delivery.

    The raw body is read *before* parsing, because the signature covers the
    exact bytes sent — parsing and re-serialising would change whitespace and
    key order and never match again.
    """
    raw_body = await request.body()

    if not service.verify_inbound_signature(raw_body=raw_body, header=signature):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid signature")

    try:
        payload = json.loads(raw_body or b"{}")
    except json.JSONDecodeError:
        # A body we cannot parse is not worth retrying, and Meta redelivers on
        # any non-2xx. Accept it and move on rather than inviting a retry loop.
        return {"received": 0, "duplicates": 0, "statuses": 0}

    if not isinstance(payload, dict):
        return {"received": 0, "duplicates": 0, "statuses": 0}

    batch = service.parse_payload(payload)

    # Receipts first: they refer to messages we already sent, and applying them
    # does not depend on anything the inbound messages do.
    applied = await service.handle_statuses(session, batch)

    if not batch.messages:
        return {"received": 0, "duplicates": 0, "statuses": applied}

    try:
        recorded = await service.handle_inbound(session, batch)
    except service.ChannelConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    return {
        "received": len(recorded),
        "duplicates": sum(1 for r in recorded if r.is_duplicate),
        "statuses": applied,
    }
