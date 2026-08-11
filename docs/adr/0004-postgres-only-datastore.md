# 0004 — PostgreSQL + pgvector as the only datastore (with Redis for ephemera)

**Status:** Accepted
**Date:** 2026-08-11
**Deciders:** Founding team

## Context

HotelAgent's storage needs span several shapes that are conventionally served by
different products:

| Need | Conventional answer |
|---|---|
| Relational core (hotels, bookings, ledger) | PostgreSQL / MySQL |
| Semi-structured payloads (webhooks, traces) | MongoDB |
| Vector search over the hotel knowledge base | Pinecone / Weaviate / Qdrant |
| Background job queue | RabbitMQ / Kafka / SQS |
| Session state and soft holds | Redis |
| Full-text search over hotel descriptions | Elasticsearch |

Adopting the conventional answer for each would mean six systems to run, back
up, monitor, secure and keep consistent — before the first booking.

Two facts bound the problem. The data is small: fifty hotels, a few thousand
bookings a year at launch, and a knowledge base of thousands of chunks, not
millions. And **money lives here** — the ledger requires real transactions, and
cross-datastore consistency is precisely where money goes missing.

## Options considered

**Best-of-breed per workload.** Each component optimal in isolation. Costs:
operational surface, no cross-store transactions, six failure modes, six
backups, and a restore procedure nobody rehearses.

**Postgres for everything it can plausibly do**, plus Redis for state that is
genuinely allowed to vanish. Postgres 16 covers relational, `JSONB` for
semi-structured, `pgvector` for embeddings, `tsvector` for full-text, and
`SELECT ... FOR UPDATE SKIP LOCKED` for queue semantics.

## Decision

**PostgreSQL 16 + pgvector is the only datastore.** Redis holds sessions, cache
and rate limiting. Background jobs run on **arq** (Redis-backed, async-native),
not on a message broker.

The `pgvector/pgvector:pg16` image is used from day one — including at S00, when
nothing needs vectors — so enabling the extension at M3 is a migration rather
than an image change and a data reload.

## Consequences

**Easier:**
- One thing to back up, and therefore one restore to rehearse. `docs/milestones.md`
  §5 requires a *tested* restore; that is achievable against one system and
  quietly skipped against six.
- **Transactional integrity across the whole domain.** A booking, its
  `BookingEvent` and its `LedgerEntry` commit or roll back together. Invariants
  #5 and #6 are enforceable by the database rather than by hope.
- One connection pool, one set of credentials, one monitoring surface.
- Stage 2 of the hosting ladder is a single `DATABASE_URL` change to a managed
  Postgres.
- Joins across what would otherwise be separate stores — "which hotels did we
  phone last week that also have a pending payable" is one query.

**Harder:**
- Each workload is served by something less specialised than a dedicated
  product. pgvector is slower than Pinecone at millions of vectors; we will have
  thousands. Postgres-as-a-queue is weaker than Kafka above thousands of events
  per second; we will have single-digit events per minute.
- One system is a single point of failure, and one bad query can affect
  everything. Mitigated by managed Postgres at Stage 2 and by keeping the
  workload small.
- Redis is deliberately treated as **losable**. Session state may vanish. Soft
  holds may **not** — so if Redis is ever run without persistence, holds move to
  Postgres. This is called out in `docs/milestones.md` §5 and is a real trap.

## When to revisit

Per `docs/milestones.md` §9, each has its own trigger:

- **A dedicated vector database** — millions of chunks *with measured latency
  problems*, not merely a large number of rows.
- **A message bus (Kafka/RabbitMQ)** — sustained thousands of events per second.
- **Elasticsearch** — when Postgres full-text search demonstrably fails a real
  ranking requirement.
- **Splitting Postgres out to a managed service** — M5, at real traffic. This is
  Stage 2 of the hosting ladder and is expected, not a reversal of this ADR.

In every case the trigger is a **measurement**, not an intuition that we have
outgrown it.
