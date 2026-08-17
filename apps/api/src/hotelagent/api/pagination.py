"""One pagination envelope for every collection.

`total` is the count of rows that *match*, not the count returned. The console
needs it to render "showing 2 of 3" and to decide whether to draw a next-page
control at all; returning the page length instead is the classic version of this
bug and only shows up once there is a second page — which, in a five-hotel city,
means it shows up in production.

Offset pagination rather than cursors, deliberately. Cursors are the right answer
for a feed of millions where rows are inserted at the head while you read; these
are operator screens over thousands of rows, and a page number the operator can
go back to is worth more than consistency under concurrent insert. `total` is
also cheap here and expensive with cursors, and the console wants it.
"""

from pydantic import BaseModel

from hotelagent.api.params import DEFAULT_PAGE_SIZE


class Page[T](BaseModel):
    """A slice of a collection, plus what the caller needs to ask for the next.

    Generic so there is one envelope and one frontend component for hotels,
    conversations, messages and call tasks. FastAPI publishes each instantiation
    as its own OpenAPI component (`Page_HotelSummary_`), so the generated
    TypeScript stays precisely typed rather than collapsing to `unknown[]`.
    """

    items: list[T]
    total: int
    limit: int
    offset: int


def page_of[T](
    items: list[T], *, total: int, limit: int = DEFAULT_PAGE_SIZE, offset: int = 0
) -> Page[T]:
    """Assemble a page in the router, from what the service returned.

    Services return `(rows, total)` and never a `Page`. Pagination is a transport
    concern — a worker calling the same service function has no use for an
    envelope — and keeping it out of `service.py` is what lets both callers share
    the query.
    """
    return Page(items=items, total=total, limit=limit, offset=offset)
