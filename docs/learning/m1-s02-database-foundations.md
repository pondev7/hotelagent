# S02 — Database foundations and the first migration · learning notes

**Slice:** M1 / S02 · **Commit:** `9a13836` · **Status:** built and verified

---

## What we built

The shape every table in HotelAgent will inherit: a time-sortable UUID primary
key, UTC timestamps, and the `city_id` tenancy key. Plus the machinery around
it — a declarative base with a fixed constraint-naming convention, one pooled
async engine, a request-scoped session, and Alembic wired for async.

Two real tables, `city` and `hotel`, created by a hand-written migration that
was proven to apply **and reverse** against real PostgreSQL.

`/health` also split into liveness and readiness, which turns out to be a
distinction with real operational consequences.

---

## The concepts

### 1. What an ORM is, and what it costs

An **Object-Relational Mapper** maps database rows to objects. Instead of

```sql
SELECT id, name, commission_rate FROM hotel WHERE city_id = $1;
```

you write

```python
await session.scalars(select(Hotel).where(Hotel.city_id == city_id))
```

and get `Hotel` objects with typed attributes.

What you gain: composable queries built in Python, types your editor and mypy
understand, and a **unit of work** that batches changes into one transaction.

What you pay: a layer of indirection where SQL used to be, and the ever-present
risk of writing something innocuous that emits a catastrophic query. The
canonical example is the **N+1 problem** — looping over 50 hotels and touching
`hotel.city` inside the loop issues 51 queries instead of one join. Async
SQLAlchemy actually protects you here: lazy loading raises rather than silently
firing a query, forcing you to say what you want loaded.

The rule we follow: the ORM writes the queries, but you should always be able to
say what SQL a line produces. `HOTELAGENT_DATABASE_ECHO=true` prints it, which
is the fastest way to build that intuition.

### 2. SQLAlchemy 2.0's declarative style

SQLAlchemy 2.0 reworked model declaration around **type annotations**:

```python
class City(Base, IdMixin, TimestampMixin):
    __tablename__ = "city"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str | None] = mapped_column(String(120))
```

`Mapped[str]` is not decoration — SQLAlchemy reads it. `Mapped[str]` implies
`NOT NULL`; `Mapped[str | None]` implies nullable. mypy checks your usage
against the same annotations, so `city.state.upper()` is flagged as possibly
`None` before it ever runs. One declaration, understood by the ORM and the type
checker together.

### 3. Sync vs async drivers, and why `asyncpg`

A **driver** speaks the database's wire protocol. `psycopg2` is synchronous: a
query blocks the thread until the answer arrives. `asyncpg` is asynchronous: it
yields control back to the event loop while waiting.

This matters because of what HotelAgent spends its time doing. A booking
conversation waits on Postgres, then the WhatsApp API, then a payment gateway.
With a sync driver each wait occupies a whole thread. With async, one thread
handles hundreds of concurrent waits — which is the same argument that chose
ASGI in S00, one layer further down.

Note the URL: `postgresql+asyncpg://...`. The part after `+` selects the driver.

### 4. Connection pooling

Opening a PostgreSQL connection is expensive: a TCP handshake, authentication,
and a whole new backend *process* on the server. Doing that per request is
wasteful, and a few thousand connections will take a database down.

A **pool** keeps a set of open connections and lends them out:

```python
create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
```

`pool_size=5` is the steady-state pool; `max_overflow=10` allows 10 more under
burst, for 15 maximum. `pool_pre_ping=True` sends a cheap `SELECT 1` before
lending a connection out — without it, a connection killed by a database restart
or an idle timeout is discovered by whichever unlucky request receives it, as a
confusing error far from the cause.

The engine is created once per process, which is what `@lru_cache` on
`get_engine()` guarantees. Creating engines per request would defeat the entire
purpose of pooling.

### 5. Sessions, transactions and the unit of work

**A session is not a connection.** It is a *unit of work*: it tracks objects you
have loaded or modified, and at `commit()` works out the SQL needed and sends it
in one transaction.

A **transaction** is all-or-nothing. `BEGIN`, then a series of statements, then
either `COMMIT` (all applied) or `ROLLBACK` (none applied). This is the property
that makes invariant #6 enforceable: a booking, its `BookingEvent` and its
`LedgerEntry` commit together or not at all. There is no state where the money
moved but the event did not.

Our dependency encodes exactly that:

```python
async with get_sessionmaker()() as session:
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
```

Handler returns → commit. Handler raises → rollback. A half-applied write cannot
escape a failed request.

`expire_on_commit=False` deserves a note. By default, SQLAlchemy marks objects
stale after commit, so touching any attribute triggers a fresh `SELECT`. In
async code that raises instead of lazily loading — so you commit, return the
object, and serialisation explodes. Turning it off keeps attributes usable after
commit.

### 6. FastAPI dependency injection

```python
async def ready(session: Annotated[AsyncSession, Depends(get_session)]) -> JSONResponse:
```

`Depends(get_session)` tells FastAPI to call `get_session()` and pass the result
in. Because `get_session` is a generator (it `yield`s), FastAPI runs the code
after the `yield` when the request finishes — which is how commit/rollback and
connection return happen automatically.

The real payoff is testability: a test can override the dependency to supply a
different session, with no change to the handler.

### 7. Migrations, and why `create_all` is banned

SQLAlchemy can create tables directly from your models with
`Base.metadata.create_all()`. It is also forbidden outside tests, and the reason
matters.

`create_all` only creates what is missing. It cannot alter an existing column,
rename anything, or transform data. So it works exactly once — on an empty
database — and from the second change onward you have no path from the schema
you have to the schema you want.

A **migration** is that path, written down: a small, ordered, version-controlled
script describing one schema change forward (`upgrade`) and backward
(`downgrade`). Migrations form a chain, each naming its predecessor, and the
database records which one it is on in the `alembic_version` table.

### 8. Alembic

**Alembic** is SQLAlchemy's migration tool. Its pieces:

- `alembic.ini` — configuration. Ours deliberately has **no** `sqlalchemy.url`;
  the URL comes from `Settings` (invariant #9), and tests override it in-process.
- `alembic/env.py` — the script Alembic runs to connect. Ours is the async
  variant, discussed below.
- `alembic/versions/` — the migrations, each with a revision id and a
  `down_revision` forming the chain.

**Autogenerate** compares your models against the live database and drafts a
migration. It is a *drafting tool*, not an oracle. It reliably misses table and
column renames (it sees a drop and an add, which destroys data), `CHECK`
constraint changes, and — as this slice hit directly — PostgreSQL enum types.

Which is why our first migration is hand-written. We then used autogenerate in
reverse, as a **drift check**: after applying our migration, autogenerating
again produced an empty migration, proving the models and the migration agree.
That is a genuinely useful trick to keep repeating.

**The async wiring.** Alembic's internals are synchronous, so `env.py` opens an
async connection and hands it over:

```python
async with engine.connect() as connection:
    await connection.run_sync(_run)
```

`run_sync` runs sync code on an async connection using greenlets. You do not
need to understand the mechanism; you do need to know this is the required
shape, because the default template is sync-only.

**The trap in `env.py`** is worth internalising:

```python
from hotelagent.modules.inventory import models as inventory_models  # noqa: F401
```

Importing models is what populates `Base.metadata`. Autogenerate compares
metadata to the database — so a model that is *not* imported here is invisible,
and Alembic will cheerfully generate a migration **dropping the table it cannot
see**. Every new module's models get added to that list.

### 9. UUIDv7: why not auto-increment, why not v4

Our primary keys are UUIDv7, generated in Python. Three options were on the
table:

**Auto-increment integers** are compact and sort naturally, but they leak
business volume (a customer with booking #41 knows you have taken forty), they
require a database round-trip before you know the id, and they collide when
merging datasets from two cities.

**UUIDv4** is 122 random bits. Safe to expose and generatable offline, but
*random*, and randomness is expensive in a b-tree index: consecutive inserts
scatter across pages, so each commit dirties many pages. Insert throughput
degrades and the index fragments.

**UUIDv7** (RFC 9562) puts a 48-bit millisecond timestamp in the leading bits:

```
 48 bits  unix timestamp (ms)
  4 bits  version (0b0111)
 12 bits  counter — monotonic within a millisecond
  2 bits  variant (0b10)
 62 bits  random
```

Because time leads, ids sort by creation order and inserts append to the
right-hand edge of the index — the same locality auto-increment gives you —
while staying safe to expose and generatable without a round-trip.

**The counter is not optional.** Without it, two ids created in the same
millisecond order randomly against each other. Our implementation keeps a
counter under a lock, resets it each new millisecond, and if it exhausts its 12
bits, borrows a millisecond from the future rather than emitting a
non-monotonic id. `test_uuid7_values_are_time_sortable` generates 50 ids in a
tight loop — all in the same millisecond — and would fail without it.

Python 3.14 adds `uuid.uuid7()` to the standard library; we are on 3.12.

### 10. `timestamptz`, and why everything is UTC

PostgreSQL has two timestamp types, and the naming is actively misleading.

`timestamp without time zone` stores wall-clock digits with no offset. Two rows
saying `2026-08-12 06:00:00` might be four and a half hours apart, and nothing
records which.

`timestamptz` (`timestamp with time zone`) does **not** store a time zone
either. It converts the input to UTC, stores that instant, and converts back on
read. It is an unambiguous point in time. That is what you almost always want.

We use `timestamptz` everywhere, store UTC, and convert to Asia/Kolkata only for
display. Time zone handling is a *presentation* concern. Ignoring this is how
you get a 5:30 a.m. sunrise booking recorded on the wrong day.

The columns also use `server_default=func.now()`, so rows written by a
migration or by hand in `psql` get correct timestamps too — not only rows
written through the ORM.

### 11. `Numeric` for money, never float

```python
commission_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), ...)
```

Floats are binary fractions and cannot represent most decimal fractions
exactly. In Python, `0.1 + 0.2` is `0.30000000000000004`. One such error is
invisible; ten thousand of them through a ledger is a reconciliation failure
nobody can explain.

`Numeric(5, 2)` is exact decimal: 5 total digits, 2 after the point — enough for
`100.00`. It maps to Python's `Decimal`, which is also exact. `CLAUDE.md` fixes
money as `Numeric(12, 2)` in INR.

The `CHECK` constraint is the same instinct one layer lower:

```sql
CHECK (commission_rate >= 0 AND commission_rate <= 100)
```

Application code can be bypassed — a migration, a script, a psql session. A
database constraint cannot.

### 12. Mixins, MRO and `declared_attr`

A **mixin** is a class that contributes attributes to others without being a
base class in its own right. `Hotel(Base, IdMixin, CityScopedMixin, TimestampMixin)`
composes four sources; Python's **MRO** (method resolution order) linearises
them left to right.

`CityScopedMixin` needs `declared_attr`:

```python
@declared_attr
@classmethod
def city_id(cls) -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("city.id", ondelete="RESTRICT"), ...)
```

A plain class attribute would be created **once** and shared by every model
using the mixin — but a `Column` object belongs to exactly one table, and a
`ForeignKey` cannot be shared. `declared_attr` makes it a function SQLAlchemy
calls once per subclass, so each gets its own column.

`ondelete="RESTRICT"` means the database refuses to delete a city that still has
hotels. The alternative, `CASCADE`, would silently delete every hotel with it —
not a behaviour you want available on the tenancy root.

### 13. PostgreSQL enums, and the broken-downgrade trap

`IntegrationTier` is a Python `StrEnum` mapped to a **native PostgreSQL enum
type**. Postgres validates the value, which is stronger than a string column.

Two sharp edges, both of which this slice hit:

**SQLAlchemy stores enum *names* by default, not values.** `IntegrationTier.MANUAL`
would be stored as `"MANUAL"`, not `"manual"`. To get the values you must say so:

```python
Enum(IntegrationTier, values_callable=lambda e: [m.value for m in e])
```

**`DROP TABLE` does not drop the enum type.** The type is an independent
database object that outlives the column using it. A downgrade that drops the
tables and stops looks like it worked — and then the next `upgrade` fails with
*"type integration_tier already exists"*. Our downgrade drops both explicitly.
This is the most common broken `downgrade()` in Postgres codebases, and it is
exactly why the exit criterion required testing the reverse direction.

### 14. Constraint naming conventions

`db/base.py` sets:

```python
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    ...
}
```

Left to itself, PostgreSQL invents constraint names. Those names differ between
the database autogenerate ran against and the one the migration later runs on,
so a `downgrade()` that says `DROP CONSTRAINT ck_hotel_a1b2c3` fails in
production.

With a convention fixed, every constraint has a deterministic name derived from
its table and columns, and `downgrade()` can always name what it drops.

**This must be set before the first migration.** Changing it later means
renaming every constraint in a live database — which is precisely the kind of
cheap-now, expensive-later decision the invariants exist to catch.

### 15. Liveness vs readiness

Two probes, because the correct *reaction* differs:

- **Liveness** (`/health`) — is the process alive? A failure should **restart**
  the container. It deliberately checks nothing downstream: restarting the API
  does not fix a database outage, it just adds a restart loop to an incident.
- **Readiness** (`/health/ready`) — can this instance serve traffic? It checks
  the database and returns **503** if not. A failure should **remove the
  instance from the load balancer**, not restart it.

Conflating them is a classic outage amplifier: the database wobbles, every
container fails its health check, the orchestrator restarts all of them at once,
and now you have a thundering herd of reconnects on top of the original problem.

### 16. CI service containers

Integration tests need a real database, so the CI job gained one:

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    options: >-
      --health-cmd "pg_isready -U hotelagent -d hotelagent"
      --health-interval 5s
```

GitHub starts the container alongside the job and publishes it on the runner's
`localhost` — which is why our config defaults point at `localhost` rather than
the Compose service name. The health options make the runner wait until Postgres
actually accepts connections; without them the first test races startup and
fails intermittently, which is the worst kind of failure to debug.

---

## Reading our code

### The two-URL problem

`config.py` defaults to `localhost`, while `docker-compose.yml` injects
`postgres`. This is not an inconsistency — it is the resolution of a real
tension:

- Host-side tooling (`make migrate`, pytest) runs **outside** the Compose
  network, where the database is `localhost:5432` via the published port.
- The api container runs **inside** it, where the same database is
  `postgres:5432`.

Defaults serve the host; Compose overrides for containers. Both are correct from
where they stand. This is the single most common Docker networking confusion,
and it appeared here as soon as real database access did.

### `tests/integration/conftest.py`

Integration tests use a **separate database** (`hotelagent_test`) so they never
touch development data. The fixture creates it on demand, connecting to the
`postgres` maintenance database first — because `CREATE DATABASE` cannot run
inside a transaction block, which is why raw asyncpg is used rather than the ORM.

The `alembic_config` fixture downgrades to `base` before *and* after each test,
so no test inherits another's schema.

The tests are deliberately **synchronous**. Alembic drives its own event loop
inside `env.py`; calling it from an `async def` test would nest event loops and
fail.

---

## The gotchas

**`create_all()` outside tests.** Works once, then leaves you with no path
forward. Alembic only.

**A model not imported in `env.py` is invisible to autogenerate** — and it will
generate a migration dropping that table.

**Autogenerate misses renames, `CHECK` constraints and enum types.** Always read
the generated migration before committing it.

**`DROP TABLE` leaves the enum type behind.** Untested downgrades hide this
until the next upgrade fails.

**SQLAlchemy stores enum names, not values, unless you pass `values_callable`.**

**`timestamp` and `timestamptz` are easy to confuse, and neither stores a time
zone.** Use `timestamptz`, store UTC.

**Float for money.** Always `Numeric`/`Decimal`.

**A shared `Column` in a plain mixin** raises on the second model. Use
`declared_attr`.

**`expire_on_commit=True` (the default) plus async** means attribute access
after commit raises rather than reloading.

**Compose service names vs localhost.** The same database has two addresses
depending on where you are standing.

**A CI service container without health options** races your tests.

---

## Check yourself

1. Why is `Base.metadata.create_all()` banned outside tests, given it does
   create the tables correctly?
2. What happens if you add a new model but forget to import it in `env.py`?
3. Why does UUIDv7 need a counter? What breaks in our test suite without one?
4. `drop_table("hotel")` runs successfully in a downgrade. What is still left in
   the database afterwards, and when do you find out?
5. Why does `config.py` default to `localhost` while `docker-compose.yml` says
   `postgres`? Are both right?
6. Why must the constraint naming convention be fixed *before* the first
   migration rather than added later?
7. Liveness fails and readiness fails. What should an orchestrator do
   differently in each case, and why does conflating them make an outage worse?
8. Why are the migration tests `def` rather than `async def`?
9. We used autogenerate even though the migration was hand-written. What for?

## Going deeper

- **SQLAlchemy 2.0** — the "ORM Quick Start" then the Session chapter. The
  "Migrating to 2.0" guide is worth skimming purely because most search results
  still show 1.x style.
- **Alembic** — the tutorial, then "Auto Generating Migrations", especially the
  section on what it cannot detect.
- **UUIDv7** — RFC 9562 §5.7. Short, and the bit layout diagram is the whole
  idea.
- **PostgreSQL** — the "Date/Time Types" chapter on `timestamptz`, and
  "Numeric Types" on why `numeric` exists.
- **Pooling** — SQLAlchemy's "Connection Pooling" page; the `pool_pre_ping`
  discussion explains a class of intermittent production error.

---

**Next:** S03 — the rest of the M1 entity set, the append-only event log, and
idempotency keys. Invariants #5 and #6 land there.
