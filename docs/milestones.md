# HotelAgent — Technical Milestones & Build Plan

**Version:** 1.0
**Date:** 2026-07-25
**Companion to:** HotelAgent Vision & Architecture v0.2
**Audience:** the founding team and Claude Code

---

## 0. How to read this document

Three constraints shape every decision below.

1. **The business must be live before the software is.** Revenue in week two, from a manual desk. Every line of code afterwards replaces labour we have already measured.
2. **The technology stays exactly one step ahead of the business — never two.** One step ahead means the *seams* exist before we need them. Two steps ahead means Kubernetes for forty hotels. The discipline is to build **boundaries early and implementations late**.
3. **Claude Code writes most of it, so the repository is the specification.** Structure, conventions, tests and docs are not hygiene — they are how the work gets done at all.

A useful rule of thumb throughout: **cheap to add later → don't build it. Expensive to retrofit → build the seam now, even if it's a stub.** §4 is the list of things that fall on the expensive side.

---

## 1. Decisions to lock in Week 0

Decide these once, write them in `docs/adr/`, and stop revisiting them.

| Decision | Choice | Why |
|---|---|---|
| Repository layout | **Monorepo** | §2 |
| Runtime architecture | **Modular monolith** | §3 |
| Backend language | **Python 3.12 + FastAPI** | Your strongest language; the LLM/data ecosystem lives here; Claude Code is excellent at it |
| Frontend | **Next.js (App Router) + Tailwind + shadcn/ui** | One framework for ops console *and* hotelier dashboard |
| Database | **PostgreSQL 16 + pgvector** | One engine for relational, JSON, queue-ish and vector work. Do not add a second datastore until it hurts |
| ORM / migrations | **SQLAlchemy 2.0 + Alembic** | Migrations from commit one, no exceptions |
| Cache / sessions / holds | **Redis** | |
| Background jobs | **arq** (async-native, Redis-backed) | Pairs cleanly with FastAPI; simpler than Celery |
| Agent framework | **None — the Anthropic SDK directly** | See note below |
| LLM models | Cheap model for routing/classification, capable model for conversation | Cost per conversation is a tracked metric from turn one |
| Container runtime | **Docker + Docker Compose** | The single most important portability decision |
| TLS / reverse proxy | **Caddy** | Automatic certificates, one config file |
| CI | **GitHub Actions** | |
| Error tracking | **Sentry** (free tier) | |
| LLM tracing | **Langfuse** (self-hosted in the same Compose file) | Traces, costs and evals in one place |

> **On skipping the agent framework.** You know LangGraph from ArchitectIQ, and it is the right tool when a graph of many nodes needs orchestrating. This is not that. HotelAgent's loop is *call the model → maybe call a tool → maybe ask a human → repeat*, roughly 200 lines. The **Automation Governor** needs to intercept every single turn and decide agent-replies vs human-approves vs escalate. Frameworks make that interception awkward and the debugging opaque. Write the loop; own the loop. Revisit only if the loop exceeds ~500 lines.

---

## 2. Repository strategy: monorepo

**Recommendation: a single monorepo. This is not a close call for your situation.**

### Why

- **Claude Code works dramatically better in one repo.** It can see the API handler, the service, the schema, the migration and the ops-console component in one context. Cross-repo work means you become the integration layer, hand-carrying context between sessions.
- **Atomic cross-cutting changes.** Adding `integration_tier` to a hotel touches the migration, the model, the router, the API, the ops UI and the tests. One commit, one PR, one review, always consistent.
- **No version skew.** Multi-repo means contracts, published packages and "which version of the API is ops on?" — pure overhead at this size.
- **A shared contract for free.** FastAPI emits OpenAPI; generate TypeScript types into `packages/contracts/` on every build. The frontend cannot drift from the backend.
- **One CI pipeline, one deploy, one `.env.example`.**
- **Splitting later is mechanical, splitting early is irreversible.** If §3's module rules are respected, extracting `payments/` into its own service is a directory move plus an HTTP shim. Merging four repos back together is not.

Multi-repo would be right with several independent teams shipping on separate cadences, or with genuinely different security boundaries. You have neither. Reassess at roughly ten engineers.

### Structure

```
hotelagent/
├── CLAUDE.md                    # the contract with Claude Code — read §7
├── Makefile                     # every command Claude Code may run
├── docker-compose.yml           # local dev: api, worker, ops, postgres, redis, langfuse
├── docker-compose.prod.yml
├── .env.example                 # every config key, documented, no secrets
│
├── docs/
│   ├── vision.md                # Vision & Architecture v0.2
│   ├── milestones.md            # this document
│   ├── adr/                     # 0001-monorepo.md, 0002-modular-monolith.md, ...
│   └── runbooks/                # deploy, restore-from-backup, rotate-keys, on-call
│
├── apps/
│   ├── api/
│   │   ├── src/hotelagent/
│   │   │   ├── main.py
│   │   │   ├── config.py        # pydantic-settings; ALL config via env
│   │   │   ├── db/              # session, base, mixins (id, city_id, timestamps)
│   │   │   ├── events/          # append-only event log + publisher
│   │   │   ├── modules/
│   │   │   │   ├── channel/         # WhatsApp webhook in / send out
│   │   │   │   ├── conversation/    # threads, turns, session state
│   │   │   │   ├── agent/           # loop, governor, tools, prompts/
│   │   │   │   ├── availability/    # router + providers/{live,bot,manual}.py
│   │   │   │   ├── inventory/       # hotels, room types, rates, search
│   │   │   │   ├── booking/         # holds, bookings, lifecycle
│   │   │   │   ├── payments/        # collection, ledger, settlement
│   │   │   │   ├── knowledge/       # RAG over hotel KB
│   │   │   │   └── ops/             # call tasks, inbox, reconciliation
│   │   │   ├── adapters/
│   │   │   │   ├── llm/         # Anthropic behind a thin interface
│   │   │   │   ├── channel/     # cloud_api.py | bsp.py | console.py (dev)
│   │   │   │   ├── payments/    # razorpay.py | manual_qr.py
│   │   │   │   └── storage/     # s3_compatible.py — works with R2, S3, MinIO
│   │   │   └── workers/         # arq tasks: hold expiry, reminders, retries
│   │   ├── alembic/
│   │   └── tests/
│   │
│   └── ops/                     # Next.js — ops console, later hotelier dashboard
│
├── packages/
│   └── contracts/               # TS types generated from OpenAPI
│
└── infra/
    ├── caddy/Caddyfile
    └── scripts/                 # deploy.sh, backup.sh, restore.sh
```

**Every module owns a `service.py`.** Modules call each other *only* through those public functions. No module imports another module's SQLAlchemy models, ever. That single rule is the entire difference between "we can extract payments in a week" and "we can never extract anything." Put it in `CLAUDE.md` and enforce it in review.

---

## 3. Architecture stance: modular monolith

The vision document draws twelve components. **Do not deploy twelve services.** Deploy one FastAPI application containing twelve modules, plus one worker process.

| | Modular monolith | Microservices (now) |
|---|---|---|
| Deploy units | 2 (api, worker) | 12+ |
| Local dev | `make dev` | orchestration pain |
| A change spanning 3 modules | one PR | three PRs, ordered deploys |
| Debugging a booking | one log stream | distributed tracing |
| Infra cost | one small VM | many, plus a mesh |
| Claude Code effectiveness | high | low |

You get the microservices *benefit* — independent scaling and failure isolation — only when you actually have the load. You pay the microservices *cost* from day one. Trade that away and keep the seams instead.

**Extract a module into a service only when one of these is true:** it needs to scale on a different axis from everything else; it has a genuinely different security boundary; or a separate team owns it. None will be true before roughly M5.

---

## 4. The "ahead of the curve" invariants

These are the things that are cheap now and brutally expensive to retrofit. Every one goes into `CLAUDE.md` as a non-negotiable and into the PR checklist.

1. **`city_id` and `hotel_id` on every relevant row, from the first migration.** With one city and five hotels this looks silly. Adding a tenancy key to a live database with a year of bookings is a weekend of downtime.

2. **A channel-agnostic internal message schema.** The WhatsApp payload is normalised at the gateway boundary and never leaks past it. Adding Instagram, SMS or web chat later then becomes a new adapter, not a rewrite.

3. **The availability router exists at M1, with only the manual provider implemented.** One interface, three provider slots. Adding the bot and live providers later is filling in stubs. Retrofitting a router around hardcoded calendar reads is a rewrite of the agent's core flow.

4. **The Automation Governor exists at M2, even if it returns a constant.** Every outbound message passes through it. Because it is there, moving from L1 to L2 to L3 is a config change per hotel and per conversation stage. Without it, each automation step is a code change under production pressure.

5. **Idempotency keys on every money or inventory mutation, from the first write.** WhatsApp redelivers webhooks. Payment gateways retry. Operators double-click. Retrofitting idempotency after the first double-charge is expensive in more than engineering time.

6. **An append-only event log for bookings and payments, from day one.** `BookingEvent` and `LedgerEntry` alongside the mutable rows. You get audit, analytics, replay and dispute resolution for the cost of one insert per state change. Reconstructing history from a `status` column is impossible.

7. **Every LLM call traced: prompt version, model, tokens, latency, tool calls, whether a human edited the draft, and final outcome.** From the very first call, before anyone needs it. By M3 this is your eval dataset, your cost model and your regression suite. It cannot be backfilled.

8. **Every availability answer written to `availability_observation`, regardless of tier — including the manual phone calls in M0.** This is the dataset that becomes the moat (Vision §2.4). It starts accruing on a paper form in week one if it must.

9. **All configuration through environment variables, all external services behind thin adapters.** No provider SDK is imported at a call site — only inside `adapters/`. This is what makes §5's hosting ladder a config change rather than a migration project.

10. **Prompts are versioned files in the repo, never strings in code.** `modules/agent/prompts/v3/booking_flow.md`. The trace records which version produced which reply. Prompt regressions become diffable.

---

## 5. The hosting ladder

The strategy: **one portable artefact, four increasingly capable places to run it.** Because everything is Docker Compose behind env vars, moving up a rung is hours of work, not a project.

### Stage 0 — Nothing (M0, weeks 1–2)

WhatsApp Business App on a phone, a spreadsheet, a printed call log, your own UPI QR. **₹0.** No servers, no code, no deploy.

### Stage 1 — One small VM (M1–M4, ~months 1–5)

A single box running Docker Compose: `caddy`, `api`, `worker`, `postgres`, `redis`, `langfuse`. Nightly `pg_dump` to Cloudflare R2.

| Component | Choice | Cost |
|---|---|---|
| VM | Oracle Cloud Always Free (Ampere ARM, Mumbai/Hyderabad) | **₹0** |
| VM (fallback) | Hetzner CX22 ≈ €4/mo, or DigitalOcean Bangalore ≈ $6/mo | ₹350–550/mo |
| Postgres + Redis | In Compose, on the same box | ₹0 |
| Object storage | Cloudflare R2 (10 GB free, no egress fees) | ₹0 |
| DNS / CDN / WAF | Cloudflare free | ₹0 |
| TLS | Caddy + Let's Encrypt | ₹0 |
| CI | GitHub Actions free tier | ₹0 |
| Errors / uptime | Sentry free + Better Stack free | ₹0 |
| Domain | | ~₹900/yr |
| **Infra total** | | **₹0–600/month** |

> **Oracle Always Free caveat.** The Ampere allowance was reduced in mid-2026 (now around 2 OCPU / 12 GB for free-tier accounts), Indian regions frequently report capacity shortages, and idle instances can be reclaimed. It is still the best genuinely-free option and 2 OCPU / 12 GB is far more than this workload needs — but treat it as *lucky if you get it*. **Do not spend more than one day fighting it**; a €4 Hetzner box removes the whole class of problem and the Compose file is identical either way. That interchangeability is the actual point.

Variable costs at this stage dwarf infrastructure: LLM tokens (roughly ₹1–3 per conversation), Razorpay (~2% per transaction), Google Ads, and ops labour. WhatsApp messaging is close to zero because the funnel is inbound-first (Vision §3.8).

### Stage 2 — Split the database out (M5, at real traffic)

The first real bottleneck is always the database, and it is the piece you least want on a box you also deploy to.

- Postgres → **Neon**, **Supabase**, or DigitalOcean Managed Postgres (~$15–20/mo). One `DATABASE_URL` change. Automated backups, PITR, painless scaling.
- App → two VMs behind a load balancer, or **Fly.io / Railway** for zero-ops container hosting.
- Redis → managed (~$10/mo) or keep it local; session loss is survivable, holds are not — move holds to Postgres if Redis stays ephemeral.
- **₹2,000–6,000/month.**

### Stage 3 — Managed platform (post-expansion)

AWS ECS/Fargate or GCP Cloud Run in `ap-south-1` / Mumbai, RDS or Cloud SQL with a read replica, ElastiCache, S3, CloudFront, multi-AZ. Same containers, same env vars. **₹20,000+/month**, justified only by revenue.

### The portability contract

Adherence to this list is what makes the ladder cheap. Review it every time an adapter is touched.

- Everything runs in Docker. Nothing is installed on the host but Docker and Caddy.
- Every external dependency reached via env var: `DATABASE_URL`, `REDIS_URL`, `S3_ENDPOINT`, `ANTHROPIC_API_KEY`, `WHATSAPP_*`, `PAYMENT_*`.
- Object storage accessed through the **S3-compatible API only** — the same code hits R2, S3 or MinIO.
- **No proprietary platform primitives.** No Lambda-shaped handlers, no Vercel-only APIs, no Supabase RLS as the authorisation model, no cloud-specific queues.
- Schema changes only through Alembic. `make migrate` is the only path.
- A single deploy command, identical everywhere: `make deploy`.
- A tested restore-from-backup runbook. Test it at M2, not after the first incident.

---

## 6. Milestones

Each milestone states a **business outcome** (what changes for the customer or the P&L), a **technical deliverable**, an **exit criterion** you can objectively check, and the **ahead-of-curve investment** made in that phase.

---

### M0 — Manual desk, instrumented · *Weeks 1–2* · zero code

**Business outcome:** first paying customers and first revenue. You are running FlashRooms' model yourself.

**Do:**
- WhatsApp **Business App** (free, instant) on a dedicated number. Apply for Cloud API access in parallel — verification takes days to weeks, so start the clock now.
- Sign up 5–10 Kanyakumari hotels at Tier C: name, room types, rack rates, reception number, payout account, 15% rate card signed. Target under 15 minutes per hotel.
- Your own **static UPI QR** for collection. Manual settlement to hotels, weekly.
- A Google Sheet with three tabs: `conversations`, `call_log`, `bookings`. The `call_log` columns are exactly the future `availability_observation` schema: hotel, date, room type, asked at, available, price quoted, operator.
- A printed one-page call script and a canned-phrase list — the seed of the agent's persona and prompt.
- Run a small click-to-WhatsApp Google Ads campaign to learn your real CPC and chat-to-booking rate.

**Exit criteria:** 10+ real bookings completed. Every conversation exported. Median time-to-first-reply and time-to-confirm measured. Real ADR, conversion rate and CAC in hand.

**Ahead-of-curve investment:** the call log. It is invariant #8 running on paper, and the transcripts become the M2 eval set. Nothing else in this phase is technical, and that is deliberate — **you cannot write a good prompt for a job you have never done.**

---

### M1 — System of record · *Weeks 3–5*

**Business outcome:** unchanged externally. Internally, the desk moves off the phone and the spreadsheet into software that scales.

**Technical deliverable:**
- Monorepo scaffolded per §2. `CLAUDE.md`, Makefile, Compose, CI, ADRs.
- **Channel gateway:** Cloud API webhook receive + send, signature verification, media handling, normalised internal message schema, delivery receipts.
- **Schema and migrations:** City, Hotel (with `integration_tier`, `commission_rate`, `reception_phone`), RoomType, User, Conversation, Message, CallTask, AvailabilityObservation, Booking, BookingEvent, LedgerEntry.
- **Availability router** with a single provider: `manual` → raises a `CallTask`.
- **Ops console v1** (Next.js): unified inbox, send replies, canned phrases, call-task queue with two-click outcome logging, hotel directory, payment reconciliation screen.
- Deploy to Stage 1. `make deploy` works. Backups running and **a restore tested**.

**Exit criterion:** an operator completes an entire booking without leaving the console, and operator seconds-per-booking is on a dashboard.

**Ahead-of-curve:** invariants 1, 2, 3, 5, 6, 9. The router and the event log exist here even though nothing needs them yet.

**Learning:** FastAPI + SQLAlchemy 2.0 + Alembic; webhook security and idempotency; Docker Compose in production; Next.js App Router.

---

### M2 — AI copilot (L1) · *Weeks 6–8*

**Business outcome:** the same operators handle 2–3x the conversations. Nights become answerable.

**Technical deliverable:**
- **Agent loop** on the Anthropic SDK: system prompt, tool schemas, multi-turn state, language detection.
- Tools live: `search_hotels`, `get_hotel_details`, `check_availability` (manual provider), `escalate_to_human`.
- **Automation Governor v1** — every outbound message passes through it; settings are `off` / `draft` / `auto`, per conversation stage. Initially always `draft`.
- Ops console shows a **suggested reply** with edit-and-send. Every edit is captured.
- **Langfuse tracing** on every call; cost per conversation on the dashboard.
- **Eval harness**: ~50 real M0/M1 conversations as fixtures; a regression run on every prompt change.

**Exit criterion:** ≥ 60% of drafted replies sent unedited, with zero incorrect price or policy assertions in a 200-conversation sample.

**Ahead-of-curve:** invariants 4, 7, 10. Every human edit is a labelled training signal.

**Learning:** tool-use loops; prompt versioning; LLM cost mechanics; evals as tests.

---

### M3 — Agent front-of-funnel (L2) + hotelier bot · *Weeks 9–13*

**Business outcome:** cost per booking falls sharply. 24/7 becomes a real, advertisable promise. Supply scales to 30–50 hotels.

**Technical deliverable:**
- Governor flipped to `auto` for greeting, language selection, qualification, FAQ and shortlist. Money, availability assertions and confirmation stay human.
- **Knowledge base + RAG** on pgvector — per-hotel policies, FAQs, amenities, local context. Grounded answers only.
- **Hotelier WhatsApp bot** → the availability router's **Tier B** provider. Structured prompts with Yes/No buttons; booking alerts; "block N rooms tonight".
- Ranking v1: relevance, price, rating, and historical availability probability from the observation table.
- Multilingual: Tamil and Hindi live, evaluated with native-speaker review.
- Per-hotel tier and commission enforced end-to-end; the 11/13/15% rate card goes into effect.

**Exit criterion:** ≥ 50% of conversations reach a shortlist with no human touch. At least 10 hotels on Tier B. Cost-per-booking measurably below M1.

**Ahead-of-curve:** the router's third provider slot is stubbed and tested against a fake live calendar.

**Learning:** RAG and chunking; multilingual evaluation; the governor as a product surface.

---

### M4 — Payments and auto-confirm (L3) · *Weeks 14–18*

**Business outcome:** end-to-end autonomous booking for Tier A hotels. The 3-minute promise becomes literally true for part of the inventory.

**Technical deliverable:**
- **Payments module**: Razorpay/Cashfree payment links and dynamic UPI QR, webhook handling, idempotent capture, refunds.
- **Ledger**: customer payment, commission, hotel payable, payout, refund — reconciled and reportable. Weekly settlement run with a hotel-facing statement.
- **Soft holds** with TTL and atomic booking confirmation under optimistic locking.
- **Tier A provider**: live availability calendar, editable by the hotelier.
- **Hotelier dashboard v1**: calendar, rates, bookings, payouts.
- Automated confirmation, reminders and directions via correctly-classified *utility* templates.
- Governor set to `auto` end-to-end for Tier A hotels, simple requests and repeat customers.

**Exit criterion:** a booking completes with zero human involvement, money reconciles to the paisa, and a deliberate double-submit produces exactly one booking and one charge.

**Ahead-of-curve:** the ledger is built properly here rather than as a reports table — it is the piece you can never rebuild retrospectively.

**Learning:** payment gateway integration; idempotency and distributed-ish consistency; financial reconciliation.

---

### M5 — Scale and harden · *Months 5–6*

**Business outcome:** the funnel is measured, the operation is repeatable, and the dataset starts paying back.

**Technical deliverable:**
- Move to **Stage 2 hosting**. Managed Postgres, app on two instances, load balancer.
- Analytics: full funnel, containment by tier, operator throughput, LLM cost per booking, tier-mix trend.
- **Availability prediction v1** — a simple model over `availability_observation` that skips the phone call on high-confidence nights. This is the first compounding return on the dataset.
- Reviews and ratings; repeat-traveller profile and one-message rebooking.
- Voice-note transcription for low-literacy travellers.
- Load testing against a peak-season profile; graceful degradation to L0 if the LLM or a tool is down.
- DPDP compliance pass: consent capture, data minimisation, retention policy, deletion path.

**Exit criterion:** a peak weekend handled without a human bottleneck, and cost-per-booking at or below target.

---

### M6 — Second city · *Month 7+*

**Business outcome:** expansion validated at near-zero marginal engineering cost.

**Technical deliverable:** city config abstraction proven by adding Rameswaram or Tirupati — language pack, hotel set, city KB, ops routing — **with no code change**. Multi-city ops queue in the console. Per-city P&L reporting.

**Exit criterion:** city #2 goes live in under two weeks, run by the same ops pod, with zero deployments required to launch it.

---

## 7. Working with Claude Code

The repository is the specification. These practices are what make an agent-written codebase stay coherent past ten thousand lines.

### `CLAUDE.md` — the contract

Keep it under ~200 lines and current. It should contain:

- What HotelAgent is, in one paragraph, and a pointer to `docs/vision.md`.
- The current milestone and what is explicitly out of scope right now.
- **The ten invariants from §4, verbatim.** These are the rules an agent will otherwise cheerfully violate.
- The module boundary rule: modules communicate only via `service.py`; never import another module's models.
- Every command: `make dev`, `make test`, `make lint`, `make migrate`, `make eval`, `make deploy`.
- Conventions: naming, error handling, logging, where config lives, how prompts are versioned.
- "Before you finish" checklist: tests pass, migration written, `.env.example` updated, ADR added if a decision was made.

### PR discipline

- **One milestone slice = one branch = one PR.** Never a whole milestone in one PR.
- Every PR states which invariants it touches.
- **Tests are the contract.** Ask Claude Code for the test first, review the test carefully, then let it write the implementation. Reviewing a test is much faster than reviewing an implementation, and it is where the real specification lives.
- CI gates: lint, types, tests, and from M2 onward the eval suite.

### Keeping context manageable

- Modules under ~500 lines; split when they grow past it. This is as much for the agent's context window as for the reader.
- `docs/` lives in the repo so Claude Code can read the vision, this plan and the ADRs directly.
- Write an ADR for every non-obvious decision. Future sessions will otherwise re-litigate them, and you will not remember why.
- Deterministic commands only. Never "run the thing in the other terminal" — put it in the Makefile.

### The review reflex

Claude Code will happily generate a plausible payments module. Read every line that touches **money, availability or a customer promise**. Everything else can be reviewed at the diff level. That is where your seventeen years of judgement actually earn their keep — not in typing.

---

## 8. Learning track

You want to learn as you build. The milestones already sequence this well; here it is explicitly.

| Milestone | New ground | Existing strength being reused |
|---|---|---|
| M0 | Sales, ops, the domain itself | — |
| M1 | FastAPI, SQLAlchemy 2.0, Alembic, webhooks, Docker in prod, Next.js | Data modelling, Python, pipelines |
| M2 | Tool-use loops, prompt versioning, evals, LLM cost mechanics | Agentic AI from ArchitectIQ and the Chubb GenAI program |
| M3 | RAG at production quality, multilingual evaluation, ranking | Embeddings, retrieval, search |
| M4 | Payment gateways, idempotency, financial ledgers | Transactional data integrity |
| M5 | Managed infra, load testing, applied prediction, DPDP compliance | Data engineering, ML, cloud architecture |
| M6 | Multi-tenancy at operational scale | Multi-tenant design |

The unfamiliar ground is concentrated in M1 and M4 — plumbing and money. Budget extra time there, and be more suspicious of generated code there than anywhere else.

---

## 9. What NOT to build (yet)

Every item below is a real temptation and a real trap. Each has a trigger that tells you when it stops being premature.

| Don't build | Because | Build it when |
|---|---|---|
| Kubernetes | Compose on one VM serves this workload for a very long time | Multiple services genuinely need independent scaling — M5+ at the earliest |
| Microservices | §3 | A module needs a different scaling axis or a different team |
| A custom auth system | Ops console = a handful of trusted users | The hotelier dashboard opens to self-service — M4 |
| A mobile app | WhatsApp *is* the app; that is the entire thesis | Never, probably |
| A message bus (Kafka/RabbitMQ) | Postgres + arq handles this volume comfortably | Sustained thousands of events per second |
| GraphQL | REST + generated types is simpler and sufficient | Multiple diverse clients with different data needs |
| Custom ML models | Not enough data yet; that is what M0's call log is for | M5, and only on `availability_observation` |
| A separate vector database | pgvector is more than adequate at this scale | Millions of chunks with latency problems |
| Multi-region / HA | One city, one ops pod | Multi-city with revenue that justifies the bill |
| Your own payment gateway | Regulated, hard, and completely undifferentiated | Never |
| A rules engine for pricing | Rack rate plus commission is the entire pricing model at M1 | Dynamic pricing becomes a real lever — M5+ |
| Fine-tuning | Prompting plus RAG plus good evals gets you further, faster | A specific measured task the prompt cannot solve |

---

## 10. The one-page summary

**Repo:** monorepo. **Runtime:** modular monolith, two processes. **Hosting:** Docker Compose on one cheap VM, portable by construction to managed infrastructure when revenue justifies it. **Sequence:** manual desk → system of record → copilot → autonomous front-of-funnel → autonomous end-to-end → scale → second city.

**The organising principle:** build the *seams* early and the *implementations* late. The availability router, the automation governor, the event log, the ledger, tenancy keys and the trace log are the seams — they cost days now and months later. Everything else waits until the business asks for it.

**The first thing to do this week has nothing to do with code.** Sign up five hotels, put a QR on a poster, and take a booking.
