"""S07's exit criterion, read off the schema.

*"`make contracts` produces TypeScript that compiles, and every list endpoint is
`city_id`-scoped."*

The second half is the interesting one. Invariant #1 puts `city_id` on every
row, which stops the *database* from being un-tenantable — but a query that
never filters on it makes the column decorative. One forgotten `WHERE city_id =`
in a list endpoint is how a console shows one city's operator another city's
conversations, and it is invisible in review because the endpoint looks fine.

So the rule is enforced against the generated OpenAPI document rather than
against our source: whatever the router does internally, it cannot answer a
collection request without being told which city is asking.

These tests read `app.openapi()` and need no database — the schema is derived
from the type annotations, which is the whole argument for generating the
frontend's types from it instead of writing them twice.
"""

from typing import Any

import pytest

from hotelagent.main import app

# Everything the console consumes lives under this prefix. `/webhooks` and
# `/health` are not part of the generated client.
CONSOLE_PREFIX = "/api"

# The pagination envelope, identified by shape rather than by name: FastAPI
# derives component names from the generic alias (`Page_HotelSummary_`), and a
# test that matched on that string would break the day we rename the model.
PAGE_MARKERS = frozenset({"items", "total", "limit", "offset"})


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    """The OpenAPI document.

    `app.openapi()` raising is itself a failure worth having a test for — an
    un-serialisable response annotation (a bare ORM class, a type FastAPI
    cannot resolve) breaks `make contracts` and nothing else, so it would
    otherwise be discovered by the frontend build.
    """
    return app.openapi()


def _resolve(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    """Follow a `$ref` one hop into `components.schemas`."""
    ref = node.get("$ref")
    if not ref:
        return node
    name = ref.rsplit("/", 1)[-1]
    resolved: dict[str, Any] = schema.get("components", {}).get("schemas", {}).get(name, {})
    return resolved


def _operations(schema: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (path, method, operation)
        for path, methods in schema["paths"].items()
        for method, operation in methods.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]


def _list_operations(schema: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Every operation that returns a page of things."""
    found = []
    for path, method, operation in _operations(schema):
        if not path.startswith(CONSOLE_PREFIX):
            continue
        content = operation.get("responses", {}).get("200", {}).get("content", {})
        body = content.get("application/json", {}).get("schema", {})
        properties = _resolve(schema, body).get("properties", {})
        if set(properties) >= PAGE_MARKERS:
            found.append((path, method, operation))
    return found


def _query_parameters(operation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        parameter["name"]: parameter
        for parameter in operation.get("parameters", [])
        if parameter.get("in") == "query"
    }


def test_the_console_api_exists(schema: dict[str, Any]) -> None:
    """The four resources S07 promises, plus the city list S08 added."""
    paths = set(schema["paths"])

    assert "/api/cities" in paths
    assert "/api/hotels" in paths
    assert "/api/hotels/{hotel_id}" in paths
    assert "/api/conversations" in paths
    assert "/api/conversations/{conversation_id}/messages" in paths
    assert "/api/call-tasks" in paths


def test_there_is_at_least_one_list_endpoint(schema: dict[str, Any]) -> None:
    """Guards the guard.

    Every rule below is expressed as "for each list endpoint", and a bug in
    `_list_operations` would make all of them pass by iterating nothing. This is
    the test that notices.
    """
    assert len(_list_operations(schema)) >= 4


def test_every_list_endpoint_requires_a_city(schema: dict[str, Any]) -> None:
    """Invariant #1, at the transport layer.

    Required rather than defaulted. A `city_id` that falls back to the
    configured default city would work perfectly for the whole of M1 — one
    city — and then leak silently on the day Madurai launches, which is the
    exact failure mode invariant #1 exists to prevent.
    """
    missing = []
    for path, method, operation in _list_operations(schema):
        parameter = _query_parameters(operation).get("city_id")
        if parameter is None or not parameter.get("required"):
            missing.append(f"{method.upper()} {path}")

    assert not missing, "list endpoints not scoped by a required city_id:\n  " + "\n  ".join(
        missing
    )


def test_even_nested_collections_require_a_city(schema: dict[str, Any]) -> None:
    """`/api/conversations/{conversation_id}/messages` too.

    The conversation id already implies a city, so this looks redundant — and it
    is exactly the redundancy that stops a guessed or leaked UUID from reading
    another city's message history. The scoping check is then one rule applied
    everywhere rather than a judgement made per endpoint.
    """
    nested = _query_parameters(
        schema["paths"]["/api/conversations/{conversation_id}/messages"]["get"]
    )

    assert nested.get("city_id", {}).get("required") is True


def test_every_list_endpoint_paginates_the_same_way(schema: dict[str, Any]) -> None:
    """One pagination convention, so the console writes one table component."""
    wrong = []
    for path, method, operation in _list_operations(schema):
        parameters = _query_parameters(operation)
        if "limit" not in parameters or "offset" not in parameters:
            wrong.append(f"{method.upper()} {path}")

    assert not wrong, "list endpoints without limit/offset:\n  " + "\n  ".join(wrong)


def test_operation_ids_are_clean_and_unique(schema: dict[str, Any]) -> None:
    """Because these become the generated client's function names.

    FastAPI's default ids append the path and method — `list_hotels_api_hotels_get`
    — which generates TypeScript nobody wants to call and changes whenever a
    route moves. Naming the operation after its endpoint function keeps the
    generated client readable and makes a rename visible in the diff.
    """
    ids = [operation.get("operationId") for _, _, operation in _operations(schema)]

    assert all(ids), "every operation needs an explicit operationId"
    assert len(ids) == len(set(ids)), f"duplicate operationIds: {ids}"

    method_suffixed = [
        operation_id
        for operation_id in ids
        if operation_id is not None
        and operation_id.endswith(("_get", "_post", "_put", "_patch", "_delete"))
    ]
    assert not method_suffixed, f"auto-generated operationIds: {method_suffixed}"


def test_the_error_envelope_is_part_of_the_published_schema(schema: dict[str, Any]) -> None:
    """The console needs a *type* for failure, not just a status code.

    Without this the generated client types the happy path and leaves error
    handling to `any`, which is how a 409 ends up rendered as a blank screen.
    """
    components = schema.get("components", {}).get("schemas", {})

    assert "ErrorEnvelope" in components
    assert set(_resolve(schema, components["ErrorEnvelope"]).get("properties", {})) == {"error"}


def test_the_city_list_is_the_one_endpoint_that_takes_no_city(schema: dict[str, Any]) -> None:
    """The tenancy root cannot be scoped by tenancy.

    Every other collection requires a `city_id`; this is the endpoint that tells
    the console which ones exist, so requiring one would be circular. That makes
    it the single most likely place for the scoping rule to be quietly widened,
    which is why the exception is asserted rather than merely allowed.

    It deliberately returns a bare array rather than a `Page`. Cities are a
    bounded set — one today, a handful ever — so there is nothing to paginate,
    and staying outside the page envelope keeps it outside
    `_list_operations()` too. The alternative was an allowlist in
    `test_every_list_endpoint_requires_a_city`, and an allowlist on a tenancy
    check is exactly the thing that rots into a leak.
    """
    operation = schema["paths"]["/api/cities"]["get"]

    assert "city_id" not in _query_parameters(operation)

    body = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert body.get("type") == "array", "the city list must not become a Page"


def test_the_hotel_directory_can_filter_by_tier(schema: dict[str, Any]) -> None:
    """S08's directory filters server-side, and only by known tiers.

    Typed as the enum rather than as a string, matching `?state=` on the inbox:
    `?tier=manaul` is then a 422 before any handler runs, instead of a silently
    empty directory that reads as "we have no manual hotels".
    """
    parameter = _query_parameters(schema["paths"]["/api/hotels"]["get"])["tier"]

    assert parameter["required"] is False

    # Optional, so FastAPI publishes `anyOf: [$ref IntegrationTier, null]`
    # rather than inlining the enum. The `$ref` is the thing being asserted:
    # a plain `type: string` here would accept `?tier=manaul` and answer it
    # with an empty directory.
    referenced = [option for option in parameter["schema"]["anyOf"] if "$ref" in option]
    assert referenced, "tier must reference the IntegrationTier enum, not be a free string"

    assert set(_resolve(schema, referenced[0])["enum"]) == {"live", "bot", "manual"}
