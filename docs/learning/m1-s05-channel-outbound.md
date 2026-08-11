# S05 — Channel gateway outbound, conversation state, logging · learning notes

**Slice:** M1 / S05 · **Commits:** `33c935b`, `60a75d1` · **Status:** built and verified

---

## What we built

The other half of the loop. A traveller's message can now be replied to, the
reply is recorded on the same conversation, delivery receipts are applied to
the message they refer to, and none of it writes a phone number or a message
body to a log.

Plus the architecture rules turned into tests, after the module boundary rule
was broken twice in five slices — both times by the person who wrote it down.

---

## The concepts

### 1. `Protocol` and structural typing

Most typed languages use **nominal** typing: a class satisfies an interface
because it *declares* that it does. Python's `Protocol` is **structural**: a
thing satisfies it because it *has the right shape*.

```python
class ChannelAdapter(Protocol):
    async def send_text(self, *, to: str, text: str) -> OutboundResult: ...
```

`cloud_api` and `console` satisfy this with no base class, no registration and
no import of the protocol at all. In fact they are not classes — they are
**modules**, and a module with functions of the right signatures satisfies a
Protocol perfectly well.

Two practical consequences:

- **mypy checks it.** `cast(ChannelAdapter, cloud_api)` is verified against the
  protocol, so an adapter with a wrong signature is a lint failure rather than
  a 3am `AttributeError`.
- **Adapters do not depend on us.** With an abstract base class, every adapter
  must import and inherit from our type. With a Protocol the dependency points
  only one way. That is *dependency inversion* with less ceremony.

This is the same shape as the availability router in S06: one interface, three
provider slots, callers unaware of which one answered.

### 2. `async`/`await` and what actually blocks

Python's event loop runs one thing at a time. `await` marks a point where a
coroutine can be suspended so the loop can run something else.

The critical distinction:

```python
await asyncio.sleep(1)  # yields — loop runs other work
time.sleep(1)  # blocks — the whole process stops
```

A blocking call inside async code freezes *every* concurrent conversation, not
just its own. That is why the stack is async end to end: `asyncpg` rather than
`psycopg2`, `httpx` rather than `requests`. One synchronous HTTP client in a
hot path silently converts a concurrent server into a sequential one.

### 3. `httpx`, and clients as connection pools

```python
async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
```

An `AsyncClient` is not just a request function — it owns a **connection pool**
and reuses TCP connections. Establishing a new HTTPS connection means a TCP
handshake plus a TLS handshake, which is expensive and dominated by round trips.

Our client is created per send, which is correct-but-not-optimal: at M1 we send
a handful of messages a minute. A long-lived module-level client is the right
answer at volume, and it comes with a lifecycle question (who closes it, and
when) that is better answered alongside the app's startup and shutdown hooks
than bolted on now.

### 4. Timeouts: bounding a resource you do not control

```python
timeout = settings.http_timeout_seconds
```

**Every** outbound call needs a timeout. A request with none waits as long as
the peer keeps the socket open — which can be forever.

The failure this prevents is not "one slow request". It is that each hung
request holds a coroutine, a connection and its memory indefinitely. Enough of
them and the process runs out of connections while looking perfectly healthy:
CPU idle, no errors, nothing being served. A timeout converts an unbounded
resource leak into a bounded, visible error.

### 5. Exponential backoff

```python
await asyncio.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))  # 0.5s, 1s, 2s
```

Retrying immediately adds load to something already struggling. If the service
is overloaded, a thundering herd of instant retries is how a brief wobble
becomes a sustained outage.

Doubling the wait gives the far end room to recover. At real scale you also add
**jitter** — a small random offset — so that many clients that failed
simultaneously do not retry simultaneously. With one sender, we do not need it
yet; with a fleet, you do.

### 6. Retry policy follows *what you know*, not *what failed*

This is the most transferable idea in the slice.

**Sending a WhatsApp message is not idempotent.** The Cloud API has no
idempotency key. So a retry after a request that actually succeeded delivers
the message twice, and the traveller watches us say the same thing again.

That means "retry on failure" is wrong. The right question is: *do I know this
did not happen?*

| Failure | Retry? | What we know |
|---|---|---|
| `ConnectError` / `ConnectTimeout` | **Yes** | The request never reached Meta. It cannot have been processed. |
| `429`, `500`–`504` | **Yes** | Meta explicitly says it did not handle this one. |
| `ReadTimeout` | **No** | We sent it and heard nothing. It may well have been delivered. |
| Other `4xx` | **No** | Deterministic. It will fail identically. |

The `ReadTimeout` row is a judgement about *this product*, not a universal
rule. A duplicate message is worse than a failed send **here**, because a
failed send is visible to an operator in the console and can be redone, while a
duplicate is invisible to us and visible to the customer.

For an idempotent operation — anything guarded by `run_once` from S03 — you can
retry freely, because the second attempt is a no-op. **Idempotency is what buys
you the right to retry**, which is a large part of why invariant #5 exists.

### 7. Order of operations: send, then record

```python
result = await adapter.send_text(...)
return await conversation_service.record_outbound(
    ..., external_message_id=result.external_message_id
)
```

Recording first would be tidier — you would have a row to attach the result to.
It would also mean a transcript containing messages the traveller never
received.

Neither order is perfect, because there is no transaction spanning our database
and Meta's servers. So you choose which failure you would rather have:

- **Record then send**, and a failure leaves us claiming we said something we
  did not.
- **Send then record**, and a failure leaves a message delivered but missing
  from our transcript.

We take the second. A missing record is a discrepancy an operator can spot and
repair; a phantom message is one nobody knows is wrong. This is the same
instinct as the retry policy — prefer the failure you can see.

### 8. Recording failed sends

```python
failed_reason = None if result.accepted else (result.error or "send failed")
```

A send that failed is still written to the transcript, with a reason and no
`sent_at`.

The temptation is to record only successes, so the transcript stays clean. But
the operator's question is never "what did we successfully send?" — it is "what
does this traveller know?" A failed reply is exactly the case where silence
does the most damage, because the desk believes it answered.

### 9. Delivery receipts: unordered, repeated, late

Receipts are the loop opened in S04 (`statuses` were parsed but unused) and
closed here. Three properties, all of which shape the code:

- **They arrive out of order.** `read` can land before `delivered`.
- **They are redelivered**, exactly like messages.
- **They arrive for messages we do not know**, including any sent before this
  system existed.

So `apply_delivery_status` only ever sets fields **forward**, never clears
them, and returns `False` rather than raising for an unknown message:

```python
if state == "delivered" and message.delivered_at is None:
    message.delivered_at = occurred_at
```

The `is None` guard is what makes it idempotent. Applying the same receipt
three times, or applying a stale one after a newer one, leaves the same state —
which `test_receipts_are_idempotent` pins down.

### 10. Structured logging

`print` produces prose. **Structured logging** produces events with fields:

```python
log.info("channel.reply", conversation_id=..., accepted=True, body_length=47)
```

Prose is searchable only by substring. Fields are queryable: *"every failed
reply in Kanyakumari last Tuesday"* is a filter rather than a grep. `structlog`
renders human-readably in development and as JSON in production, from one call
site, which is why `configure_logging(json_output=settings.log_json)` is the
only difference between the two.

**Event names are dotted and stable** — `channel.reply`, `channel.send.failed`
— because a dashboard filters on the name. Putting variable data in the message
string is what makes logs ungroupable.

### 11. PII: why the rule is absolute

`CLAUDE.md`: *"Never log message bodies, phone numbers in full, or payment
identifiers."*

Logs go where the database does not: aggregators, error trackers, a terminal in
a shared office, a screenshot in a support thread. They have different
retention, different access control, and nobody audits them. A message body in
a log is a traveller's private conversation sitting somewhere nobody
inventoried — and under India's DPDP Act it is personal data we have no basis
to keep there.

So we log the **shape**, never the content:

```python
redact_identifier("919812345678")  # "********5678"
body_shape("Is parking free?")  # {"body_length": 16, "body_empty": False}
```

The last four digits are enough for an operator to line a log up with a
conversation in front of them, and not enough to identify or contact anyone.
Length and emptiness debug truncation and empty-send bugs; the text never does.
If you need the text, read the database, where access is controlled and
retention is defined.

Note `redact_identifier` masks a short value **entirely** — keeping "the last
four" of a four-digit string would reveal all of it. Redaction functions fail in
the edge cases, which is why they get their own tests.

### 12. Business rules as data: the service window

WhatsApp permits free-form replies for 24 hours after the customer's last
message. Outside it, only pre-approved templates — which we do not have at M1.

That could have been a constant in the send path. Instead it is
`conversation.service_window_expires_at`, written when a message arrives, and
the service refuses clearly:

```python
raise ServiceWindowExpiredError("the 24-hour service window has closed; ...")
```

Two benefits. The console can *show* an operator that a conversation has gone
cold, because it is a queryable column rather than a calculation buried in a
function. And we fail with our own error rather than discovering it as a
provider rejection — the difference between a product rule and an integration
bug.

### 13. Promoting an enum to shared vocabulary

`SenderKind` started in `conversation/models.py`. This slice needed `channel` to
name it when sending, so it moved to `enums.py` — the third to do so, after
`Channel` and `MessageType`.

The rule that has emerged, worth stating explicitly: **an enum lives in the
module that owns it until a second module needs it, then it becomes shared
vocabulary.** Duplicating it would be worse than sharing — two definitions of
`"operator"` that can drift apart is a bug that surfaces as a mismatched string
months later.

Note this is not a loophole in the boundary rule. The rule is about **ownership
of data**: models carry a table, a session and a mutation surface. An enum
carries a set of names.

---

## Reading our code

### The boundary rule, now enforced

`apps/api/tests/unit/test_module_boundaries.py` reads every source file with
`ast` and fails on five things: a cross-module `models` import, a cross-module
import bypassing `service`/`schemas`, a provider SDK outside `adapters/`, a
router importing models, and anything but `config.py` reading `os.environ`.

**Why this exists is the interesting part.** `CLAUDE.md` called a cross-module
models import "an automatic PR rejection" from day one, and it was violated
twice in five slices — both times by the author of the rule, both times caught
by chance. A rule enforced by attention is enforced only when you are paying
attention, which is never the moment you break it.

**Why `ast` rather than ruff**: ruff's `banned-api` is global, and these rules
are *contextual* — `conversation` may import its own models, `channel` may not.
No global ban expresses "except from inside itself". The empty
`banned-api` section had been sitting in `pyproject.toml` since S00 with a
comment promising it would be filled in; it could not be, and the comment now
says so.

**And it was verified red**, with a canary file violating all five rules, before
being deleted. A gate you have never seen fail is not known to work — the same
lesson as S01, and it keeps applying.

### `_post`: reading a retry loop

The loop reads as one decision per failure kind. Note that the `else` clause of
the `try` runs only when no exception fired, which is the idiomatic way to
separate "the call raised" from "the call returned something bad", and note that
`ReadTimeout` returns immediately rather than breaking to the retry — the whole
point of §6.

`log.warning("channel.send.read_timeout", to=redact_identifier(to), ...)` is
worth a look: the one case where we genuinely do not know what happened is also
the one worth an explicit log line, because it is the case a human may need to
reconcile by hand.

---

## The gotchas

**A blocking call in async code freezes every concurrent request**, not just
its own.

**Never retry a non-idempotent operation on an ambiguous failure.** Ask what
you *know*, not what broke.

**Every outbound call needs a timeout.** No timeout means an unbounded wait and
a leaked coroutine.

**Retrying immediately makes an overload worse.** Back off, and add jitter once
there is more than one sender.

**Receipts arrive out of order, repeated, and for unknown messages.** Set
fields forward only; never clear.

**Recording before sending** puts messages in the transcript that were never
delivered.

**Only logging successful sends** hides exactly the case where the desk thinks
it replied and did not.

**Redaction breaks on short values.** `"1234"` keeping "the last four" reveals
everything.

**Variable data in a log message string** makes events ungroupable. Put it in
fields.

**An `AsyncClient` per request** discards connection reuse. Fine at our volume,
wrong at scale — and the fix has a lifecycle question attached.

---

## Check yourself

1. `cloud_api` is a module, not a class, and never imports `ChannelAdapter`.
   How does it satisfy the protocol, and what checks that it does?
2. Why is `ConnectTimeout` retried but `ReadTimeout` not, when both are
   timeouts?
3. What makes an operation safe to retry? Which of our operations are, and why?
4. Why send before recording, given it can leave a delivered message missing
   from the transcript?
5. A receipt for a message arrives twice, and a `read` arrives before its
   `delivered`. What does our code do in each case, and which line makes that
   true?
6. Why is `service_window_expires_at` a column rather than a calculation in the
   send path?
7. What is wrong with logging `f"sent reply to {phone}"`, in two separate ways?
8. Why does `redact_identifier("1234")` return `"****"` rather than `"1234"`?
9. `ruff`'s `banned-api` cannot express the module boundary rule. Why not?
10. The boundary tests passed the moment they were written. Why was that not
    sufficient evidence they worked?

## Going deeper

- **`Protocol`** — PEP 544, and the mypy docs on protocols. The section on
  protocol variance is worth skipping until you need it.
- **asyncio** — "Developing with asyncio" in the standard library docs;
  specifically the debug-mode section, which catches blocking calls.
- **httpx** — the "Async Support" and "Timeouts" pages.
- **Retries** — AWS's "Timeouts, retries and backoff with jitter" is the
  clearest short treatment, and the jitter section explains what we have not
  needed yet.
- **structlog** — the "Why structured logging?" introduction.
- **DPDP Act 2023** — worth a skim before M5's compliance pass; the data
  minimisation principle is what this slice's logging rules implement.

---

**Next:** S06 — the availability router and the manual provider. Invariant #3:
one interface, three provider slots, only one implemented. It is the same
structural-typing idea as this slice's `ChannelAdapter`, applied to the
mechanism the whole business runs on.
