# S00 — Repository skeleton · learning notes

**Slice:** M1 / S00 · **Commit:** `85a70c8` · **Status:** built and verified

---

## What we built

A monorepo skeleton: the directory tree from `docs/milestones.md` §2, a
`Makefile` of every command that may be run, Docker Compose files for local and
production, a Python package containing a FastAPI app with exactly one route,
and a Next.js shell for the ops console.

It has no business logic at all. Nine module folders sit empty, four adapter
folders sit empty. What it does have is a **verified toolchain**: `make test`
and `make lint` pass, and `uv run uvicorn hotelagent.main:app` serves a real
HTTP response.

This file explains every tool that appeared. It is long because S00 touched
seven unfamiliar technologies at once — which is normal for a first slice and
will not happen again.

---

## The concepts

### 1. Monorepo, and why `apps/` and `packages/`

A **monorepo** is one Git repository containing several deployable things. Ours
holds `apps/api` (Python) and `apps/ops` (TypeScript), which in another shop
would be two repositories.

The layout convention is near-universal:

- **`apps/`** — things that *run*. Each has its own entrypoint and Dockerfile.
- **`packages/`** — things that are *imported* by apps. Ours will hold generated
  TypeScript types.
- **`infra/`** — deployment configuration that belongs to no single app.
- **`docs/`** — in the repo, so it is version-controlled alongside the code it
  describes.

`docs/milestones.md` §2 argues the case: one context for cross-cutting changes,
no version skew between frontend and backend, one CI pipeline. The cost is that
you must impose structure yourself, which is what the module boundary rule does.

### 2. Python packaging: modules, packages and the src layout

A **module** is a `.py` file. A **package** is a directory Python treats as a
module container. Historically a package needed an `__init__.py`; since Python
3.3 "namespace packages" work without one, but you should still write it —
explicit packages have predictable import behaviour and tools understand them.

Our package is `hotelagent`, living at `apps/api/src/hotelagent/`. So:

```python
from hotelagent.config import get_settings
#    ^package  ^module     ^name inside it
```

**Why `src/`?** Without it, the package directory sits next to your tests, and
Python's habit of putting the current directory on the import path means
`import hotelagent` can silently pick up the *source folder* rather than the
*installed package*. That hides packaging bugs until deployment, where there is
no source folder. Putting the code one level down inside `src/` makes that
accident impossible: if the import works, it works because the package is
genuinely installed. This is called the **src layout** and it is the current
recommended default.

**How Python finds it.** The interpreter searches `sys.path` in order. Our
package gets on that path two ways, deliberately belt-and-braces:

1. `uv sync` installs the project in **editable mode** — a pointer file in the
   virtualenv referring back to `apps/api/src`, so edits take effect with no
   reinstall.
2. `pyproject.toml` sets `pythonpath = ["apps/api/src"]` for pytest, so tests
   work even in a checkout where the install has not been run.

In Docker we use a third mechanism, the `PYTHONPATH` environment variable, since
the container copies source rather than installing it editable.

### 3. `pyproject.toml`, uv, virtualenvs and lockfiles

**The virtualenv problem.** Installing packages globally means two projects
cannot use different versions of the same library. A **virtual environment** is
a private directory of installed packages. Ours is `.venv/`, gitignored.

**`pyproject.toml`** is the modern, standardised (PEP 621) single place for
project metadata, dependencies and tool configuration. It replaced `setup.py`,
`requirements.txt`, `setup.cfg`, and scattered per-tool config files. Ours
configures the project *and* ruff, mypy and pytest.

**uv** is a fast package manager and installer, written in Rust, that replaces
pip + virtualenv + pip-tools (and largely poetry). What matters for us:

- `uv sync` reads `pyproject.toml`, resolves the full dependency graph, writes
  `uv.lock`, creates `.venv/` if missing, and installs everything **including
  your project in editable mode**.
- `uv run <cmd>` runs a command inside that virtualenv **without activating
  anything**. This is why every Makefile target says `uv run pytest` rather than
  `source .venv/bin/activate && pytest` — there is no shell state to get wrong,
  which matters enormously when an agent is running the commands.

**The lockfile.** `pyproject.toml` says what you *want* (`fastapi>=0.115`).
`uv.lock` records what you *got* (`fastapi==0.128.4`), for every transitive
dependency, with hashes. Commit it. It is the difference between "works on my
machine" and "works identically on the VM in six months". `--frozen` in the
Dockerfile means "install exactly the lockfile, fail if it disagrees".

**Dependency groups.** `[dependency-groups] dev = [...]` holds tools needed to
develop but not to run — pytest, ruff, mypy. The production image installs with
`--no-dev` and stays smaller.

**The build backend.** `[build-system]` names the tool that turns source into an
installable artefact; we use hatchling. Because our layout is unusual (package
nested under `apps/api/src` while `pyproject.toml` is at the root), we tell it
explicitly:

```toml
[tool.hatch.build.targets.wheel]
packages = ["apps/api/src/hotelagent"]
```

### 4. Type hints and mypy

Python is dynamically typed and always will be at runtime. **Type hints** are
annotations that describe intent:

```python
async def health() -> dict[str, str]:
```

Python itself does not check these — they are documentation the interpreter
mostly ignores. **mypy** is a separate program that reads them and proves your
code consistent *before* it runs. We run it in `--strict` mode, which requires
every function to be annotated and rejects implicit `Any`.

Strict from day one is a deliberate choice: adding types to an untyped codebase
is miserable, whereas staying typed costs almost nothing per function. And two
libraries here — Pydantic and SQLAlchemy 2.0 — are *designed* around type hints,
so annotations buy real correctness rather than mere documentation.

### 5. ruff — linter and formatter

A **linter** finds suspicious code (unused imports, shadowed names, mutable
default arguments). A **formatter** rewrites your code into a canonical style so
nobody argues about it and diffs stay small.

Ruff does both, extremely fast. Our configuration selects rule families:

```toml
select = ["E", "F", "I", "N", "UP", "B", "SIM", "TID"]
```

`E`/`F` are the classic pycodestyle/pyflakes checks; `I` sorts imports;
`N` enforces naming conventions; `UP` rewrites old idioms into modern ones;
`B` is bugbear (likely bugs); `SIM` suggests simplifications; `TID` controls
import hygiene.

That last one matters here. `TID` is how the **module boundary rule** stops
being a code-review promise and becomes machine-enforced:
`[tool.ruff.lint.flake8-tidy-imports.banned-api]` is sitting empty in our
`pyproject.toml`, waiting for entries that ban one module from importing
another's internals.

Note the distinction in the Makefile: `make lint` runs `ruff format --check`
(fails if formatting is wrong, changes nothing) while `make fmt` runs
`ruff format` (rewrites files). CI uses the first.

### 6. HTTP, ASGI, uvicorn and FastAPI

These four are commonly confused. From the bottom up:

**HTTP** is the protocol: a client opens a TCP connection and sends a request
(method, path, headers, optional body); the server returns a status code,
headers and a body. `GET /health` with `200 OK` is exactly this.

**A web server** is the process that owns the socket, speaks HTTP, and hands
parsed requests to your code. **uvicorn** is ours.

**ASGI** (Asynchronous Server Gateway Interface) is the *calling convention*
between the server and your application — a specification saying an app is an
async callable receiving a `scope` dict plus `receive`/`send` functions.
Standardising it means any ASGI server can run any ASGI framework.

Its predecessor **WSGI** was synchronous: one thread per request, blocked while
waiting. Since our workload is dominated by *waiting* — on Postgres, on the
WhatsApp API, on a payment gateway — ASGI's ability to handle thousands of
concurrent waits on one thread is the right shape. That is the whole reason for
the async stack.

**FastAPI** is the framework: routing, validation, serialisation, dependency
injection, and automatic OpenAPI documentation. It is built on **Starlette**
(the ASGI toolkit) and **Pydantic** (validation). It is not a server — which is
why the command is `uvicorn hotelagent.main:app` and not `python main.py`.

That argument is `module_path:variable_name`. Uvicorn imports
`hotelagent/main.py` and looks for `app`.

**The free OpenAPI schema.** FastAPI reads your type hints and generates a
machine-readable API description at `/openapi.json`, rendered as interactive
docs at `/docs`. You wrote nothing for this. It is also the input to
`make contracts`, which will generate the ops console's TypeScript types —
so the frontend cannot drift from the backend. That is `docs/milestones.md` §2's
"shared contract for free", already working.

### 7. Pydantic v2 and pydantic-settings

**Pydantic** validates and coerces data using type hints. Declare the shape,
and it parses input, converts types, and raises detailed errors on bad data. v2
moved the core to Rust and is very fast. It is the reason FastAPI can turn a
JSON body into a typed Python object with no manual parsing.

**pydantic-settings** applies the same machinery to *configuration*. Our
`Settings` class declares each key with a type and a default; the library
populates it from environment variables and `.env`, coercing as it goes —
`HOTELAGENT_LOG_JSON=false` becomes a real Python `False`, and a malformed value
fails loudly at startup rather than mysteriously at 2am.

`env_prefix = "HOTELAGENT_"` namespaces our variables so they cannot collide
with anything else on the host.

**`@lru_cache` on `get_settings()`** is a small, standard trick. `lru_cache`
memoises a function by its arguments; with no arguments it means "compute once,
return the same object forever". So the environment is read exactly once per
process, and every caller shares one `Settings` instance — a singleton without
a singleton pattern.

### 8. pytest and testing an ASGI app without a network

**pytest** finds functions named `test_*`, runs them, and reports. Assertions
are plain `assert` statements; pytest rewrites them to produce useful failure
output.

Two settings in our `pyproject.toml` do real work:

- `asyncio_mode = "auto"` — our test is `async def`, and something must drive
  the event loop. Auto mode makes pytest-asyncio handle every async test
  without decorating each one.
- `pythonpath = ["apps/api/src"]` — discussed above.

**The interesting part** is that our test makes an HTTP request without a
server:

```python
transport = httpx.ASGITransport(app=app)
async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
    response = await client.get("/health")
```

`httpx` is an HTTP client. Normally its transport opens a TCP socket.
`ASGITransport` replaces that with a direct in-process call into the ASGI app.
Nothing binds a port, nothing touches the network, and the test runs in
milliseconds — while still exercising real routing, real serialisation and real
status codes. This is the standard way to test ASGI apps, and it is why
`tests/unit` needs no running services.

### 9. Docker: images, containers, layers and volumes

Four ideas, in dependency order:

- An **image** is a read-only filesystem snapshot plus metadata (default
  command, environment, exposed ports). It is a *template*.
- A **container** is a running instance of an image, with a thin writable layer
  on top. Delete it and that writable layer goes with it.
- A **volume** is storage that lives *outside* any container's lifecycle. This
  is how Postgres keeps data across restarts, and why `docker compose down`
  without `-v` is safe.
- A **Dockerfile** is the recipe that builds an image.

**Layer caching** is the thing to internalise, because it dictates how
Dockerfiles are written. Each instruction creates a layer; Docker reuses cached
layers until an input changes, then rebuilds everything after that point. Hence
our ordering:

```dockerfile
COPY pyproject.toml uv.lock* ./     # changes rarely
RUN uv sync --frozen --no-install-project --no-dev
COPY apps/api/src ./apps/api/src    # changes constantly
```

Dependencies install in their own layer, so editing a Python file rebuilds only
the last step. Reverse those two and every edit reinstalls every dependency.

**The build context** is the directory passed to `docker build` — everything in
it is sent to the daemon. Ours is the repo root (not `apps/api/`), because
`pyproject.toml` and `uv.lock` live at the root and both the api and worker
images must share one dependency resolution. That is why the Dockerfile lives at
`apps/api/Dockerfile` but paths inside it are written relative to the root.

**`--from=ghcr.io/astral-sh/uv:0.5`** is a multi-stage copy: it pulls the `uv`
binary out of a published image instead of installing it, which is faster and
pins the version.

### 10. Docker Compose

A Dockerfile builds one image. **Compose** describes a *set* of containers that
run together, in one YAML file, with a private network where **services reach
each other by service name**. That is why our database URL says
`postgresql+asyncpg://...@postgres:5432/...` — `postgres` is a hostname created
by Compose. On your laptop, outside the network, the same database is
`localhost:5432` via the published port.

Concepts in our file:

- **`ports: "8000:8000"`** — `host:container`. Only published ports are
  reachable from your machine.
- **`volumes: ./apps/api/src:/app/apps/api/src`** — a *bind mount*, mapping a
  host directory into the container. This is what makes `--reload` useful: edit
  on your laptop, the container sees it immediately. Production deliberately has
  none.
- **`healthcheck`** — a command Docker runs periodically to decide whether a
  container is not merely *running* but *ready*. `pg_isready` is Postgres's own
  answer to that question.
- **`depends_on: condition: service_healthy`** — start ordering that waits for
  readiness. Without the condition, `depends_on` only waits for the process to
  *start*, and the API cheerfully connects to a Postgres that has not finished
  initialising.
- **Named volumes** (`postgres_data`) — Docker-managed storage that survives
  `docker compose down`.
- **`profiles`** — services that do **not** start by default. We used this for
  `worker` and `langfuse` because neither has work to do yet: there are no arq
  tasks, and no LLM calls to trace until M2. They are declared so the shape is
  visible, and they lose their profiles in the slice that gives each one a job.

### 11. Caddy and reverse proxies

A **reverse proxy** sits in front of your applications, terminates HTTPS, and
routes each request to the right backend. It is how one machine serves both the
API and the console on one domain and one certificate.

**Caddy** was chosen over nginx for one reason: it obtains and renews TLS
certificates from Let's Encrypt automatically, with no cron job and no manual
step. Our `Caddyfile` routes `/api/*` to the api container (stripping the
prefix) and everything else to the ops console. It is unused until S12.

### 12. The JavaScript side: Node, npm, TypeScript, React, Next.js, Tailwind

**Node.js** runs JavaScript outside a browser. **npm** is its package manager;
`package.json` is its `pyproject.toml`, and `package-lock.json` its `uv.lock`.
`dependencies` ship to production, `devDependencies` do not.

**TypeScript** is JavaScript plus a type system. Browsers cannot run it, so it
is compiled (really, type-checked then stripped) to JavaScript. `tsconfig.json`
configures that; `"strict": true` is the equivalent of mypy strict and is on.

**React** is a library for building UIs from **components** — functions that
return markup. That markup is **JSX**, an HTML-like syntax compiled to function
calls. Our `app/page.tsx` is a component:

```tsx
export default function Home() {
  return <main className="p-8">...</main>;
}
```

The core idea: you describe what the UI *should look like* for the current data,
and React works out the minimal DOM changes to get there. You never write
"find this element and update its text". (`className` rather than `class`
because `class` is a reserved word in JavaScript.)

**Next.js** is the React framework — routing, server rendering, bundling and
production builds. We use the **App Router**, where the filesystem *is* the
routing table:

- `app/layout.tsx` — the shell wrapping every page (the `<html>` and `<body>`
  tags live here, exactly once).
- `app/page.tsx` — the page rendered at `/`. A file at `app/hotels/page.tsx`
  would serve `/hotels`, with no route configuration anywhere.

A crucial App Router default: components are **server components** unless marked
otherwise. They render on the server and ship *no JavaScript* to the browser.
Interactivity requires opting in with `"use client"`. This distinction is the
main thing to understand about modern Next.js, and S08 covers it properly.

**Tailwind CSS** styles via utility classes: `className="p-8 font-mono text-sm"`
is padding, font family, font size. It looks like inline styles and is not —
these are real CSS classes, constrained to a design scale, and the build step
emits only the classes you actually used. It scans the files listed in
`content:` in `tailwind.config.ts`; a class in a file not covered by those globs
silently does nothing. **PostCSS** is the CSS build pipeline Tailwind plugs
into, and `autoprefixer` adds vendor prefixes.

**`output: "standalone"`** in `next.config.mjs` makes the production build emit
a self-contained bundle with only the needed `node_modules`, which keeps the
image small — this runs on one cheap VM.

---

## Reading our code

### `config.py` — the only file that reads the environment

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HOTELAGENT_",
        env_file=".env",
        extra="ignore",
    )
    env: Environment = "local"
```

`Environment` is `Literal["local", "staging", "production"]` — a type that
permits exactly three strings, so a typo in `.env` fails at startup, and mypy
rejects a comparison against `"prod"`. `extra="ignore"` means unrelated
environment variables do not crash us.

Everything else calls `get_settings()`. That is invariant #9: one file reads the
environment, and every external dependency arrives through it.

### `main.py` — a wiring file

```python
settings = get_settings()
app = FastAPI(title="HotelAgent API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, ...)

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.env}
```

**Middleware** wraps every request and response. **CORS** — Cross-Origin
Resource Sharing — is a browser rule: JavaScript served from `localhost:3000`
may not call `localhost:8000` unless the API says so. That header is why the ops
console will be able to talk to the API at all.

`@app.get("/health")` is a **decorator**: it registers the function in FastAPI's
routing table. The function returns a plain `dict` and FastAPI serialises it to
JSON and sets the content type.

The docstring says readiness checks arrive with the database session. Right now
this proves only that the process is alive — an honest liveness probe, not a
readiness probe.

### The empty `service.py` files

Nine of them, each containing only a docstring. They exist because of the
strongest rule in `CLAUDE.md`:

> Every module owns a `service.py`. Modules call each other only through those
> public functions. No module ever imports another module's SQLAlchemy models.

Creating them empty makes the boundary visible before there is anything to put
behind it. When `booking` needs something from `inventory`, the only legal
import is `from hotelagent.modules.inventory import service` — never
`models`. That single rule is what keeps "extract payments into its own service"
a week of work rather than impossible.

---

## The gotchas

**Make recipes need a literal TAB.** Spaces give `missing separator`.

**Every make recipe line is its own shell** — a `cd` on one line does not affect
the next.

**`.PHONY` is not optional.** Make thinks targets are files; create a file named
`test` and `make test` silently does nothing while reporting success.

**Docker layer order dictates rebuild time.** Copy dependency manifests before
source, always.

**`depends_on` without `condition: service_healthy` does not wait for
readiness** — only for the process to start. This produces intermittent
connection-refused errors at startup that look like application bugs.

**Compose service names are hostnames.** `postgres:5432` inside the network,
`localhost:5432` from your laptop. Mixing these up is the most common Compose
confusion.

**Tailwind classes in files outside `content:` globs are silently dropped.** No
error, the style just does not apply.

**`ruff format` rewrites; `ruff format --check` does not.** CI must use the
second, or it will "pass" by fixing the problem it was meant to report.

**`uv.lock` belongs in Git.** Not committing it discards the entire benefit.

---

## Check yourself

1. Why does `uvicorn hotelagent.main:app` have a colon in it, and what is on
   each side?
2. What breaks if you swap the two `COPY` instructions in `apps/api/Dockerfile`?
3. The API talks to `postgres:5432`, but a GUI client on your laptop uses
   `localhost:5432`. Why are both correct?
4. `/health` returned `"env":"local"` although no `.env` file exists. Where did
   that value come from?
5. Why does our test hit `/health` without any server running?
6. What would go wrong if the nine `service.py` files did not exist and modules
   imported each other's models directly?
7. Why is `worker` in `docker-compose.yml` at all, given it cannot start?

## Going deeper

- **FastAPI** — the official tutorial is genuinely excellent; read the
  dependency-injection chapter before S04.
- **ASGI** — the spec at `asgi.readthedocs.io` is short and clarifies what a
  framework actually is.
- **uv** — `docs.astral.sh/uv`, particularly the project/lockfile pages.
- **Docker** — the "best practices for writing Dockerfiles" page is the highest
  value-per-page document about layer caching.
- **Next.js App Router** — the "Server and Client Components" page. Read it
  before S08; it is the concept everything else there depends on.
- **Tailwind** — the "Utility-First Fundamentals" page addresses the "isn't this
  just inline styles?" objection head-on.

---

**Next:** S01 — decision records and CI gates.
