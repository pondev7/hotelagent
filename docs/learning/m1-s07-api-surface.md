# S07 — API surface and generated contracts · learning notes

**Slice:** M1 / S07 · **Commit:** `00ae0f1` · **Status:** built and verified

---

## What we built

The first HTTP surface anything other than WhatsApp will talk to: four resources
(hotels, conversations, messages, call tasks), one error shape, one pagination
envelope, and a TypeScript package generated from the schema so the ops console
cannot disagree with the API about what a hotel is.

Underneath it, a thing that should have existed five slices ago: `errors.py`. Each
earlier slice had grown its own exceptions over `RuntimeError` and the one router
we had translated them by hand. That works for one router. It does not work for
four modules of endpoints, because every new route re-decides what "this row does
not exist" means.

Nothing a traveller can see changed. This is scaffolding for S08–S12, and the
conventions chosen here get copied by every endpoint added for the next year.

---

## The concepts

### 1. Exceptions carry meaning; transport is derived from it

The rule in `CLAUDE.md` is *"raise `HotelAgentError` subclasses from services;
the API layer maps them to HTTP. Never raise `HTTPException` below
`router.py`."*

The reason is not tidiness. Consider `check_availability`. Today an HTTP request
calls it. At M2 the arq worker calls it when a call task times out. An operator
fixing something by hand calls it from a management command. If it raises
`HTTPException(404)`, the other two callers must import a web framework and read
a status code off an exception object to discover what went wrong.

So the class says what happened and the status code follows:

```python
class NotFoundError(HotelAgentError):
    status_code = 404
    code = "not_found"
```

`status_code` is a `ClassVar` — a property of the *situation*, decided once by
whoever raises it, never by a caller. The router does not contain the number 404
anywhere.

Two fields travel with every error and they are for different readers. `message`
is prose for a human reading a log. `code` is a stable slug the console branches
on — deliberately not the class name, so renaming a Python class is not a
breaking change for the frontend. `detail` is optional structure the UI can
render: the call-task queue wants to say "already claimed by Ravi" in its own
words and its own language, which it can only do from fields, not from a
sentence we wrote in English.

### 2. Status-code semantics, where the choice is not obvious

Three of them took actual thought.

**404 versus 403 for another city's row.** A 403 is more informative to a
legitimate caller who mistyped a city. It is also an oracle: it confirms the row
exists to anyone who can guess a UUID. There is no authentication until M4, so
today anyone can name any id. Tenancy is the one place where being unhelpful is
correct, so a row outside the asking city reads as absent.

**409 versus 422 for the expired service window.** WhatsApp allows free-form
replies for 24 hours after the customer's last message; outside it we have no
approved templates, so we cannot reply at all. The request was perfectly well
formed — the text was fine, the clock was not. A 422 invites the console to
highlight a form field the operator filled in correctly. That is a `Conflict`:
the state of the world refuses a valid request.

**503 versus 500 for missing configuration.** An unseeded city means the gateway
cannot assign a `city_id`. The request would have succeeded against a correctly
configured system, so "not now" is honest where "not ever" is not. It also
interacts well with WhatsApp's redelivery on any non-2xx: the message arrives
once we are set up, rather than being lost.

### 3. One error envelope, including the framework's own

Every non-2xx response body is now:

```json
{"error": {"code": "unknown_hotel", "message": "...", "detail": null}}
```

The subtle half is FastAPI's own `RequestValidationError`, which by default
returns `{"detail": [...]}` — a different shape, from a layer we do not control,
for the very common case of a bad query parameter. Left alone, the console has
two failure formats to understand and cannot tell which layer refused it.

A generated client can only expose one error type. Two shapes means every call
site in the console handles failure twice, and the second path is the one nobody
tests. So `install_error_handlers` overrides both:

```python
def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HotelAgentError, _handle_domain_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
```

One function rather than two decorators at the call site, so a second app — a
test harness, a future admin surface — cannot install half the contract.

### 4. Where an error class lives tells you who owns the meaning

`UnknownHotelError` was written in `availability` in S06, because that is where
it was first needed. It moved to `inventory` in this slice, and `availability`
imports it.

The question that settles it: which module owns hotels? Inventory does, so
inventory owns the meaning of "there is no such hotel". Any module may raise
another module's public error — that is a normal thing to do with a public API,
and it is why `errors.py` is shared rather than per-module.

The alternative is two classes for one condition, which gives the console two
codes to handle for one situation. The uniqueness test on `code` is what forces
the issue: if both existed and both inherited `not_found`, the codes would
collide and the test would fail. A test that makes a design mistake impossible
to commit is worth more than a convention that makes it embarrassing.

### 5. A base class you cannot usefully catch is not a base class

`ChannelError` existed to group the gateway's three errors. It is deleted, not
retrofitted, and the reasoning generalises.

The three situations map to 503, 404 and 409. So there is no `except
ChannelError:` that could do anything sensible — any handler catching the group
would immediately have to ask which one it got. The group had no behaviour, only
a name. Nothing referenced it, which is the evidence.

A base class earns its place when callers want to treat its members alike.
`HotelAgentError` does: one handler turns any of them into a response.
`NotFoundError` does: everything under it is a 404. `ChannelError` did not.

### 6. Thin routers, and what "thin" means precisely

Every handler in this slice is three lines: call the service, wrap the result.

```python
@router.get("")
async def list_hotels(...) -> Page[HotelSummary]:
    hotels, total = await service.list_hotels(session, city_id=city_id, ...)
    return page_of(hotels, total=total, limit=limit, offset=offset)
```

No `try`. No status code. No query. The router's whole job is translating between
HTTP and Python, and everything it does beyond that is business logic that a
worker or a CLI cannot reach.

Note what the router *does* do: it accepts the `AsyncSession` and passes it down.
That is how the request's transaction reaches the service. Holding the session is
fine; using it is not.

Services return `(rows, total)` and never a `Page`. Pagination is a transport
concern — a worker calling the same function has no use for an envelope — and
keeping it out of `service.py` is what lets both callers share one query.

### 7. Enforcing a rule where the rule actually lives

`test_routers_do_not_import_models` already existed. Two more joined it:

- **Routers run no ORM queries** — matched on the verb (`session.scalar`,
  `session.execute`, `session.add`, …) rather than on the import, because
  `select` can reach a router by many spellings.
- **`HTTPException` appears only in `router.py`.**

The second one is the interesting story. The first draft searched the file text
and failed immediately — on `channel/service.py`, where the only occurrence of
the word is a docstring *explaining that services must not raise it*.

A checker that cannot tell code from prose teaches people to stop writing the
prose. So it parses the AST and looks for the name in expression position:

```python
tree = ast.parse(path.read_text())
for node in ast.walk(tree):
    if isinstance(node, ast.Name) and node.id == "HTTPException":
        violations.append(f"{path}:{node.lineno}")
```

The real check also covers `ast.Attribute` (`fastapi.HTTPException`) and
`ast.alias` (the import itself), which is three node types for one rule — the
price of asking about code rather than about text.

This is the same lesson as S01's CI and S06's registry test, from a new angle:
the check that matters is the one that runs whether or not you remember — but a
check with false positives is worse than none, because the fix people learn is to
stop doing the thing that trips it.

### 8. Invariant #1 enforced against the schema, not the source

Invariant #1 puts `city_id` on every row. That makes the database tenantable and
guarantees nothing about whether a query filters on it. A list endpoint that
forgets is invisible in review — the handler looks exactly like a correct one.

So the rule is checked against the generated OpenAPI document:

```python
for path, method, operation in _list_operations(schema):
    parameter = _query_parameters(operation).get("city_id")
    assert parameter is not None and parameter["required"]
```

Whatever a handler does internally, it cannot answer a collection request without
being told which city is asking. And "list endpoint" is identified by *shape* —
any 200 response whose schema has `items`, `total`, `limit` and `offset` — not by
a naming convention, so a new endpoint is covered the moment it returns a page,
with nobody having to remember to add it.

One test guards the guard: `test_there_is_at_least_one_list_endpoint`. Every
other rule is "for each list endpoint", and a bug in the detector would make them
all pass by iterating nothing. Vacuous truth is the most comfortable way for a
test suite to lie to you.

**Required, never defaulted.** Falling back to the configured city would behave
perfectly for the whole of M1 — there is one city — and leak silently the day
Madurai launches. That is precisely the failure invariant #1 exists to prevent,
so accepting it in the transport layer would defeat the point of the invariant.

The nested case, `/api/conversations/{id}/messages`, requires `city_id` too, even
though the conversation id already implies a city. The redundancy is the point: it
stops a guessed or leaked UUID from reading another city's transcript, and it
keeps scoping one rule applied everywhere rather than a judgement made per
endpoint.

### 9. Offset pagination, and what `total` means

```python
class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
```

`total` is the count of rows that **match**, not the count returned. The console
needs it to render "showing 2 of 3" and to decide whether to draw a next-page
control at all. Returning the page length is the classic version of this bug, and
it only appears once there is a second page — which, in a five-hotel city, means
it appears in production.

Offsets rather than cursors, deliberately. Cursors are right for a feed of
millions where rows arrive at the head while you read. These are operator screens
over thousands of rows, where a page number the operator can return to is worth
more than consistency under concurrent insert — and `total`, which the console
wants, is cheap with offsets and expensive with cursors.

The cost is real and worth naming: a row inserted while an operator reads page one
can be missed on page two. Acceptable here. Not acceptable for a ledger export,
which is a different problem for a different slice.

**Every ordering tie-breaks on `id`:**

```python
.order_by(Conversation.last_inbound_at.desc().nullslast(), Conversation.id)
```

Without the tie-break, two rows sharing a timestamp can appear on both page one
and page two, or on neither, and the bug is invisible in a test with distinct
timestamps. The integration test asserts the two pages are disjoint and cover
everything, which is the assertion that catches it.

### 10. Two orderings, opposite on purpose

The inbox is most-recently-active first. The call-task queue is longest-waiting
first. Same codebase, same week, opposite decisions — and neither is a
preference.

HotelAgent is specified as a response-time contract (`docs/vision.md` §2.2), so
an operator working the inbox top-down must be working whoever is currently
waiting on us. A call task is a promise *already made* to a traveller who was
told five minutes; newest-first there means the person who has waited longest
waits longest.

Both are pinned by tests, because "whatever the database returns" is not an
ordering and the day someone adds an index it silently changes.

### 11. OpenAPI as a machine-readable contract

FastAPI derives an OpenAPI document from the type annotations. That document is
the artefact this slice actually delivers: it is what lets the frontend's types
be generated rather than written.

Which makes the annotations load-bearing in a new way. `state: ConversationState`
is not documentation — it produces an enum in the schema, so `?state=activee` is
a 422 before any handler runs. A `str` there would silently match nothing, and
"my conversations are missing" is a much worse bug report than "invalid value".

Two mechanics were new here:

**`Annotated` types as reusable parameters.** `CityId` is an alias, not a
`Depends()`:

```python
CityId = Annotated[uuid.UUID, Query(description="...")]
```

Either works, but an alias keeps the parameter visible in the schema as an
ordinary query parameter, which is what the contract test reads and what makes
the generated client take it as a named argument. A class-based dependency tends
to collapse into something less legible on the far side.

**Operation ids become the client's type keys.** FastAPI's default is
`list_hotels_api_hotels_get` — path and method appended — which generates
TypeScript nobody wants to call and renames itself whenever a route moves. One
app-level function fixes it:

```python
app = FastAPI(generate_unique_id_function=lambda route: route.name)
```

Uniqueness becomes our problem rather than FastAPI's, which is exactly why the
contract test asserts it.

### 12. Code generation, and why it beats hand-written client types

`make contracts` is three steps, each able to fail loudly:

1. `export_openapi.py` dumps `app.openapi()` to JSON. It does **not** start a
   server — the schema comes from import-time annotations, so this works in CI,
   in a container build, and on a laptop with nothing running. Keys are sorted
   and the file ends in a newline, so regenerating an unchanged API produces a
   byte-identical file. A generated artefact that reorders itself cannot be
   diffed, and a contract you cannot diff is one nobody reviews.
2. `openapi-typescript` turns that JSON into `src/generated.ts` — about a
   thousand lines of pure type declarations, no runtime code.
3. `tsc --noEmit` typechecks the result.

Step 3 is what makes this a contract rather than a code dump, and it works
because of a small hand-written file. `generated.ts` spells a hotel
`components["schemas"]["HotelSummary"]`. Nobody wants that in a React component,
so `packages/contracts/src/index.ts` names them:

```typescript
export type Hotel = Schemas["HotelSummary"];
```

That file is committed; the generated one is gitignored. And because it *names*
the schemas it expects, renaming a Pydantic model on the Python side fails at
`tsc` in the same commit — instead of six months later, in a console component
that silently became `any`.

This is the whole argument for generation. A hand-written interface mirroring
`HotelSummary` is correct on the day it is written and wrong the first time
someone adds a field, and nothing anywhere notices.

### 13. TypeScript, the parts that matter here

Three ideas, all visible in `index.ts`:

**Structural typing.** TypeScript cares about an object's shape, not its declared
name — the same idea as Python's `Protocol`, which S05 and S06 used for adapters
and providers. Two types with identical fields are interchangeable. This is why
generated types compose with hand-written ones without any adapter layer.

**Interfaces and type aliases.** `export type Hotel = ...` names an existing
shape; `export interface Page<T>` declares one. Roughly interchangeable for our
purposes; aliases are for renaming, interfaces for describing.

**Generics.** `Page<T>` is the same idea as Python's `Page[T]` — a container
parameterised by what it holds, so one type and one React table component serve
hotels, conversations, messages and call tasks. Note it is declared structurally
here rather than aliased to one of the generated `Page_HotelSummary_` components:
FastAPI publishes each instantiation separately, and reconstructing the generic
keeps a single `<Table of T>` possible on the console side.

### 14. PEP 695 generics, and a nudge from the linter

`Page[T]` was first written the way generics have looked in Python for a decade:

```python
T = TypeVar("T")

class Page(BaseModel, Generic[T]):
```

Ruff rejected it — `UP046`, "uses `Generic` subclass instead of type parameters"
— and wanted Python 3.12's new syntax:

```python
class Page[T](BaseModel):

def page_of[T](items: list[T], ...) -> Page[T]:
```

No `TypeVar`, no `Generic`, and the parameter is scoped to the thing that
declares it rather than living as a module-level global that any other class
could accidentally share. Pydantic 2.9+ understands it, so this is now the house
style for generics. Worth knowing why the linter cares: a module-level `TypeVar`
reused across two unrelated classes is a real source of confusing inference
errors.

### 15. `__all__`, and a rule biting where it was aimed

The conversation router needs `ConversationState` for its filter parameter. That
enum lives in `conversation/models.py`, beside the column it constrains — and
`test_routers_do_not_import_models` bans a router importing models
*unconditionally*, including from its own module.

That felt wrong for about a minute. It is right: "it is only an enum" is exactly
how a model import gets into a router, and the next one is a query. So the enums
re-export through `schemas.py`, the module's public surface.

Which surfaced a mypy strict flag worth knowing: `--no-implicit-reexport`. Under
strict mode, importing a name into a module does not make it importable *from*
that module. You must say so:

```python
__all__ = ["ConversationState", "ConversationSummary", ...]
```

Or the `import X as X` form, which is what the cross-module error imports use.
The default is the right one — it stops a module's imports from becoming
accidental public API — and the `__all__` here is load-bearing rather than
decorative.

### 16. Two schemas over one table

`inventory` now returns two shapes for a hotel. `HotelAvailabilityContext` has
five fields, all the availability router is allowed to see.
`HotelSummary` adds the address, the commission rate and the verification status,
because the directory is a human-facing screen and those are what make it useful.

The instinct is to merge them. Don't: widening the narrow one hands the
availability router the whole hotel record it was deliberately denied in S06. The
duplication is the price of the boundary, and it is a low price — two explicit
schemas are easier to reason about than one schema with a comment about which
fields which caller should ignore.

---

## Reading our code

### The whole error path, end to end

A service raises:

```python
raise UnknownHotelError(f"hotel {hotel_id} is not in city {city_id}")
```

The router does nothing at all — no `except`. `errors.py` answers:

```python
event = "http.server_error" if exc.status_code >= 500 else "http.client_error"
logger = log.error if exc.status_code >= 500 else log.info
logger(event, code=exc.code, status=exc.status_code, path=request.url.path)
return JSONResponse(status_code=exc.status_code, content=exc.envelope())
```

Three things worth noticing.

**5xx logs at error, 4xx at info.** A 404 is ordinary API traffic; logging it as
an error trains everyone to ignore the error level, and then a real 500 goes
unnoticed.

**What is not logged.** No message body, no full phone number, no payment
identifier — per `CLAUDE.md`. The `message` may name a hotel or a conversation
id, which is what makes an incident traceable, and stops there.

**The handler narrows rather than annotates.** Starlette's registry declares
handlers as `Callable[[Request, Exception], Response]`, so annotating the
parameter as `HotelAgentError` is a type error. `isinstance` inside keeps mypy
strict happy without a `cast`.

### The channel router got shorter

S04 wrote this:

```python
try:
    recorded = await service.handle_inbound(session, batch)
except service.ChannelConfigurationError as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from exc
```

S07 deletes all of it. `ChannelConfigurationError` is a `ConfigurationError`, so
the answer is 503 — the same status this router used to construct by hand, now
decided once for every endpoint in the system. The existing test still passes
unchanged, which is the useful evidence that the refactor preserved behaviour.

---

## The gotchas

**A service that raises `HTTPException`** has decided it is only ever called from
a web request. It has two other callers.

**403 on a tenancy boundary is an oracle.** "Not yours" confirms it exists.

**A required parameter the service then ignores** is worse than no parameter —
the schema now documents a guarantee that does not hold. Both halves need a test.

**A default `city_id`** is correct for exactly as long as there is one city.

**`total` is the match count, not the page length.** The bug hides until there
are two pages.

**An ordering without a tie-break** is not an ordering. Rows sharing a timestamp
land on two pages or none.

**"For each X" tests pass vacuously** when the detector finds no X. Guard the
guard.

**A string search cannot tell code from prose.** It will fail on the docstring
that explains the rule, and the lesson people learn is to delete the docstring.

**FastAPI's default operation ids** are path- and method-derived, so they change
when a route moves and generate a client nobody wants to call.

**mypy strict does not re-export.** Importing a name does not make it importable
from you; say `__all__`.

**A generated file that reorders itself** cannot be diffed, so nobody reviews the
contract change.

---

## Check yourself

1. `check_availability` raises `UnknownHotelError`. Name the three callers that
   error has to make sense to, and what each would have to do if it were an
   `HTTPException` instead.
2. Why is a hotel in another city a 404 and not a 403 — and what changes about
   that answer at M4, when there is authentication?
3. The service window has closed. Why is that a 409 rather than a 422, and what
   would the console do wrong if we sent 422?
4. `ChannelError` was deleted rather than re-parented. What test would you write
   to decide whether a base class is worth keeping?
5. `city_id` is required on `/api/conversations/{id}/messages` even though the
   conversation id implies a city. Give the concrete attack that redundancy
   blocks.
6. What would `test_every_list_endpoint_requires_a_city` do if
   `_list_operations` had a bug and matched nothing? Which test catches that?
7. Two conversations have identical `last_inbound_at`. Without the `id`
   tie-break, describe precisely what the operator sees across two pages.
8. The inbox sorts newest-first and the call-task queue oldest-first. Argue both
   from `docs/vision.md` §2.2 rather than from taste.
9. Someone renames `HotelSummary` to `HotelRow` in Python. Trace exactly where
   that failure surfaces, and what would have happened if the console's types
   were hand-written.
10. Ruff rejected `Generic[T]` in favour of `class Page[T]`. What concrete bug
    does the new syntax's scoping prevent?
11. Why can't the conversation router import `ConversationState` from
    `models.py`, given that it is the router of the module that owns it?
12. `export_openapi.py` deliberately does not start a server. Name two
    environments where that matters.

## Going deeper

- **HTTP status codes** — RFC 9110 §15, particularly the 4xx section. Worth
  reading once properly; most status-code arguments are settled there.
- **Exception hierarchies** — any discussion of "exception translation" at
  architectural boundaries; the framing is that an exception is part of a
  function's public type.
- **OpenAPI** — the specification's own "Parameter Object" and "Components
  Object" sections; you now have a real document to read alongside them
  (`packages/contracts/openapi.json` after `make contracts`).
- **`openapi-typescript`** — its README on how `components["schemas"]` is
  structured, which explains why `index.ts` looks the way it does.
- **TypeScript** — the handbook's "Everyday Types" and "Generics" chapters are
  enough for everything in this slice.
- **PEP 695** — the type-parameter syntax, and the motivation section on why
  module-level `TypeVar`s were a problem.
- **Pagination** — anything comparing offset and keyset pagination; the useful
  question is always "what is the cost of a row moving between requests".
- **`docs/adr/0005-console-api-conventions.md`** — the decisions in this slice,
  with the options that were rejected and why.

---

**Next:** S08 — the ops console shell and hotel directory. The React foundation,
the first real screen, and the first consumer of the types this slice generates —
which is where we find out whether the contract actually holds.
