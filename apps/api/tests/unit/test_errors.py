"""The error contract.

`CLAUDE.md`: *"raise `HotelAgentError` subclasses from services; the API layer
maps them to HTTP. Never raise `HTTPException` below `router.py`."*

Until now there was no such base class. Five slices grew five private
hierarchies — `ChannelError`, `UnknownHotelError`, `UnknownCallTaskError`, each
inheriting `RuntimeError` — and the one router we have translates them by hand
in an `except` clause. That does not scale to four modules' worth of endpoints:
every new route re-decides what "this row does not exist" means, and the console
gets a different error shape from each one.

These tests move the decision to the raise site. The status code and the
machine-readable `code` become properties of the exception class, so a service
author chooses the meaning once and no router ever chooses again.

The single-envelope tests matter more than they look. A generated TypeScript
client can only have one error type; if a 404 from our code and a 422 from
FastAPI's own validation have different bodies, every call site in the console
needs two failure paths.
"""

import pytest
from fastapi import FastAPI

from hotelagent.errors import (
    ConfigurationError,
    ConflictError,
    HotelAgentError,
    InvalidRequestError,
    NotFoundError,
    PermissionDeniedError,
    UpstreamError,
    install_error_handlers,
)

# Importing these registers their subclasses, which is what makes the
# whole-hierarchy tests below see the module-specific errors at all.
from hotelagent.modules.availability import service as availability_service
from hotelagent.modules.channel import service as channel_service

# The transport meaning of each base class. This table is the contract: a
# service author picks a row, and the HTTP status follows.
STATUS_BY_CLASS: dict[type[HotelAgentError], int] = {
    NotFoundError: 404,
    InvalidRequestError: 422,
    PermissionDeniedError: 403,
    ConflictError: 409,
    UpstreamError: 502,
    ConfigurationError: 503,
}


def _all_subclasses(root: type[HotelAgentError]) -> set[type[HotelAgentError]]:
    found: set[type[HotelAgentError]] = set()
    for subclass in root.__subclasses__():
        found.add(subclass)
        found |= _all_subclasses(subclass)
    return found


@pytest.mark.parametrize(("error_class", "status"), list(STATUS_BY_CLASS.items()))
def test_each_base_class_carries_its_transport_meaning(
    error_class: type[HotelAgentError], status: int
) -> None:
    assert error_class.status_code == status


def test_the_base_error_is_a_server_error() -> None:
    """An error nobody classified is our fault until proven otherwise.

    Defaulting the base class to 400 would be worse than useless: it would tell
    the console "you sent something wrong" about what is actually an unhandled
    condition on our side, and the bug would be reported as a client bug.
    """
    assert HotelAgentError.status_code == 500


def test_every_error_has_a_usable_status_code() -> None:
    for error_class in _all_subclasses(HotelAgentError):
        assert 400 <= error_class.status_code <= 599, (
            f"{error_class.__name__} has status_code {error_class.status_code}"
        )


def test_every_error_code_is_a_stable_slug() -> None:
    """`code` is what the console branches on, so it is part of the API.

    Snake case rather than the class name: the console should not have to know
    our Python identifiers, and renaming a class must not be a breaking change
    for the frontend.
    """
    for error_class in _all_subclasses(HotelAgentError) | {HotelAgentError}:
        code = error_class.code
        assert code, f"{error_class.__name__} has no code"
        assert code == code.lower(), f"{error_class.__name__}: {code!r} is not lower case"
        assert " " not in code and "-" not in code, f"{error_class.__name__}: {code!r}"


def test_no_two_errors_share_a_code() -> None:
    """Two classes with one code makes the console's switch statement a lie.

    This is also what forces a module error to name itself: a
    `UnknownHotelError` that silently inherits `not_found` from its parent
    collides with every other unnamed 404 and fails here.
    """
    by_code: dict[str, list[str]] = {}
    for error_class in _all_subclasses(HotelAgentError) | {HotelAgentError}:
        by_code.setdefault(error_class.code, []).append(error_class.__name__)

    collisions = {code: names for code, names in by_code.items() if len(names) > 1}
    assert not collisions, f"duplicate error codes: {collisions}"


def test_the_envelope_is_the_only_error_shape() -> None:
    """One body for every failure, whatever raised it."""
    error = NotFoundError("hotel 1234 does not exist")

    assert error.envelope() == {
        "error": {
            "code": "not_found",
            "message": "hotel 1234 does not exist",
            "detail": None,
        }
    }


def test_detail_carries_structure_the_console_can_render() -> None:
    """A message is for a human; `detail` is for the UI.

    The call-task queue wants to say "this task is already claimed by Ravi" in
    its own words and its own language, which it can only do from fields.
    """
    error = ConflictError("call task already claimed", detail={"assigned_to": "ravi"})

    assert error.envelope()["error"]["detail"] == {"assigned_to": "ravi"}
    assert str(error) == "call task already claimed"


def test_the_handlers_are_installed_on_a_bare_app() -> None:
    """Installing is one call, so a second FastAPI app cannot forget half of it.

    `RequestValidationError` is included deliberately. FastAPI's default body
    for it is `{"detail": [...]}` — a different shape from ours, produced by a
    layer we do not control, and the reason to override it is precisely that we
    do not want the console to know that layer exists.
    """
    from fastapi.exceptions import RequestValidationError

    app = FastAPI()
    install_error_handlers(app)

    assert HotelAgentError in app.exception_handlers
    assert RequestValidationError in app.exception_handlers


def test_the_real_app_installs_them() -> None:
    from hotelagent.main import app

    assert HotelAgentError in app.exception_handlers


@pytest.mark.parametrize(
    ("error_class", "status"),
    [
        (channel_service.ChannelConfigurationError, 503),
        (channel_service.UnknownConversationError, 404),
        (channel_service.ServiceWindowExpiredError, 409),
        (availability_service.UnknownHotelError, 404),
        (availability_service.UnknownCallTaskError, 404),
    ],
)
def test_the_errors_the_earlier_slices_invented_now_join_the_hierarchy(
    error_class: type[HotelAgentError], status: int
) -> None:
    """The retrofit, stated as a test.

    Each of these is currently a bare `RuntimeError` subclass that one router
    translates in an `except` clause. Re-parenting them is the whole point of
    the slice — a service raising `UnknownHotelError` from a worker, a CLI or a
    web request should not need three different callers to know it means 404.

    Note `ServiceWindowExpiredError` is a 409 and not a 422: the request was
    perfectly well formed, and the reason we cannot send is the state of the
    world (`docs/vision.md` §3.8). A 422 would invite the console to highlight
    a field.
    """
    assert issubclass(error_class, HotelAgentError)
    assert error_class.status_code == status
