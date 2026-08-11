# Architecture Decision Records

An **ADR** records one decision: what we chose, what we were choosing between,
why, and what it costs us. One decision per file, numbered, never deleted.

## Why we keep them

`docs/milestones.md` §7 states the problem directly: *"Write an ADR for every
non-obvious decision. Future sessions will otherwise re-litigate them, and you
will not remember why."*

That is not hypothetical here. Most of this codebase is written by an agent in
sessions that start with no memory of the last one. Without these files, every
session is free to re-propose LangGraph, microservices, or a second datastore —
each time plausibly, each time costing an argument. With them, the decision is
already made and the reasoning is on disk.

A second reason matters more over time: an ADR records the **conditions** under
which a decision was correct. When those conditions change, you want to know
that you are reversing a decision deliberately rather than drifting away from
one by accident. That is what the *When to revisit* section is for.

## Format

Each file follows the same shape:

```markdown
# NNNN — Short title

**Status:** Accepted | Superseded by NNNN | Deprecated
**Date:** YYYY-MM-DD
**Deciders:** who

## Context
The situation and constraints. What makes this a real decision.

## Options considered
What else was on the table, stated fairly.

## Decision
What we chose, in the active voice.

## Consequences
What this makes easy, and what it makes hard. Be honest about the costs.

## When to revisit
The concrete trigger that makes this worth reopening.
```

## Rules

- **Numbered sequentially**, zero-padded: `0001-`, `0002-`.
- **Immutable once accepted.** A decision that changes gets a *new* ADR whose
  Status supersedes the old one; the old file stays, with its Status updated to
  point forward. The history is the value.
- **State options fairly.** An ADR that strawmans the alternative is worthless
  in two years when the alternative starts looking attractive.
- **Be honest in Consequences.** Every real decision has costs. An ADR listing
  only benefits means the decision was not actually made.
- **Write one whenever a choice is non-obvious** — per the `CLAUDE.md` checklist,
  a PR making a non-obvious decision without an ADR is incomplete.

## Index

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-monorepo.md) | Single monorepo, not multiple repositories | Accepted |
| [0002](0002-modular-monolith.md) | Modular monolith, not microservices | Accepted |
| [0003](0003-no-agent-framework.md) | Anthropic SDK directly, no agent framework | Accepted |
| [0004](0004-postgres-only-datastore.md) | PostgreSQL + pgvector as the only datastore | Accepted |
