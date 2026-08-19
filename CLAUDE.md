# CLAUDE.md — the contract

## What this is

HotelAgent is a WhatsApp-first hotel booking concierge for Kanyakumari. A traveller
chats in Tamil/English/Hindi; behind the curtain an AI agent, a human operator, or
both find a real room, answer real questions, take payment and confirm. The customer
cannot tell which, and does not care — the product is specified as a **response-time
contract**, not as "an AI agent". Full context: `docs/vision.md`. Build plan and
milestone definitions: `docs/milestones.md`.

## Current milestone

**M1 — System of record** (weeks 3–5). The desk moves off the phone and the
spreadsheet into software. Externally nothing changes.

In scope now:
- Channel gateway (WhatsApp Cloud API webhook in/out, signature verification,
  normalised internal message schema)
- Schema + migrations for the M1 entity set
- Availability router with the `manual` provider only (raises a `CallTask`)
- Ops console v1: unified inbox, canned phrases, call-task queue, hotel directory,
  payment reconciliation
- Stage 1 deploy, backups running, a **tested** restore

Explicitly **out of scope right now** — do not build these unprompted:
- The agent loop, tool schemas, LLM calls of any kind (that is M2)
- RAG / pgvector retrieval, the hotelier bot (M3)
- Payment gateway integration, soft holds, the hotelier dashboard (M4)
- Kubernetes, microservices, message buses, GraphQL, custom auth, a mobile app,
  a separate vector DB, custom ML models. See `docs/milestones.md` §9 for the full
  list and the trigger that makes each one non-premature.

## The ten invariants — non-negotiable

These are cheap now and brutally expensive to retrofit. Every PR states which of
these it touches.

1. **`city_id` and `hotel_id` on every relevant row, from the first migration.**
   With one city and five hotels this looks silly. Adding a tenancy key to a live
   database with a year of bookings is a weekend of downtime.
2. **A channel-agnostic internal message schema.** The WhatsApp payload is
   normalised at the gateway boundary and never leaks past it. Adding Instagram,
   SMS or web chat later then becomes a new adapter, not a rewrite.
3. **The availability router exists at M1, with only the manual provider
   implemented.** One interface, three provider slots.
4. **The Automation Governor exists at M2, even if it returns a constant.** Every
   outbound message passes through it. Moving L1 → L2 → L3 is then a config change
   per hotel and per conversation stage.
5. **Idempotency keys on every money or inventory mutation, from the first write.**
   WhatsApp redelivers webhooks. Payment gateways retry. Operators double-click.
6. **An append-only event log for bookings and payments, from day one.**
   `BookingEvent` and `LedgerEntry` alongside the mutable rows.
7. **Every LLM call traced:** prompt version, model, tokens, latency, tool calls,
   whether a human edited the draft, and final outcome. It cannot be backfilled.
8. **Every availability answer written to `availability_observation`, regardless of
   tier** — including the manual phone calls. This dataset is the moat.
9. **All configuration through environment variables, all external services behind
   thin adapters.** No provider SDK is imported at a call site — only inside
   `adapters/`.
10. **Prompts are versioned files in the repo, never strings in code.**
    `modules/agent/prompts/v1/booking_flow.md`. The trace records which version
    produced which reply.

## The module boundary rule

**Every module owns a `service.py`. Modules call each other _only_ through those
public functions. No module ever imports another module's SQLAlchemy models.**

That single rule is the entire difference between "we can extract payments in a
week" and "we can never extract anything." A cross-module import of `models` is an
automatic PR rejection. Cross-module data crosses as a Pydantic schema, never as an
ORM instance.

Routers (`router.py`) are thin: parse, call `service.py`, serialise. No business
logic and no ORM queries in a router.

## Commands

Everything Claude Code may run is in the `Makefile`. Never "run the thing in the
other terminal".

| Command | Does |
|---|---|
| `make dev` | Full stack up via Docker Compose (api, worker, ops, postgres, redis, langfuse) |
| `make test` | pytest (API) + vitest (ops console). `test-api` / `test-ops` run one half |
| `make lint` | ruff + ruff format --check + mypy, then the console's `tsc --noEmit`. `lint-api` / `lint-ops` run one half |
| `make fmt` | ruff format + ruff check --fix |
| `make migrate` | Apply Alembic migrations |
| `make migration m="..."` | Autogenerate a new revision |
| `make seed` | Idempotent development data: one city, a few hotels |
| `make contracts` | Regenerate `packages/contracts/` TS types from OpenAPI |
| `make eval` | Eval suite (M2 onward; a no-op stub today) |
| `make deploy` | The single deploy command, identical everywhere |

## Conventions

- **Python 3.12**, FastAPI, SQLAlchemy 2.0 (async, `Mapped[]` style), Alembic,
  Pydantic v2. Managed with `uv`.
- **Config**: `apps/api/src/hotelagent/config.py`, pydantic-settings, one `Settings`
  object read via `get_settings()`. Nothing reads `os.environ` directly. Every new
  key lands in `.env.example` with a comment in the same commit.
- **IDs** are UUIDv7-ish (`uuid7()` in `db/mixins.py`) — time-sortable, safe to
  expose. Money is `Numeric(12, 2)` in INR, never a float. Timestamps are
  `timestamptz`, always UTC, named `*_at`.
- **Errors**: raise `HotelAgentError` subclasses from services; the API layer maps
  them to HTTP. Never raise `HTTPException` below `router.py`.
- **Logging**: `structlog`, JSON in prod. Log the `conversation_id`, `booking_id`
  and `city_id` on anything customer-facing. Never log message bodies, phone numbers
  in full, or payment identifiers.
- **Migrations**: schema changes only through Alembic. Never `create_all` outside
  tests. Every migration has a working `downgrade()`.
- **Tests**: `tests/unit` needs no services; `tests/integration` gets a real
  Postgres via the Compose file. Ask for the **test first** — reviewing a test is
  much faster than reviewing an implementation, and the specification lives there.
- **Prompts**: `modules/agent/prompts/v{n}/*.md`, loaded by `prompts.py`, version
  recorded on every trace. Bump the directory; never edit a shipped version.

## Before you finish

- [ ] `make lint` and `make test` pass
- [ ] Migration written if the schema moved, with a working `downgrade()`
- [ ] `.env.example` updated if config moved
- [ ] ADR added under `docs/adr/` if a non-obvious decision was made
- [ ] The PR description names the invariants touched
- [ ] No module imported another module's models
