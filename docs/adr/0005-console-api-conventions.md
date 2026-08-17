# 0005 — Console API conventions: explicit city scoping, one error envelope, generated types

**Status:** Accepted
**Date:** 2026-08-17
**Deciders:** Founding team

## Context

M1 slice 07 adds the first HTTP surface the ops console consumes: hotels,
conversations, messages and call tasks. Four resources, and every convention
chosen here gets copied by every endpoint added in S08–S12 and again at M4 when
the hotelier dashboard arrives. The conventions are cheap now and are the kind of
thing that is never revisited once six screens depend on them.

Four questions had no obvious answer.

**How does an endpoint know which city is asking?** Invariant #1 puts `city_id`
on every row, which makes the database tenantable. It does nothing to guarantee
that a query filters on it, and a list endpoint that forgets is invisible in
review — the handler looks exactly like a correct one.

**What does a cross-tenant read return?** There is no authentication until M4
(`docs/milestones.md` §9), so today any caller can name any UUID.

**What shape does a failure have?** Five slices had each grown their own error
classes over `RuntimeError`, translated by hand in the one router that knew them.

**How does the console get its types?** Hand-written TypeScript interfaces
mirroring the Pydantic schemas drift the first week and are wrong silently.

## Options considered

### City scoping

**A `city_id` query parameter, required on every collection.** Explicit, visible
in the OpenAPI document, and machine-checkable.

**Default to the configured city when absent.** Considerably more pleasant to
call, and correct for the whole of M1 — there is exactly one city. It fails on
the day Madurai launches, silently, by serving one city's rows to another city's
operator. This is precisely the failure invariant #1 exists to prevent, so
accepting it inside the transport layer would be self-defeating.

**Infer it from the operator's session.** The right long-term answer and it
requires authentication, which is deferred to M4. Nothing in this ADR prevents
it: an inferred value can be injected into the same parameter later.

### Cross-tenant reads

**404, as though the row did not exist**, versus **403, "it exists but is not
yours"**. A 403 is more informative to a legitimate caller who has mistyped a
city, and is also an oracle: it confirms a row exists to anyone who can guess a
UUID. Tenancy boundaries are the one place where being unhelpful is correct.

### Errors

**A `HotelAgentError` hierarchy carrying its own status code and a stable slug**,
translated once in `errors.py`, versus **per-router `except` clauses** (the
status quo, which re-decides the meaning of "absent" per endpoint) or **raising
`HTTPException` in services** (which ties every service to being called from a
web request — the arq worker and management commands are real callers).

FastAPI's own `RequestValidationError` was a sub-question: leaving it alone gives
the console a second error shape, `{"detail": [...]}`, from a layer we do not
control.

### Types

**Generate from OpenAPI with `openapi-typescript`**, versus hand-written
interfaces, versus a full client generator that also emits fetch functions. The
last was rejected as more machinery than four resources justify; the console can
call `fetch` and type the result.

## Decision

1. **`city_id` is a required query parameter on every collection endpoint**,
   including nested ones such as `/api/conversations/{id}/messages` where the
   parent id already implies a city. The redundancy is deliberate: it makes the
   rule one rule applied everywhere rather than a judgement made per endpoint,
   and `tests/unit/test_openapi_contract.py` enforces it by reading the schema.
2. **A row outside the asking city is reported absent**, with the same error a
   missing row produces.
3. **One error envelope for every non-2xx response** — `{"error": {code,
   message, detail}}` — produced by `errors.py` from a `HotelAgentError`
   subclass, with `RequestValidationError` overridden to match. `code` is a
   stable slug the console branches on, unique per class and independent of the
   Python class name.
4. **Offset pagination** with `{items, total, limit, offset}` and a hard cap of
   100 rows, in a generic `Page[T]`.
5. **Operation ids are the endpoint function name**, via an app-level
   `generate_unique_id_function`, because they become the generated client's
   type keys.
6. **No version prefix in the URL.** The console's types are generated from this
   exact schema and shipped from this monorepo, so the compiler is the
   compatibility check. A `/v1` would be decoration until an external consumer
   exists, which is an M4 question at the earliest.
7. **Generated output is not committed** — `openapi.json` and `generated.ts` are
   gitignored and produced by `make contracts`. The hand-written
   `packages/contracts/src/index.ts` names the schemas the console depends on, so
   the generation step is also a drift check.

## Consequences

**Easier:**

- A tenancy bug becomes a schema-level test failure rather than a code review
  that has to notice a missing `WHERE`.
- The console handles failure once. One typed `ErrorEnvelope`, one code to
  branch on, no per-status parsing.
- Adding an endpoint is mechanical: annotate the types, and pagination, error
  documentation and city scoping follow from the shared vocabulary in
  `hotelagent/api/`.
- A renamed or removed Python schema breaks `make contracts` at `tsc`, in the
  same commit, instead of degrading a console component to `any`.

**Harder:**

- Every list call must pass `city_id`, which is noise for the whole of M1 while
  there is one city. This is a deliberate cost paid now.
- Offset pagination is not stable under concurrent insert: a row added while an
  operator reads page one can be missed on page two. Acceptable for operator
  screens over thousands of rows, and `total` — which the console needs and
  cursors make expensive — is cheap this way.
- Two schemas over one table in places (`HotelSummary` and
  `HotelAvailabilityContext`), which is duplication. Collapsing them would hand
  the availability router the whole hotel record it was deliberately denied.
- `make contracts` needs Node and the npm registry, so the API's contract step
  depends on the frontend toolchain being installed.
- Generated files being gitignored means a fresh clone cannot typecheck
  `packages/contracts` until `make contracts` has been run once.

## When to revisit

- **`city_id` moves from a query parameter to the authenticated session** at M4,
  when there is an operator identity to read it from. That is a fulfilment of
  this decision, not a reversal — the scoping stays required.
- **A URL version prefix** when a consumer outside this monorepo exists, which
  means the compiler no longer checks compatibility.
- **Cursor pagination** for a specific endpoint that measurably outgrows offsets
  — tens of thousands of rows on a screen an operator scrolls, not a suspicion.
- **A full client generator** if the console starts hand-writing the same fetch
  wrapper for the tenth time.
