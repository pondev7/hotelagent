"""Domain errors, and the single place they become HTTP.

`CLAUDE.md`: *"raise `HotelAgentError` subclasses from services; the API layer
maps them to HTTP. Never raise `HTTPException` below `router.py`."*

The rule exists because a service is not a web handler. `check_availability` is
called from an HTTP request today, from the arq worker when a call task times
out, and from a management command when an operator fixes something by hand. A
service that raises `HTTPException` forces the other two callers to import a web
framework and read a status code off an exception to find out what went wrong.

So the meaning is chosen at the raise site and the transport is derived from it.
A service author picks the class whose name describes the situation; nobody
downstream chooses a status code ever again.

Two things travel with every error:

- `code` — a stable slug the console branches on. Deliberately not the class
  name, so renaming a Python class is not a breaking change for the frontend.
- `detail` — optional structure for the UI to render. The `message` is for a
  human reading a log; `detail` is what lets the call-task queue say "already
  claimed by Ravi" in its own words and its own language.
"""

from typing import Any, ClassVar

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from hotelagent.logging import get_logger

log = get_logger(__name__)


class HotelAgentError(Exception):
    """Base for every error this system raises on purpose.

    The default is 500 and not 400. An error nobody has classified is our fault
    until proven otherwise — defaulting to a client error would report our
    unhandled conditions as the console's bugs, and they would be investigated
    in the wrong place.
    """

    status_code: ClassVar[int] = 500
    code: ClassVar[str] = "internal_error"

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def envelope(self) -> dict[str, Any]:
        """The response body. One shape for every failure — see `ErrorEnvelope`."""
        return {"error": {"code": self.code, "message": self.message, "detail": self.detail}}


class NotFoundError(HotelAgentError):
    """The thing asked for does not exist, or does not exist *for this caller*.

    That second clause is load-bearing. A row belonging to another city is
    reported as absent rather than forbidden: 403 would confirm it exists, and
    that confirmation is itself the tenancy leak invariant #1 guards against.
    """

    status_code = 404
    code = "not_found"


class InvalidRequestError(HotelAgentError):
    """The request is malformed or self-contradictory."""

    status_code = 422
    code = "invalid_request"


class PermissionDeniedError(HotelAgentError):
    """The caller is known and is not allowed to do this."""

    status_code = 403
    code = "permission_denied"


class ConflictError(HotelAgentError):
    """The request was fine; the state of the world refuses it.

    Two operators claiming one call task, a booking whose room went while the
    console was open. Not a 422 — there is no field to highlight, and telling
    the console otherwise makes it draw a validation error against a form the
    operator filled in correctly.
    """

    status_code = 409
    code = "conflict"


class UpstreamError(HotelAgentError):
    """A service we depend on failed. WhatsApp, a payment gateway, an LLM.

    Distinct from `ConfigurationError` because the operational response differs:
    this one is retried and watched, that one is fixed by a deploy.
    """

    status_code = 502
    code = "upstream_unavailable"


class ConfigurationError(HotelAgentError):
    """We cannot do the job because we are not set up to.

    A missing environment variable, an unseeded city. 503 rather than 500: the
    request would have succeeded against a correctly configured system, so it is
    honest to signal "not now" instead of "not ever".
    """

    status_code = 503
    code = "not_configured"


# --------------------------------------------------------------------------
# The published shape
# --------------------------------------------------------------------------


class ErrorBody(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] | None = None


class ErrorEnvelope(BaseModel):
    """Every non-2xx response, without exception.

    Declared as a Pydantic model rather than assembled ad hoc so it lands in the
    OpenAPI document, and from there in `packages/contracts/`. Without a *type*
    for failure the generated client types the happy path and leaves error
    handling to `any` — which is how a 409 becomes a blank screen.
    """

    error: ErrorBody


# Attached to every console route so the schema documents the failure shape.
# FastAPI would otherwise publish its own `HTTPValidationError` for 422, which
# is a second error type the console would have to understand.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorEnvelope, "description": "Absent, or not visible to this city."},
    409: {"model": ErrorEnvelope, "description": "Refused by the current state."},
    422: {"model": ErrorEnvelope, "description": "The request did not validate."},
}


# --------------------------------------------------------------------------
# Translation
# --------------------------------------------------------------------------


async def _handle_domain_error(request: Request, exc: Exception) -> Response:
    """Turn a raised `HotelAgentError` into its response.

    Typed as `Exception` because that is the signature Starlette's handler
    registry declares; narrowing here rather than in the annotation keeps mypy
    strict happy without a cast.
    """
    if not isinstance(exc, HotelAgentError):  # pragma: no cover - registry guarantees the type
        raise exc

    # 5xx is ours to fix and belongs at error level; 4xx is the ordinary traffic
    # of an API and would drown the logs. Note what is *not* logged: the message
    # may name a hotel or a conversation, never a body or a full phone number.
    event = "http.server_error" if exc.status_code >= 500 else "http.client_error"
    logger = log.error if exc.status_code >= 500 else log.info
    logger(event, code=exc.code, status=exc.status_code, path=request.url.path)

    return JSONResponse(status_code=exc.status_code, content=exc.envelope())


async def _handle_validation_error(request: Request, exc: Exception) -> Response:
    """Give FastAPI's own validation failures our envelope.

    Out of the box this returns `{"detail": [...]}` — a different shape, from a
    layer we do not control. Overriding it is the whole point: the console
    should not be able to tell which layer refused it, and the generated client
    can then expose exactly one typed failure.
    """
    if not isinstance(exc, RequestValidationError):  # pragma: no cover - registry guarantees it
        raise exc

    error = InvalidRequestError(
        "the request did not validate",
        detail={"fields": jsonable_encoder(exc.errors())},
    )
    log.info("http.client_error", code=error.code, status=422, path=request.url.path)
    return JSONResponse(status_code=error.status_code, content=error.envelope())


def install_error_handlers(app: FastAPI) -> None:
    """Wire both handlers onto an app.

    One function rather than two decorators at the call site, so a second app —
    a test harness, a future admin surface — cannot install half of the
    contract and produce two error shapes.
    """
    app.add_exception_handler(HotelAgentError, _handle_domain_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
