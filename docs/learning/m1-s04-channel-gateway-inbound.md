# S04 — Channel gateway, inbound · learning notes

**Slice:** M1 / S04 · **Commit:** `8fe117b` · **Status:** built and verified

---

## What we built

The first slice that touches the outside world. A webhook endpoint that accepts
a WhatsApp delivery, proves it is authentic, normalises it into our own message
type, and stores it exactly once — however many times it arrives.

Two adapters produce the same normalised output: the real Cloud API one, and a
development one that needs no Meta account and no public URL.

It is also the first slice where the module boundary rule stopped being a
principle and started being a constraint that changed the design.

---

## The concepts

### 1. HTTP, quickly

An HTTP request is a **method**, a **path**, **headers**, and an optional
**body**. The response is a **status code**, headers and a body.

The methods that matter here:

- **GET** — retrieve. Must be *safe*: no side effects. Meta's subscription
  handshake is a GET precisely because it should change nothing.
- **POST** — submit. May have side effects. Deliveries arrive as POSTs.

Status codes come in families, and the family is the meaningful part:

| Range | Means | Ours |
|---|---|---|
| 2xx | Success | `200` — delivery accepted |
| 4xx | *You* got it wrong | `403` — bad signature |
| 5xx | *We* got it wrong | `503` — no city configured |

The 4xx/5xx distinction is not pedantry. It tells the caller whether retrying
could ever help. Meta retries on 5xx and gives up on 4xx — so choosing the wrong
one either loses messages or creates an infinite retry loop.

**Headers** carry metadata: `Content-Type` describes the body,
`X-Hub-Signature-256` carries Meta's signature. The `X-` prefix conventionally
marks a non-standard header.

### 2. Webhooks: the inversion

Normally *you* call an API. A **webhook** inverts that: you register a URL, and
the provider calls **you** when something happens.

The alternative is polling — "any new messages?" every few seconds — which is
wasteful when nothing is happening and still slow when something is. Webhooks
are push, so a traveller's message reaches us in milliseconds. Given our SLA is
a **first reply in under 30 seconds** (`docs/vision.md` §2.2), that matters.

The consequences shape everything else in this slice:

- **You are a server on the public internet**, so anyone can POST to that URL.
  Hence signature verification.
- **Delivery is at-least-once, never exactly-once.** Providers retry when
  unsure. Hence idempotency.
- **You must answer quickly.** A slow 200 looks like failure and triggers a
  retry, which is one of the main ways duplicates arise.

### 3. HMAC: proving who sent it

**A hash** (SHA-256) turns any input into a fixed-length digest. Same input,
same digest; any change produces a completely different one. But anyone can
compute a hash, so a hash alone proves nothing about *who* sent something.

**HMAC** (Hash-based Message Authentication Code) mixes a **shared secret**
into the hashing. Meta and we both know the app secret; nobody else does. Meta
signs the body, we recompute the same HMAC, and if they match we know two things
at once:

1. **Authenticity** — it came from someone holding the secret.
2. **Integrity** — the body was not modified in transit.

```python
expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
```

Without this, anyone who learns the URL could POST fake bookings.

### 4. Why the *raw* bytes

```python
raw_body = await request.body()
```

The signature covers the body **exactly as sent**. Parse that JSON and
re-serialise it and you may get different key order, different whitespace,
different unicode escaping — a different byte sequence, and a signature that can
never match.

So the router reads the raw bytes, verifies, and only then parses. Reversing
those two steps is a bug that looks like "signature verification randomly
fails", and people usually "fix" it by disabling verification.

### 5. Timing attacks and constant-time comparison

This is the subtlest security idea in the slice.

Comparing two strings with `==` returns **as soon as it finds a difference**. So
comparing against `"abc..."` takes fractionally longer if the attacker's guess
starts with `a` than if it starts with `z`. That difference is tiny — but it is
*measurable* over many requests, and it leaks how much of the prefix was
correct. An attacker guesses one character at a time, and a 64-character
signature falls in a few thousand requests rather than never.

```python
hmac.compare_digest(provided, expected)  # constant time
provided == expected  # leaks via timing
```

`compare_digest` always examines the whole input, so the duration says nothing
about the content. Use it for **any** comparison of a secret: signatures,
tokens, API keys, password hashes.

### 6. Failing closed

```python
if not app_secret or not header:
    return False
```

If the secret is not configured, verification **fails** rather than passes.

"Fail closed" versus "fail open" is a decision you make once per security check,
and getting it backwards is catastrophic: a deployment that forgets the
environment variable would silently accept forged requests from anyone. There is
a test named `test_an_empty_secret_fails_closed` for exactly this, because it is
the kind of thing a well-meaning refactor breaks.

### 7. Replay attacks, and why idempotency is the defence

Even with a valid signature, an attacker who captures a request can **send it
again** — the signature is still valid, because the body has not changed.

More mundanely, this happens by accident constantly: Meta redelivers whenever
our 200 was slow or lost.

Signature verification cannot help; the request is genuinely authentic. The
defence is **idempotency**: the message id is recorded, so the second and
subsequent arrivals write nothing.

```python
result = await run_once(
    session,
    scope=IDEMPOTENCY_SCOPE,
    key=f"{channel.value}:{external_message_id}",
    operation=store,
)
```

This is invariant #5's machinery from S03, used for the first time. Note that
security and reliability converge here: the same mechanism that defends against
a replay attack also prevents a duplicate customer message on a flaky network.

### 8. Pydantic v2

Pydantic validates and coerces data using type annotations. `InboundMessage` is
a schema, not a model — it has no database table and exists to move data across
boundaries with its shape guaranteed.

Two features used here:

**Frozen models.**

```python
model_config = ConfigDict(frozen=True)
```

Makes instances immutable. A normalised inbound message records something that
already happened; nothing downstream should be editing it. Immutability also
makes it safe to pass around without defensive copying.

**Default factories.**

```python
attachments: list[InboundAttachment] = Field(default_factory=list)
```

`= []` as a default would be the classic Python bug — one list shared by every
instance, so appending to one message's attachments appends to all of them.
`default_factory` builds a fresh one each time.

### 9. The adapter pattern and dependency inversion

Invariant #9 says no provider SDK or payload knowledge outside `adapters/`. This
slice is the first place it earns its keep.

`cloud_api.py` and `console.py` both expose `parse_webhook(payload) ->
InboundBatch`. The service picks one by configuration:

```python
if get_settings().channel_adapter == "cloud_api":
    return cloud_api.parse_webhook(payload)
return console.parse_webhook(payload)
```

That is **dependency inversion**: the service depends on a *shape* rather than a
specific implementation. The payoff is not theoretical — it is the reason this
slice exists at all while the BSP-versus-Cloud-API question is still open in
`docs/vision.md` §6. The decision blocks one file, not the milestone.

### 10. Tunnels, and why we do not need one

For a real provider to reach your laptop, your laptop needs a public URL.
Normally that means a tunnel — ngrok or similar — which gives you a public
address forwarding to `localhost`.

Tunnels are fine, and also: a URL that changes every restart, a Meta app config
to update each time, an account, and a dependency on someone else's uptime in
your inner development loop.

The console adapter removes all of it. `curl` a JSON body at
`/webhooks/whatsapp` and the entire path runs — service, idempotency, database,
response. You will still want a tunnel eventually, to test against the real
Cloud API. You just do not need one to *build*.

### 11. FastAPI routers and dependency injection

**A router** groups related endpoints, mounted onto the app:

```python
router = APIRouter(prefix="/webhooks", tags=["channel"])
app.include_router(channel_router)
```

`prefix` is prepended to every path in the group; `tags` groups them in `/docs`.
Each module owning its own router is what keeps `main.py` a wiring file.

**Parameter declarations** tell FastAPI where each argument comes from:

```python
mode: Annotated[str | None, Query(alias="hub.mode")] = None
signature: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None
session: Annotated[AsyncSession, Depends(get_session)]
```

The `alias` matters here because `hub.mode` is not a valid Python identifier —
aliases decouple the wire format from your code, which is the same instinct as
the whole normalisation boundary, one level down.

### 12. Thin routers, and where `HTTPException` may live

`CLAUDE.md`: *"Routers are thin: parse, call `service.py`, serialise. No
business logic and no ORM queries in a router."* And: *"Never raise
`HTTPException` below `router.py`."*

The second rule is the interesting one. `HTTPException` is an **HTTP** concept.
A service that raises it has decided that its caller is a web request — which
makes it unusable from a background worker, a CLI, or a test, without those
callers catching an exception that makes no sense to them.

So services signal failure in their own vocabulary, and the router translates:

```python
except service.ChannelConfigurationError as exc:
    raise HTTPException(status_code=503, detail=str(exc)) from exc
```

`from exc` preserves the original as `__cause__`, so the traceback shows both
the translation and the real cause. Dropping it discards the useful half.

### 13. Parsing defensively: skip, do not raise

```python
if not external_id or not sender:
    continue
```

The parser skips entries it cannot understand rather than raising.

Normally you want loud failures. Here the reasoning inverts, because of what a
failure *means* to the caller: an exception becomes a 500, Meta retries a few
times and then gives up — dropping **every** message in that delivery, including
the well-formed ones. Being strict costs real customer messages.

The same reasoning produces `MessageType.UNSUPPORTED`. A message type we cannot
render is still a message the traveller sent; recording it as unsupported lets
an operator see that *something* arrived. Dropping it silently means a customer
who thinks they told us something, and a desk that never saw it.

### 14. Providers batch

```python
for message in batch.messages:
```

One webhook can carry several messages. Handling only the first works perfectly
in every test you write by hand, and silently drops messages the first time two
arrive together — which happens under exactly the load where it hurts most.

---

## Reading our code

### The module boundary rule, in action

This slice is where the rule stopped being abstract. The gateway needs to store
a message. `Message` belongs to `conversation`. `channel` may not import it.

So the flow became:

```
router.py  →  channel/service.py  →  conversation/service.py  →  Message
                                  →  inventory/service.py    →  City.id
```

`channel/service.py` imports two *functions* and one *schema*. It never sees an
ORM instance, and it could not write to `message` if it wanted to.

The temptation was real: `from hotelagent.modules.conversation.models import
Message` would have saved a file and twenty minutes. It would also have meant
that extracting `conversation` later requires finding every module that learned
its table layout. Instead, `conversation` now has a public interface that says
exactly what it offers: `record_inbound(...) -> RecordedMessage`.

**Notice what the rule bought immediately**, not just eventually: the whole
find-or-create-user, find-or-open-conversation, store-idempotently sequence
lives in one place, so *any* future channel gets it for free.

### `_find_or_create_user`: the same concurrency lesson again

```python
await session.execute(
    pg_insert(User).values(...).on_conflict_do_nothing(index_elements=["channel", "external_id"])
)
user = await session.scalar(select(User).where(...))
```

Two messages from a first-time traveller can arrive in the same delivery, or in
two concurrent requests. Select-then-insert would let both find nothing and both
insert. This is the S03 idempotency pattern applied to a different problem —
the database arbitrates, because only it can.

### Testing an endpoint against a real database

```python
async def _use_test_session() -> AsyncIterator[AsyncSession]:
    yield session


app.dependency_overrides[get_session] = _use_test_session
```

FastAPI lets a test **replace a dependency**. The handler receives the test's
session, so everything it writes is inside the test's transaction and disappears
with the schema teardown. No mocking of the database, no separate code path —
the real handler, the real service, real SQL.

This is the practical reason dependency injection is worth the ceremony.

### Overriding settings in a test

```python
monkeypatch.setenv("HOTELAGENT_CHANNEL_ADAPTER", "cloud_api")
get_settings.cache_clear()
```

`get_settings` is `lru_cache`d (S00), so it reads the environment once. A test
changing an environment variable must clear that cache — **and clear it again
afterwards**, or the override leaks into every later test in the session. That
is the `settings_env` fixture's whole job, and this class of leak produces the
worst kind of failure: tests that pass alone and fail in a suite, or vice versa.

---

## The gotchas

**Verify before parsing.** The signature covers raw bytes; re-serialised JSON
will not match.

**Never `==` on a secret.** `hmac.compare_digest`, always.

**Fail closed.** Missing configuration must reject, never accept.

**A valid signature does not stop a replay.** Only idempotency does.

**4xx vs 5xx changes provider behaviour.** 5xx invites retries; 4xx ends them.
Returning 500 for a permanently malformed body creates a retry loop.

**`= []` as a Pydantic default** is shared across instances. `default_factory`.

**`lru_cache` on settings leaks between tests** unless cleared on both sides.

**Providers batch.** Loop over messages.

**Strict parsing loses messages.** Skip unparseable entries; a raise costs the
whole delivery.

**A slow 200 causes duplicates.** Answer fast; do slow work afterwards. This one
is latent in our code today — the handler writes to the database before
replying — and becomes real when the agent loop lands in M2.

---

## Check yourself

1. Why must the signature be verified against the raw body rather than the
   parsed-and-re-serialised JSON?
2. What does `hmac.compare_digest` protect against that `==` does not, and how
   would the attack actually work?
3. A request has a perfectly valid signature and is a replay of one from an hour
   ago. What stops it doing damage twice?
4. Why does a malformed body return 200 rather than 400?
5. Why can the console adapter skip signature verification without weakening
   production?
6. `channel/service.py` needs to write a `Message`. Why does it not import the
   `Message` model, and what did that cost?
7. What breaks if a test sets `HOTELAGENT_CHANNEL_ADAPTER` and forgets
   `get_settings.cache_clear()`?
8. Why is `InboundMessage` frozen?
9. Why does the parser record an unknown message type instead of skipping it,
   when it *does* skip an entry with no sender?

## Going deeper

- **Meta's webhook docs** — "Webhooks Security" is short and specifies exactly
  the scheme implemented here.
- **HMAC** — RFC 2104 for the construction; Wikipedia's "Timing attack" for the
  comparison problem.
- **Pydantic v2** — the "Models" page, and "Fields" for `alias` and
  `default_factory`.
- **FastAPI** — "Dependencies" and "Testing Dependencies with Overrides", which
  is the pattern our integration tests are built on.
- **Idempotency** — Stripe's idempotency-key article again; the webhook section
  matches this slice closely.

---

**Next:** S05 — the outbound half. Sending replies through the same adapter
boundary, conversation state, `httpx` with timeouts and retries, and structured
logging that never records a message body or a full phone number.
