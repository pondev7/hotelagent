# 0002 — Modular monolith, not microservices

**Status:** Accepted
**Date:** 2026-08-11
**Deciders:** Founding team

## Context

`docs/vision.md` §3.2 draws twelve components: channel gateway, orchestrator,
session store, tool layer, ops console, inventory, booking, payments, knowledge
base, hotelier interfaces, jobs, and analytics. A component diagram is not a
deployment diagram, but it is routinely mistaken for one.

The load we are actually designing for at M1: one city, five to fifty hotels,
one ops pod, and a booking volume measured in tens per day. FlashRooms sustains
this entire business on a telephone.

## Options considered

**Microservices now.** Each of the twelve components deployed independently.
You get independent scaling, failure isolation and team autonomy — none of which
we currently need — in exchange for costs paid from day one.

**Modular monolith.** One FastAPI application containing twelve modules, plus
one worker process. Two deploy units. Module boundaries enforced in code rather
than by the network.

| | Modular monolith | Microservices now |
|---|---|---|
| Deploy units | 2 | 12+ |
| Local dev | `make dev` | orchestration pain |
| A change spanning 3 modules | one PR | three PRs, ordered deploys |
| Debugging a booking | one log stream | distributed tracing |
| Infra cost | one small VM | many, plus a mesh |
| Agent effectiveness | high | low |

## Decision

**One FastAPI application (`api`) plus one worker process (`worker`).** Twelve
modules, two containers.

Module boundaries are real but enforced in-process: each module owns a
`service.py`, cross-module calls go through those functions, and data crosses as
Pydantic schemas rather than ORM instances. The seam is preserved without paying
for the network between every pair of components.

## Consequences

**Easier:**
- One log stream to debug a booking through. At M4, tracing money across a
  distributed system would be the single largest source of accidental
  complexity.
- One deploy, one rollback, one `.env`, one VM at ₹0–600/month.
- A refactor spanning three modules is one atomic commit.
- In-process calls have no serialisation cost and no partial-failure modes.

**Harder:**
- Everything scales together. One hot module means scaling the whole app.
  Acceptable: this workload is I/O-bound and the app is stateless, so scaling is
  "run more copies".
- A crash takes the whole API down. Mitigated by the process being stateless and
  restart-on-failure being instant; the customer-facing SLA degrades to L0
  (human desk) which exists anyway.
- Nothing physically prevents a developer — or an agent — from reaching across a
  module boundary. This is the real risk, and it is why the rule is stated in
  `CLAUDE.md`, checked in review, and being moved into ruff's `TID` rules.

## When to revisit

Extract a module into its own service when **one** of these becomes true:

1. It needs to scale on a genuinely different axis from everything else.
2. It has a genuinely different security or compliance boundary.
3. A separate team owns it.

None will be true before roughly M5. Note that the trigger is a property of the
system, not a headcount or a date — "we're big now" is not a reason.
