# M1 — System of record · build plan

**Milestone:** M1, weeks 3–5 (`docs/milestones.md` §6)
**Business outcome:** nothing changes for the customer. Internally, the desk moves
off the phone and the spreadsheet into software that scales.
**Milestone exit criterion:** an operator completes an entire booking without
leaving the ops console, and operator seconds-per-booking is on a dashboard.

---

## 0. How this document works

M1 is broken into **thirteen technical sub-milestones**. We build **one at a
time**, in order. Each one is a branch, a PR and a commit — never several at once
(`docs/milestones.md` §7).

Each sub-milestone has a fixed shape:

| Field | Meaning |
|---|---|
| **Goal** | The one sentence that says why this slice exists |
| **Deliverable** | The files that will exist when it is done |
| **Out of scope** | What we deliberately do *not* build, so scope cannot creep |
| **Invariants** | Which of the ten non-negotiables (`CLAUDE.md`) this slice touches |
| **Exit criterion** | An objective check — it passes or it does not |
| **Teaches** | The concepts the companion learning file will explain |

### The learning contract

This project has two outputs: **working software** and **understanding**. So every
sub-milestone produces two artefacts.

1. The code, on its own branch.
2. A learning file: `docs/learning/m1-sNN-<slug>.md`.

The learning file is written **after** the code is built and passing, and it
explains **every technical concept the slice used** — Python, SQL, HTTP, Docker,
React, TypeScript, whatever appeared — from the ground up, using the actual code
we just wrote as the worked example. It is not API documentation. It assumes
strong general engineering judgement and no familiarity with the specific tool.

Each learning file follows this structure:

- **What we built** — the slice in three sentences
- **The concepts** — one section per concept, explained from first principles
- **Reading our code** — a walk through the real files, line by line
- **The gotchas** — the mistakes this tool invites, and how to spot them
- **Check yourself** — a few questions to confirm the ideas landed
- **Going deeper** — where to read more, if you want to

> Nothing in `apps/` gets written without its learning file following it. A slice
> is not done when the tests pass; it is done when the tests pass and the
> explanation exists.

---

## 1. Sub-milestone index

| # | Sub-milestone | Status | Learning file |
|---|---|---|---|
| S00 | Repository skeleton | ✅ built (`85a70c8`) | ✅ [m1-s00](learning/m1-s00-repository-skeleton.md) |
| S01 | Decision records and CI gates | ✅ built (`6355f1f`) | ✅ [m1-s01](learning/m1-s01-adrs-and-ci.md) |
| S02 | Database foundations and the first migration | ✅ built (`9a13836`) | ✅ [m1-s02](learning/m1-s02-database-foundations.md) |
| S03 | The M1 entity set, event log and idempotency | ✅ built (`3cc7d70`) | ✅ [m1-s03](learning/m1-s03-entities-events-idempotency.md) |
| S04 | Channel gateway — inbound | ✅ built (`8fe117b`) | ✅ [m1-s04](learning/m1-s04-channel-gateway-inbound.md) |
| S05 | Channel gateway — outbound and conversation state | ✅ built (`33c935b`) | ✅ [m1-s05](learning/m1-s05-channel-outbound.md) |
| S06 | Availability router and the manual provider | ✅ built (`5aa8feb`) | ✅ [m1-s06](learning/m1-s06-availability-router.md) |
| S07 | API surface and generated contracts | ✅ built (`00ae0f1`) | ✅ [m1-s07](learning/m1-s07-api-surface.md) |
| S08 | Ops console shell and hotel directory | ⬜ | ⬜ |
| S09 | Unified inbox and canned phrases | ⬜ | ⬜ |
| S10 | Call-task queue | ⬜ | ⬜ |
| S11 | Payment reconciliation | ⬜ | ⬜ |
| S12 | Stage 1 deploy, backups and a tested restore | ⬜ | ⬜ |

**Dependency order is strict from S02 to S07.** S08–S11 are all console work and
could reorder if a real operator need appears. S12 is last by definition.

---

## S00 — Repository skeleton ✅

**Goal:** a monorepo where `make dev`, `make lint` and `make test` are real
commands rather than aspirations.

**Delivered:** the tree from `docs/milestones.md` §2 — `Makefile`, both Compose
files, `pyproject.toml` + `uv.lock`, `apps/api` with `main.py` (a single
`GET /health`) and `config.py` (one `Settings` object), nine empty module
`service.py` files, four empty adapter packages, a Next.js shell in `apps/ops`,
`infra/caddy/Caddyfile`.

**Verified:** `make test` (1 passed), `make lint` (ruff + format + mypy strict,
30 files). `make dev` **not** verified — the Docker daemon was unavailable.

**Invariants:** #9.

**Teaches:** `make` as a task runner; `uv` and `pyproject.toml`; virtualenvs and
editable installs; ASGI, uvicorn and what FastAPI actually is; Docker images vs
containers vs volumes; Docker Compose services, healthchecks and profiles; the
Next.js App Router skeleton; ruff, mypy strict and pytest; why the module
boundary rule exists.

---

## S01 — Decision records and CI gates

**Goal:** stop future sessions re-litigating settled decisions, and make the
quality bar automatic rather than remembered.

**Deliverable:**
- `docs/adr/0001-monorepo.md`, `0002-modular-monolith.md`,
  `0003-no-agent-framework.md`, `0004-postgres-only-datastore.md` — each with
  Context / Decision / Consequences / When to revisit, drawn from the choices
  already made in `docs/milestones.md` §1–3.
- `.github/workflows/ci.yml` — runs `make lint` and `make test` on every push
  and PR.
- `docs/adr/README.md` explaining the ADR format and when to write one.

**Out of scope:** deploy automation (S12), the eval gate (M2), branch protection
rules (a GitHub setting, not a file).

**Invariants:** none directly — this protects all ten.

**Exit criterion:** CI runs green on a pull request, and a deliberately
introduced lint error turns it red.

**Teaches:** what an ADR is and why "we already decided this" needs to be written
down; YAML syntax; GitHub Actions concepts (workflow, job, step, runner, matrix,
caching); why CI runs the *same* `make` targets you run locally.

---

## S02 — Database foundations and the first migration

**Goal:** the shape every table in the system will inherit — tenancy key,
time-sortable id, UTC timestamps — proven by migrating two real tables up and
back down.

**Deliverable:**
- `db/base.py` — the SQLAlchemy 2.0 `DeclarativeBase`.
- `db/mixins.py` — `uuid7()`, `IdMixin`, `TimestampMixin`, `CityScopedMixin`.
- `db/session.py` — async engine, session factory, a FastAPI dependency.
- `alembic.ini` + `alembic/env.py` wired for async and autogenerate.
- Migration 0001: `city` and `hotel` (with `integration_tier`,
  `commission_rate`, `reception_phone`, `verification_status`, `trust_score`).
- `modules/inventory/models.py` for those two tables.
- `tests/integration/test_migrations.py` — upgrade head, then downgrade base.
- `/health` gains a real readiness check against Postgres.

**Out of scope:** every other table (S03), any service function, any route
besides health, seed data.

**Invariants:** #1 (`city_id` from the first migration).

**Exit criterion:** `make migrate` applies cleanly, `alembic downgrade base`
reverses it cleanly, and the round-trip is asserted by a test against real
Postgres.

**Teaches:** what an ORM is and when it earns its keep; SQLAlchemy 2.0
`Mapped[]` declarative style; sync vs async database drivers and why `asyncpg`;
connection pooling; sessions, transactions and the unit-of-work pattern; what a
migration is and why `create_all` is banned; Alembic revisions, `upgrade`,
`downgrade` and autogenerate's blind spots; UUIDv7 vs auto-increment vs UUIDv4
(time-sortability, index locality, safe exposure); `timestamptz` and why
everything is UTC; `Numeric(12,2)` vs float for money; Python mixins and MRO;
FastAPI dependency injection.

---

## S03 — The M1 entity set, event log and idempotency

**Goal:** the rest of the schema, plus the two mechanisms that cannot be
retrofitted — the append-only log and idempotency keys.

**Deliverable:**
- Models across their owning modules: `RoomType` (inventory), `User` and
  `Conversation` and `Message` (conversation), `CallTask` (ops),
  `AvailabilityObservation` (availability), `Booking` + `BookingEvent`
  (booking), `LedgerEntry` (payments).
- `events/` — the append-only writer used by `BookingEvent` and `LedgerEntry`.
- `db/idempotency.py` — an idempotency-key table and a helper that makes a
  mutation safe to replay.
- Migration 0002, with a working `downgrade()`.
- Unit tests for the idempotency helper; an integration test proving a replayed
  mutation produces exactly one row.

**Out of scope:** service logic on top of these tables, any API, any UI.

**Invariants:** #1, #5, #6, #8 (the observation table exists here; it gets
written to in S06).

**Exit criterion:** migration round-trips, and a test calling the same mutation
twice with one key produces one row and one event.

**Teaches:** relational modelling (one-to-many, many-to-many, association
tables); primary vs foreign vs unique keys; indexes and when they matter;
`CHECK` constraints and enums in Postgres vs Python; nullability as a design
decision; what "append-only" means and the difference between event sourcing and
an event log; why a `status` column loses history; idempotency — what breaks
without it (webhook redelivery, gateway retries, double-clicks) and the
key-plus-unique-constraint pattern; double-entry bookkeeping basics and why a
ledger is not a reports table.

---

## S04 — Channel gateway, inbound

**Goal:** receive a WhatsApp message safely and turn it into our own message
type, so no Meta-shaped data ever leaks past the boundary.

**Deliverable:**
- `modules/channel/schemas.py` — the channel-agnostic `InboundMessage`
  (Pydantic v2), with no WhatsApp vocabulary in it.
- `modules/channel/router.py` — `GET /webhooks/whatsapp` (Meta's verify-token
  handshake) and `POST /webhooks/whatsapp`.
- `adapters/channel/cloud_api.py` — payload parsing + HMAC-SHA256 signature
  verification.
- `adapters/channel/console.py` — a dev adapter that injects a fake message, so
  the whole flow is testable with **no Meta account and no public URL**.
- `modules/channel/service.py` — persist the message, idempotently on
  `wa_message_id`.
- Tests: valid signature accepted, tampered body rejected, redelivered message
  stored once.

**Out of scope:** sending anything (S05), media download, the agent, any reply
logic.

**Invariants:** #2, #5, #9.

**Exit criterion:** a webhook POST with a valid signature persists exactly one
normalised message; the same payload delivered three times still persists one;
a body with a bad signature returns 403 and persists nothing.

**Teaches:** HTTP verbs, status codes, headers, request bodies; what a webhook
is and how it inverts the client/server relationship; HMAC and why a shared
secret plus a digest proves authenticity; constant-time comparison and timing
attacks; replay attacks and why idempotency is the defence; Pydantic v2
validation, field aliases and `model_validate`; the adapter pattern and
dependency inversion; FastAPI routers, dependencies and `Depends`; ngrok/tunnels
and why our console adapter avoids needing one.

---

## S05 — Channel gateway, outbound and conversation state

**Goal:** send a reply back, and keep the thread — the full loop an operator
needs before any console exists.

**Deliverable:**
- `adapters/channel/base.py` — the `ChannelAdapter` protocol (`send_text`,
  `send_buttons`), implemented by both `cloud_api` and `console`.
- Outbound send via `httpx`, with timeouts and bounded retries.
- `modules/conversation/service.py` — find-or-create a conversation, append
  turns, track language and state.
- Delivery-receipt handling; the WhatsApp 24-hour window recorded on the
  conversation.
- Structured logging with `structlog` — `conversation_id`, `city_id`, never
  message bodies or full phone numbers.
- Tests against a stubbed adapter.

**Out of scope:** templates and template approval, the automation governor (M2),
any LLM.

**Invariants:** #2, #9.

**Exit criterion:** a message received through the console adapter can be
replied to, and both turns appear on one conversation in the right order.

**Teaches:** `async`/`await`, the event loop, coroutines, and what actually
blocks it; `httpx` async clients and connection reuse; timeouts, retries,
exponential backoff, idempotent vs unsafe retries; Python `Protocol` and
structural typing vs inheritance; structured logging vs print debugging; PII
discipline and why phone numbers are redacted; the WhatsApp session window as a
business rule expressed in data.

---

## S06 — Availability router and the manual provider

**Goal:** invariant #3 — the router exists with one implementation and two empty
slots, so Tier B and Tier A are later a fill-in rather than a rewrite.

**Deliverable:**
- `modules/availability/router.py` (the routing logic, not a FastAPI router) —
  `check_availability(hotel_id, dates, guests, room_type) -> AvailabilityResult`
  with `status: available | unavailable | pending`.
- `providers/base.py` (the protocol), `providers/manual.py` (raises a
  `CallTask`, returns `pending` with an ETA), `providers/bot.py` and
  `providers/live.py` — present, raising `NotImplementedError`.
- Resolution path: an operator logging a call outcome resolves the pending
  check.
- **Every** resolution writes an `AvailabilityObservation`, regardless of tier.
- Tests: manual provider raises exactly one call task; resolving it writes
  exactly one observation; the unimplemented providers fail loudly.

**Out of scope:** the bot and live providers, ranking, prediction, any UI.

**Invariants:** #3, #8.

**Exit criterion:** a check against a Tier C hotel returns `pending` and creates
one `CallTask`; logging the outcome resolves it and writes one observation.

**Teaches:** programming to an interface; the strategy pattern; ABC vs
`Protocol` in Python; designing for three implementations while writing one;
modelling asynchronous real-world work (a phone call) as state rather than a
blocking call; enums and exhaustive matching; why the dataset is written on
*every* path, including the manual one.

---

## S07 — API surface and generated contracts

**Goal:** a real HTTP surface for the console to consume, with types the
frontend cannot drift from.

**Deliverable:**
- Thin routers per module: hotels, conversations, messages, call tasks.
- `errors.py` — the `HotelAgentError` hierarchy and a FastAPI exception handler
  mapping them to status codes. No `HTTPException` below `router.py`.
- Pagination, filtering, and `city_id` scoping applied consistently.
- `make contracts` wired: OpenAPI JSON → TypeScript into `packages/contracts/`.
- Tests: error mapping, tenancy scoping, and that a router contains no ORM query.

**Out of scope:** authentication (deferred to M4 per `docs/milestones.md` §9),
rate limiting, the console itself.

**Invariants:** #1, and the module boundary rule.

**Exit criterion:** `make contracts` produces TypeScript that compiles, and
every list endpoint is `city_id`-scoped.

**Teaches:** REST resource design and status-code semantics; why routers stay
thin; exception hierarchies and translating domain errors to transport errors;
OpenAPI as a machine-readable contract; code generation and why it beats
hand-written client types; TypeScript basics — structural typing, interfaces,
generics.

---

## S08 — Ops console shell and hotel directory

**Goal:** the first real screen, and the React foundation everything after it
builds on.

**Deliverable:**
- App shell: navigation, layout, shadcn/ui installed, dark mode.
- Hotel directory: list, filter by tier, detail view — read-only.
- A typed API client using `packages/contracts/`.
- Loading and error states that are designed, not accidental.

**Out of scope:** editing anything, the inbox, auth.

**Invariants:** #1 (city scoping visible in the UI).

**Exit criterion:** the directory lists hotels from the real API, with tier and
commission shown, and it survives the API being down without a blank screen.

**Teaches:** what React actually is — components, JSX, props, state, the
reconciler; why re-renders happen; Next.js App Router — file-based routing,
layouts, server vs client components, `"use server"`/`"use client"`; data
fetching and caching in the App Router; Tailwind's utility-class model and why
it is not inline styles; shadcn/ui as copied source rather than a dependency;
TypeScript in React (typing props, discriminated unions for loading states).

---

## S09 — Unified inbox and canned phrases

**Goal:** the operator's primary surface — read a conversation, reply, without
touching WhatsApp.

**Deliverable:**
- Conversation list with unread and waiting states; a thread view.
- A reply composer that sends through the channel gateway.
- A canned-phrase library — the seed of the agent's persona (Vision §4.1).
- Near-real-time updates by polling.
- Time-to-first-reply displayed per conversation — our SLA, made visible.

**Out of scope:** AI drafts (M2), attachments, WebSockets.

**Invariants:** #2.

**Exit criterion:** an operator holds a complete two-way conversation entirely
inside the console.

**Teaches:** React state and effects in depth; controlled forms; `useEffect`
dependency arrays and the mistakes they cause; polling vs SSE vs WebSockets and
why polling is right at this scale; optimistic updates and rollback; list
virtualisation and keys; component composition.

---

## S10 — Call-task queue

**Goal:** the Tier C loop, and the screen whose speed *is* our gross margin.

**Deliverable:**
- The queue: which hotel to ring, what to ask, how long it has waited.
- Two-click outcome logging — available / not, price, room type.
- Logging resolves the pending availability check from S06 and writes the
  observation.
- Claim/assign so two operators cannot take the same task.
- Seconds-per-task measured and displayed.

**Out of scope:** predicting availability (M5), auto-dialling, SLA alerting.

**Invariants:** #3, #8.

**Exit criterion:** an operator resolves a task in **two clicks**, the traveller's
pending check resolves, and one observation row is written.

**Teaches:** designing for operator seconds rather than screens; optimistic
concurrency and claim semantics (two operators, one task); keyboard-first UI;
measuring an interface; closing an async loop that started in another module.

---

## S11 — Payment reconciliation

**Goal:** know what money arrived, against which booking, and what we owe each
hotel — while collection is still a static QR.

**Deliverable:**
- Reconciliation screen: expected vs received, unmatched payments, match action.
- Manual payment entry (UPI reference, amount, timestamp) writing `LedgerEntry`.
- Per-hotel settlement view: gross, commission, payable.
- Every mutation idempotent.

**Out of scope:** Razorpay/Cashfree, payment links, refunds, automated payouts —
all M4.

**Invariants:** #5, #6.

**Exit criterion:** a booking with a manually recorded payment reconciles to the
paisa, and the hotel's payable equals gross minus commission.

**Teaches:** why money is `Numeric` and never float; decimal arithmetic and
rounding rules; reconciliation as a concept; debits, credits and reading a
ledger; representing money in JSON and TypeScript without losing precision.

---

## S12 — Stage 1 deploy, backups and a tested restore

**Goal:** it runs somewhere other than your laptop, and you have *proven* you can
get the data back.

**Deliverable:**
- A VM (Oracle Always Free, or Hetzner — see the one-day rule in
  `docs/milestones.md` §5), Docker + Caddy, nothing else on the host.
- `docker-compose.prod.yml` live behind TLS on a real domain.
- `infra/scripts/deploy.sh` → `make deploy`.
- `infra/scripts/backup.sh` — nightly `pg_dump` to Cloudflare R2.
- `infra/scripts/restore.sh` + `docs/runbooks/restore-from-backup.md`.
- **A restore actually rehearsed into a scratch database, and the runbook
  corrected by what you learn doing it.**
- Sentry and uptime monitoring.

**Out of scope:** Stage 2 hosting, multi-region, autoscaling, zero-downtime
deploys.

**Invariants:** #9.

**Exit criterion:** `make deploy` ships from a clean checkout, and a restore from
last night's backup is performed end-to-end with the elapsed time written down.

**Teaches:** Linux server basics, SSH keys, firewalls; DNS records and how TLS
certificates are actually issued; Caddy and reverse proxies; Docker in
production — restart policies, log rotation, resource limits; `pg_dump`/
`pg_restore`; the difference between having backups and having *restores*;
runbooks; secret handling on a real host.

---

## 2. Working agreement

- **One sub-milestone at a time.** Nothing starts until the previous one's code
  and learning file are both done.
- **One branch per slice**, named `m1/sNN-<slug>`.
- **Test first.** The test is the specification and is faster to review than the
  implementation (`docs/milestones.md` §7).
- **Every PR names the invariants it touches.**
- **Read every line that touches money, availability or a customer promise.**
  Everything else can be reviewed at diff level.
- If a slice turns out to need something not in its Deliverable list, that is a
  conversation, not a quiet addition.

## 3. Open questions that M1 must answer

- **BSP vs direct Meta Cloud API** — `docs/vision.md` §6 says decide at M1.
  Blocks S04. Direct is cheaper; a BSP is faster on template approval.
- **Is M0 actually complete?** One hotel is signed. The exit bar is 5–10 hotels
  and 10+ real bookings with a call log in `availability_observation` shape.
  S10's design quality depends on having done the job by hand first.
- **Ops staffing** — founder-operated through M2, then what? Affects S09/S10.
