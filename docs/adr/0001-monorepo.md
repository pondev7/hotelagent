# 0001 — Single monorepo, not multiple repositories

**Status:** Accepted
**Date:** 2026-08-11
**Deciders:** Founding team

## Context

HotelAgent ships at least four distinct things: a FastAPI backend, an ops
console, later a hotelier dashboard, and shared type contracts between them.
The conventional instinct is one repository per deployable.

Two constraints make this decision different from the usual case:

1. **Most of the code is written by an agent.** Claude Code works from what it
   can see in one context. Across repositories, a human becomes the integration
   layer, hand-carrying context between sessions.
2. **The team is one person.** There are no independent release cadences to
   decouple and no separate security boundaries to enforce.

Changes here are overwhelmingly cross-cutting. Adding `integration_tier` to a
hotel touches the migration, the model, the availability router, the API, the
ops UI and the tests.

## Options considered

**Multiple repositories.** Correct when several teams ship on separate cadences,
or when parts of the system have genuinely different security boundaries.
Requires published packages, version negotiation and cross-repo release
coordination.

**Monorepo.** One checkout, one CI pipeline, one `.env.example`, atomic
cross-cutting commits. Requires you to impose internal structure yourself,
because the filesystem no longer enforces boundaries for you.

## Decision

**A single monorepo**, laid out as `apps/` (things that run), `packages/`
(things that are imported), `infra/` and `docs/`, per `docs/milestones.md` §2.

The boundary discipline that repository separation would have given us for free
is replaced by an explicit rule, stated in `CLAUDE.md`: every module owns a
`service.py`, modules call each other only through those functions, and no
module imports another module's SQLAlchemy models.

## Consequences

**Easier:**
- A cross-cutting change is one commit, one PR, one review, always consistent.
- No version skew — there is no "which version of the API is the console on?"
- FastAPI emits OpenAPI; `make contracts` generates TypeScript into
  `packages/contracts/`, so the frontend cannot drift from the backend. This is
  a shared contract for free, and it only works because both live together.
- The agent sees the handler, the service, the schema, the migration and the UI
  component in one context.

**Harder:**
- Boundaries are now a convention, and conventions erode without enforcement.
  Mitigated by the `service.py` rule, by review, and by ruff's `TID` rules
  (`flake8-tidy-imports.banned-api`), which will machine-enforce it.
- CI runs everything on every change unless we add path filtering later.
- Repository size grows monotonically; irrelevant at this scale.

**Reversibility is asymmetric, and this is the crux.** If the module rules hold,
extracting `payments/` into its own service is a directory move plus an HTTP
shim — roughly a week. Merging four drifted repositories back together is not a
week's work at any point. We therefore take the option that stays cheap to undo.

## When to revisit

At roughly **ten engineers**, or the first time two people are genuinely blocked
on each other's release timing. Also revisit if a component acquires a different
security or compliance boundary — a service handling raw card data, for example,
though ADR 0004's stance on not building our own payment gateway makes that
unlikely.
