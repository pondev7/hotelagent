# S06 — Availability router and the manual provider · learning notes

**Slice:** M1 / S06 · **Commit:** `5aa8feb` · **Status:** built and verified

---

## What we built

The mechanism the business actually runs on. A traveller asks whether a room is
free; the router picks a provider based on the hotel's tier; the manual provider
puts a phone call on an operator's queue and answers `PENDING`; the operator
rings the hotel and logs what they heard; the answer comes back and a row lands
in the dataset.

Two of the three provider slots are empty and raise. That is not an oversight —
it is the entire content of invariant #3.

---

## The concepts

### 1. A `Protocol` as a routing table

S05 used `Protocol` for one interface with two implementations. Here it becomes
a dispatch table:

```python
_PROVIDERS: dict[IntegrationTier, AvailabilityProvider] = {
    IntegrationTier.MANUAL: manual,
    IntegrationTier.BOT: bot,
    IntegrationTier.LIVE: live,
}
```

The alternative is a chain of `if tier == ...: elif ...`. The table is better
for reasons that compound:

- **Adding a tier is one line**, in one place, rather than a branch threaded
  through every function that cares.
- **The mapping is data**, so it can be inspected and tested directly —
  `test_every_tier_has_a_provider_slot` asserts the table, not behaviour.
- **Exhaustiveness is visible.** With an `if` chain you discover a missing case
  at runtime; with a table you see the gap by reading it.

Worth noting what is *absent*: no cast. mypy accepts the modules as satisfying
`AvailabilityProvider` on their shape alone. I had written `# type: ignore` on
all three lines and mypy reported them as unnecessary — a small demonstration
that structural typing does what it claims.

### 2. Building the seam before the implementation

`docs/milestones.md` §0 states the organising principle: **build boundaries
early and implementations late.** This slice is the clearest instance.

Only Tier C exists today. Tier B arrives at M3, Tier A at M4. We could have
written `check_availability` to raise a call task directly and generalised later.

The reason not to is specific rather than aesthetic. The agent's conversation
flow — greet, qualify, shortlist, check, wait, confirm — is *identical* in all
three cases; only the wait message differs. Code written against "check means
raise a call task" bakes that assumption into every caller, so generalising
later means changing the agent's core flow, the conversation states, the ops
console and the tests together. Filling in a stub changes one file.

Days now, months later. That asymmetry is the whole argument.

### 3. Stubs must fail loudly

```python
raise NotImplementedError(
    "Tier B (hotelier bot) arrives at M3. "
    f"Hotel {request.hotel_id} is marked 'bot' but no bot provider exists yet."
)
```

The tempting alternative is to return `UNKNOWN` so nothing crashes.

That would be worse than having no stub at all. Someone sets a hotel to `bot` in
the database — an operator experimenting, a data import, a hopeful founder — and
the system produces confident, plausible, wrong answers about rooms it cannot
see. Nobody notices, because nothing looks broken.

**A stub that fails quietly converts a configuration error into a data error.**
The error message names the milestone and the hotel, so whoever hits it knows
both what happened and when it will work.

### 4. `PENDING` as a first-class answer

The most important design choice in the slice:

```python
class AvailabilityStatus(enum.StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    PENDING = "pending"
    UNKNOWN = "unknown"
```

A phone call takes minutes. A function that waited for one would hold a
coroutine, a database session and a conversation for that whole time — and with
thirty concurrent travellers you would have thirty stalled conversations.

So the manual provider **starts** the answering process and returns immediately
with an ETA. The real-world asynchrony is modelled as *state* rather than as a
blocking call.

This is a generally useful move: when an operation depends on something outside
your process that takes human time, represent the waiting explicitly rather than
hiding it behind a call that eventually returns. The traveller sees *"Checking
with the hotel — about 2 minutes ⏳"*, which `docs/vision.md` §4.1 requires be
honest — never fake instant availability we do not have.

### 5. `UNKNOWN` is not `UNAVAILABLE`

The subtlest decision here, and it is about data rather than code.

An operator rings the hotel. Nobody answers. What do we record?

The convenient answer is "unavailable" — the traveller cannot have the room
either way. It is also **false**, and falsehood in this table is expensive,
because `availability_observation` is not a log. It is the training set for M5's
prediction model (`docs/vision.md` §2.4), the thing the milestone plan calls the
only genuinely defensible asset in the business.

Record `NO_ANSWER` as unavailable and you teach a future model that a hotel
which was probably half empty was full. Do that through a season and the model
learns your reception's phone habits rather than the town's occupancy.

So:

```python
_OUTCOME_TO_STATUS = {
    CallOutcome.AVAILABLE: AvailabilityStatus.AVAILABLE,
    CallOutcome.UNAVAILABLE: AvailabilityStatus.UNAVAILABLE,
    CallOutcome.NO_ANSWER: AvailabilityStatus.UNKNOWN,
    CallOutcome.UNREACHABLE: AvailabilityStatus.UNKNOWN,
}
```

…and `UNKNOWN` writes no observation at all. The dataset stays smaller and
honest.

**The general principle: distinguish "the answer is no" from "there is no
answer".** Most systems conflate them, and it is invisible right up until
someone trains something on the result.

### 6. One-directional dependencies, and the cycle we avoided

There was a real design problem here. The manual provider needs to **create** a
call task, which `ops` owns. Resolving a call task needs to **write an
observation**, which `availability` owns.

The obvious arrangement gives you `availability → ops` and `ops → availability`
— a cycle. Cycles are bad beyond the import errors: two modules that call each
other cannot be understood, tested, or extracted separately. They are one module
wearing two names.

The resolution was to ask **who owns the meaning**:

- `ops` owns the *work* — which hotel to ring, who has it, what they typed in.
- `availability` owns the *meaning* — what that answer says about a room.

So the resolution path lives in `availability`, which calls `ops` to mark the
task resolved. `ops` never calls back. One direction, no cycle:

```
availability.resolve_manual_check()
    ├─ ops.get_call_task()
    ├─ ops.record_call_outcome()
    └─ availability.record_observations()
```

When you find a cycle, the fix is usually not a technical trick — it is
noticing that one of the two modules has been given a responsibility belonging
to the other.

### 7. Keeping three things in one transaction

`resolve_manual_check` marks the task resolved, writes the observation, and
returns the answer. All three share one transaction, deliberately.

The alternative — ops resolves, then the caller writes the observation — would
eventually produce resolved tasks with no dataset row, whenever the second step
failed or a caller forgot. And a missing observation is invisible: nothing looks
broken, the dataset is just quietly incomplete.

**When two writes must either both happen or neither, put them behind one
function, not two calls in a caller.** The transaction is what makes it true;
the single function is what stops someone splitting them.

### 8. Deduplication before idempotency

```python
existing = await ops_service.find_open_task(...)
if existing is not None:
    return _pending(existing.call_task_id)
```

Two checks for the same hotel, dates and conversation reuse one call task.

This is not quite the `run_once` idempotency of S03 — there is no key and no
unique constraint. It is a *business* rule: an operator must not ring the same
hotel twice about the same question, because the hotel would rightly find it
odd and the second call costs money for no information.

Under real concurrency two simultaneous checks could still slip through. That is
tolerable here — the cost is one wasted phone call, not a double charge — and
worth naming rather than pretending otherwise. The money paths get the
database-enforced version.

### 9. Claim semantics

```python
if task is None or task.status is not CallTaskStatus.OPEN:
    return False
```

Two operators must not ring the same hotel. `claim_call_task` checks the
**current** row, not the one the console rendered a minute ago, and returns
`False` rather than raising — "someone beat you to it" is an ordinary outcome,
not an error.

This is the shape of optimistic concurrency, which returns properly in S10 when
the console makes it visible and again at M4 for booking confirmation.

### 10. A night is the unit

```python
@property
def nights(self) -> list[date]:
    span = (self.check_out - self.check_in).days
    return [self.check_in + timedelta(days=n) for n in range(span)]
```

Saturday to Sunday is **one** night, not two dates. A three-night stay confirmed
available yields three observations.

Getting this unit right matters because the dataset is meant to answer "is this
hotel likely free on *this night*?" Storing a stay range instead would force
every future query to decompose it, and half of them would do it slightly
differently.

Note this is a small inference: the operator confirmed the stay as a whole, and
we record each night as available. That is sound — a hotel confirming a
three-night stay is confirming all three nights — but it is an inference, and
worth knowing you made it.

### 11. SQLAlchemy's model registry, and a bug that hides

The slice's real bug, and it never appeared in the test suite.

Running a script outside pytest produced:

```
NoReferencedTableError: Foreign key associated with column
'call_task.conversation_id' could not find table 'conversation'
```

`ForeignKey("conversation.id")` is resolved by **name**, against
`Base.metadata` — which only contains tables whose model module has actually
been imported. The script imported `ops` and `availability`, never
`conversation`, so the target table did not exist as far as SQLAlchemy knew.

Why it hid: the API works because `main.py` transitively imports nearly
everything; the tests work because test modules import what they assert on. The
failure needs an entry point that imports *less* — a worker, a script, a
management command — which is exactly the code you write last and test least.

The fix is `db/registry.py`: one module importing every model, imported by every
entry point. `alembic/env.py` now uses it too, replacing its own duplicate list —
which had the same failure mode with a nastier symptom, since a model missing
from *that* list makes autogenerate produce a migration **dropping the table it
cannot see**.

And a test asserts the registry stays complete, because "remember to add your
model to two places" is not a plan.

### 12. The test that was wrong

That registry test failed the first time it ran, and for the wrong reason.

```python
from hotelagent.modules.ops import models as _ops
```

In Python's AST this is an `ImportFrom` whose `module` is
`hotelagent.modules.ops` and whose *alias* is `models`. I compared against
`hotelagent.modules.ops.models`, so nothing ever matched and the test reported
every module missing.

It went red when I removed a model — the behaviour I was checking for — so the
canary "passed". **A test can be broken and still fail at the right moment.**
The tell was the message: it named modules that were plainly present. Reading
the failure output rather than just its colour is what caught it.

---

## Reading our code

### `check_availability` — the whole router in fifteen lines

```python
hotel = await inventory_service.get_hotel_for_availability(session, request.hotel_id)
if hotel is None or not hotel.is_active:
    raise UnknownHotelError(...)

provider = provider_for(hotel.integration_tier)
result = await provider.check(session, request, hotel)

if result.status in (AvailabilityStatus.AVAILABLE, AvailabilityStatus.UNAVAILABLE):
    await record_observations(...)
```

Three things worth noticing.

**It asks `inventory` through a service function** returning a narrow Pydantic
schema — `HotelAvailabilityContext`, with five fields — rather than importing
the `Hotel` model. The router cannot reach the rest of the hotel record, let
alone mutate it. A schema that returned everything would couple everything.

**The observation is written here, not in the provider.** A Tier A provider
answering instantly gets the same treatment as a Tier C call resolving later,
without each provider having to remember. Invariant #8 is enforced at the
router, which is the one place all three paths pass through.

**`PENDING` writes nothing yet.** Nothing has been learned; the observation
comes when the call comes back.

### Errors in the module's own vocabulary

`UnknownHotelError` and `UnknownCallTaskError` are plain `RuntimeError`
subclasses, not `HTTPException`. Per `CLAUDE.md`, services never raise HTTP
concepts — S07 introduces the `HotelAgentError` hierarchy and the mapping to
status codes, and these will move under it.

---

## The gotchas

**A stub returning a plausible value** turns a configuration error into a silent
data error. Raise.

**"No answer" is not "no room".** Conflating them corrupts a dataset in a way
nobody notices until something is trained on it.

**Blocking on human-time work** stalls the coroutine, the session and the
conversation. Model the wait as state.

**Mutual imports between modules** are a signal that a responsibility is in the
wrong place, not a problem to solve with a lazy import.

**Two writes that must happen together** belong behind one function, in one
transaction.

**A `ForeignKey` resolves by name against `Base.metadata`**, so an unimported
model breaks a *different* table's flush, in whichever entry point imports least.

**A duplicate model list** (registry and `alembic/env.py`) drifts. One source.

**A test can fail for the wrong reason** and look like it works. Read the
message, not the colour.

**Dedup by query is not idempotency.** It is a business rule with a race window;
say so, and use the database for anything involving money.

---

## Check yourself

1. Why does `bot.py` raise instead of returning `UNKNOWN`?
2. What would have to change, across the codebase, if `check_availability` had
   been written to raise a call task directly and generalised at M3?
3. An operator rings and nobody picks up. What is recorded, and what is
   deliberately *not* recorded — and why does it matter more in a year?
4. `availability` calls `ops`, and `ops` never calls `availability`. What made
   that the right direction rather than the reverse?
5. Why do the task resolution and the observation write share one transaction?
6. A stay from the 15th to the 18th produces how many observation rows, and
   what inference did we make?
7. Why did `NoReferencedTableError` appear in a script but never in the tests?
8. `alembic/env.py` used to keep its own list of model imports. What is the
   worst thing that could have happened if someone forgot to add one?
9. mypy reported the `# type: ignore` comments on the provider table as
   unnecessary. What does that tell you about `Protocol`?
10. The registry test failed the first time it ran, which is what I wanted. Why
    was that not evidence it was correct?

## Going deeper

- **Strategy pattern** — any design-patterns reference; the useful framing is
  "behaviour selected at runtime by data", which is exactly the tier table.
- **`Protocol`** — PEP 544 again, this time the section on protocols as
  structural interfaces for modules.
- **SQLAlchemy metadata** — "Describing Databases with MetaData", especially how
  `ForeignKey` resolves string targets.
- **Data quality** — anything on missing-data semantics; the distinction between
  "missing", "not applicable" and "zero" is the same one as §5 here, and gets
  expensive in exactly the same way.
- **`docs/vision.md` §2.4** — worth rereading now that the observation table
  exists. The three things the tier model buys are all downstream of this slice.

---

**Next:** S07 — the API surface and generated contracts. Thin routers, the
`HotelAgentError` hierarchy mapped to status codes, `city_id` scoping applied
consistently, and `make contracts` turning OpenAPI into TypeScript the ops
console cannot drift from.
