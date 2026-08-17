"""Shared query parameters, as reusable annotated types.

Declared as `Annotated` aliases rather than as a `Depends()` class on purpose:
an alias keeps each parameter visible in the OpenAPI document as an ordinary
query parameter, which is what `tests/unit/test_openapi_contract.py` checks and
what makes the generated TypeScript client take them as named arguments.
"""

import uuid
from typing import Annotated

from fastapi import Query

# The ceiling on any single page. A console bug asking for `?limit=100000` is a
# slow query, a large JSON encode and an unresponsive browser tab; refusing it
# costs one line and is cheaper than surviving it.
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 50

CityId = Annotated[
    uuid.UUID,
    Query(
        description="The city this request is scoped to. Required on every collection.",
    ),
]
"""Invariant #1 at the transport layer.

Required, never defaulted. Falling back to the configured default city would
behave perfectly for the whole of M1 — there is one city — and then leak
silently on the day the second one launches. That is precisely the failure
invariant #1 exists to prevent, so the parameter has no default.
"""

Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Rows per page.")]

Offset = Annotated[int, Query(ge=0, description="Rows to skip.")]
