# S01 — Decision records and CI gates · learning notes

**Slice:** M1 / S01 · **Commit:** `6355f1f` · **Status:** built and verified

---

## What we built

Four architecture decision records capturing the Week-0 choices — monorepo,
modular monolith, no agent framework, Postgres-only — plus a README documenting
the format, and a GitHub Actions workflow that runs `make lint` and `make test`
on every push to a slice branch and every PR to `main`.

No application code changed. This slice is entirely about making decisions
durable and quality automatic.

**Verified both directions:** the workflow went green on the real commit
(`6355f1f`, 31 seconds), and a deliberately introduced unused import turned it
red (`eca79c7`, conclusion `failure`). A gate you have never seen fail is not a
gate — it is decoration.

---

## The concepts

### 1. What an ADR actually is

An **Architecture Decision Record** is a short document capturing one decision:
the context, the options, the choice, the costs, and the conditions under which
you would revisit it. The idea comes from Michael Nygard (2011) and has become
close to standard practice.

The common misconception is that an ADR is documentation of *what the system
does*. It is not — the code already says that, and says it more accurately. An
ADR documents **why the system is that way**, which the code cannot say.

Three specific things it buys you:

**It stops re-litigation.** This matters unusually much here. Most of this
codebase is written by an agent whose sessions start with no memory of the last
one. Without ADR 0003 on disk, every future session is free to suggest
LangGraph — plausibly, politely, and repeatedly.

**It records the conditions, not just the conclusion.** ADR 0004 says Postgres
is the only datastore *because* the knowledge base has thousands of chunks, not
millions. That is falsifiable. When it stops being true, you have a written
trigger rather than a vague feeling that things have outgrown the design.

**It makes reversal deliberate.** Systems rarely reverse decisions in a meeting;
they drift. A decision with a written trigger drifts visibly.

### 2. Why accepted ADRs are immutable

Our `docs/adr/README.md` states that an accepted ADR is never edited. If the
decision changes, you write a *new* ADR that supersedes it, and update the old
one's Status to point forward.

This feels wrong at first — surely documentation should be kept current? But an
ADR is not a description of the present, it is **a record of a decision made at a
point in time with particular information**. Editing 0002 to say "actually we
use microservices" destroys the useful artefact: the knowledge that we once
chose otherwise, and why. The sequence of superseded ADRs is the reasoning
history of the system, and it is the part you cannot reconstruct later.

The same instinct explains invariant #6, the append-only event log: overwriting
a `status` column loses history in exactly the same way.

### 3. The honest-costs rule

Our README says an ADR listing only benefits means the decision was not
actually made. That is worth taking seriously, and our four follow it:

- 0001 concedes that a monorepo makes boundaries a convention that erodes.
- 0002 concedes that everything scales together and a crash takes the API down.
- 0003 concedes we must write retries, tool dispatch and token accounting
  ourselves.
- 0004 concedes pgvector is slower than a specialised vector database, and that
  one datastore is a single point of failure.

A decision where one option has no downsides was not a decision — it was
recognising the obvious, which needs no record.

### 4. YAML

YAML is a data format designed to be human-readable, used for configuration
almost everywhere (GitHub Actions, Docker Compose, Kubernetes). Three
structures:

```yaml
key: value                 # mapping (dict)
items:                     # sequence (list)
  - first
  - second
nested:
  inner: value             # nesting is by indentation
```

**Indentation is syntax**, like Python. **Tabs are forbidden entirely** — always
spaces. A list of mappings, the most common Actions shape, looks like this:

```yaml
steps:
  - name: Check out the repository
    uses: actions/checkout@v4
```

The `-` starts an item, and everything indented to align with `name` belongs to
the same item.

**The `on:` gotcha.** YAML 1.1 interprets several bare words as booleans:
`yes`, `no`, `on`, `off`, `true`, `false`. So in a GitHub workflow, the key `on:`
parses as the **boolean `True`**, not the string `"on"`. That is why the
validation script in this slice reads:

```python
key = True if True in d else "on"
```

GitHub handles this correctly, so it does not affect us in practice — but it
surprises everyone who first tries to parse a workflow file themselves. The
same family of quirks is why `country: NO` (Norway) famously parses as `False`,
and why you quote strings that could be misread.

### 5. Continuous Integration, and what a "gate" means

**CI** means: on every change, automatically run the checks that decide whether
the change is acceptable. The value is not the automation — you can run
`make lint` yourself. The value is that it is **not optional**. Checks that rely
on memory get skipped on the day you are in a hurry, which is precisely the day
they would have caught something.

A **gate** is a check that can block. Ours currently reports; turning it into a
true gate requires GitHub branch protection, which is a repository *setting*
rather than a file, and therefore deliberately outside this slice.

### 6. GitHub Actions: the object model

Five nouns, top down:

- **Workflow** — one YAML file in `.github/workflows/`. Ours is `ci.yml`.
- **Event / trigger** — what starts it (`push`, `pull_request`, a schedule, a
  manual dispatch).
- **Job** — a unit that runs on one machine. Jobs run in **parallel** by default
  and are isolated from each other. Ours has one job, `api`.
- **Runner** — the machine. `ubuntu-latest` is a fresh GitHub-hosted VM,
  destroyed afterwards. This freshness is the point: it catches "works because
  of something installed on my laptop three months ago".
- **Step** — one thing within a job, either a shell command (`run:`) or a
  reusable action (`uses:`).

**`uses:` versus `run:`** is the distinction worth internalising. `run:` executes
shell. `uses:` pulls in a packaged, versioned action someone else published:

```yaml
- uses: actions/checkout@v4        # official; clones your repo
- uses: astral-sh/setup-uv@v5      # by uv's authors; installs uv
```

The `@v4` is a version pin. Actions are ordinary repositories, so pinning
matters for both stability and supply-chain safety.

Note that **the runner does not have your code by default** — `actions/checkout`
is what puts it there, which is why it is always the first step.

### 7. Caching, concurrency and timeouts

Three production concerns in our workflow, each one line:

**Caching.** A fresh runner would re-download every dependency each run.

```yaml
enable-cache: true
cache-dependency-glob: "uv.lock"
```

The cache key is derived from `uv.lock`, so it is reused while dependencies are
unchanged and invalidated the moment they change. Keying on the *lockfile* — not
on `pyproject.toml`, and not on a date — is what makes the cache both fast and
correct.

**Concurrency.**

```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

`${{ }}` is Actions' expression syntax; `github.ref` is the branch. Together
this means: runs on the same branch form one group, and a new push cancels the
one still running. Pushing three times quickly leaves one run, for the commit
you actually care about.

**Timeout.** `timeout-minutes: 10` kills a hung job. Without it, a job that
hangs can occupy a runner for six hours.

### 8. Why CI runs `make`, not its own commands

Our workflow's two meaningful steps are `make lint` and `make test` — the same
commands you type locally.

The alternative, spelling out `uv run ruff check . && uv run mypy && ...` in the
YAML, creates a second definition of "what correct means". The two drift, and
the failure mode is nasty: CI passes while local fails, or worse, the reverse,
and people learn to ignore CI.

One definition, in the `Makefile`, used everywhere. This is the concrete payoff
of the rule in `CLAUDE.md` that every command lives in the Makefile.

### 9. `--frozen`, and lockfile drift

```yaml
- run: uv sync --frozen
```

`--frozen` means "install exactly `uv.lock`; fail if it disagrees with
`pyproject.toml`". This catches a specific, common mistake: someone adds a
dependency to `pyproject.toml`, it works locally because their environment
already has it, and they never regenerate the lockfile. Without `--frozen`, CI
quietly resolves and passes; production later installs something different.

The same flag appears in `apps/api/Dockerfile`, for the same reason.

---

## Reading our code

### `.github/workflows/ci.yml`

```yaml
on:
  push:
    branches: [main, "m1/**", "m2/**"]
  pull_request:
    branches: [main]
```

Two triggers. Pushes to `main` or any slice branch run CI — this is what let us
verify the workflow without opening a PR, since the `gh` CLI is not installed
here. PRs *targeting* `main` also run. `"m1/**"` is a glob; the quotes are
needed because `*` is special in YAML.

The steps then read as a straight line: check out the code, install uv, install
Python 3.12, install dependencies from the lockfile, lint, test. Each `name:` is
cosmetic but appears in the GitHub UI, and a well-named failing step tells you
what broke without opening logs.

### The ADRs

Each follows Context → Options considered → Decision → Consequences → When to
revisit. Two are worth reading closely for how they argue:

**0001 (monorepo)** turns on **asymmetric reversibility**. Extracting a module
from a monorepo is roughly a week if the boundary rules held; merging four
drifted repositories is never a week. Given genuine uncertainty, choose the
option that stays cheap to undo. That reasoning pattern generalises far beyond
this decision.

**0002 (modular monolith)** separates two things that get conflated: a
*component diagram* and a *deployment diagram*. `docs/vision.md` draws twelve
components. That is a statement about boundaries, not about processes. Twelve
modules in one process preserves every boundary while paying none of the
distributed-systems cost.

---

## The gotchas

**YAML indentation must be spaces.** A tab is a parse error, and editors hide it.

**Bare `on`, `yes`, `no`, `off` are booleans in YAML 1.1.** Quote anything you
mean as a string.

**`actions/checkout` is not automatic.** No checkout step, no source code.

**Unpinned actions are a supply-chain risk.** `@v4` at minimum; a commit SHA for
anything sensitive.

**A cache keyed on the wrong file is worse than no cache** — it serves stale
dependencies while looking like it is working. Key on the lockfile.

**Jobs are isolated.** Files written in one job do not exist in another unless
explicitly passed as artifacts. Steps within a job *do* share a filesystem.

**A CI gate you have never seen fail may not work at all.** Typos in a workflow,
a step that swallows its exit code, a linter finding nothing because it was
pointed at an empty directory — all look identical to "passing". This is exactly
why this slice's exit criterion required a deliberate failure.

**Local and CI must run the same commands**, or you maintain two definitions of
correct and trust neither.

**`ruff format` reformats Python code blocks inside Markdown.** This one was
found the hard way, by this very slice. The first version of *this file* used
single quotes inside a ` ```python ` block; ruff's default quote style is
double, so `ruff format --check .` failed — and CI went red on a commit that
touched nothing but documentation.

Two lessons, and the second is the real one:

1. Prose files are not outside the toolchain. A fenced `python` block is code as
   far as ruff is concerned.
2. **Run the gate after your last edit, not before it.** `make lint` had passed
   — before the Markdown was written. The `CLAUDE.md` "before you finish"
   checklist exists for exactly this, and skipping it because "it's only docs"
   is how it gets skipped every time.

It is a fitting failure for the slice that built the gate: the gate caught a
mistake its own author made, in the file describing the gate.

---

## Check yourself

1. Why is an accepted ADR never edited, even when the decision changes?
2. What does the *When to revisit* section give you that the Decision section
   does not?
3. In a workflow file, why does `on:` parse as `True` in most YAML libraries?
4. What breaks if you remove the `actions/checkout` step?
5. Why is the dependency cache keyed on `uv.lock` rather than `pyproject.toml`?
6. What specific mistake does `uv sync --frozen` catch that plain `uv sync`
   would not?
7. Why does CI run `make lint` instead of listing ruff and mypy directly?
8. We proved CI green *and* proved it red. Why was the second one necessary?

## Going deeper

- **ADRs** — Michael Nygard's original post, "Documenting Architecture
  Decisions"; and `adr.github.io` for format variants (MADR is the common one).
- **GitHub Actions** — the "Workflow syntax" reference; skim it once so you know
  what exists, then use it as a lookup.
- **YAML** — "YAML Ain't Markup Language" spec §10 on type resolution, if you
  want to understand the boolean quirk properly. `noyaml.com` is a more
  entertaining tour of the same traps.
- **CI philosophy** — Martin Fowler's "Continuous Integration" article; the
  parts about build self-testing are the ones that still matter.

---

**Next:** S02 — database foundations and the first migration. This is the first
slice that needs the running Postgres from `make dev`, and the first with an
integration test.
