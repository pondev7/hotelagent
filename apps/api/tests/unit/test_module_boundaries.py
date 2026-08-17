"""The architecture rules, enforced.

`CLAUDE.md` states these as rules and calls a violation "an automatic PR
rejection". Until now nothing rejected anything — and the rule was broken twice
in five slices, both times by the author, both times caught by chance rather
than by process.

A rule that depends on someone noticing is not a rule. These tests read the
source with `ast` and fail on a violation, which is the same reasoning that
made S01's CI worth building: the check that matters is the one that runs
whether or not you remember it.

Why `ast` rather than ruff: ruff's `banned-api` is global, and these rules are
*contextual*. `conversation` may import its own models; `channel` may not. No
global ban expresses "except from inside itself", so the check lives here.
"""

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "hotelagent"

# Cross-module traffic may only touch these. `service` is the public surface;
# `schemas` carries the Pydantic types that cross the boundary.
PUBLIC_SURFACE = frozenset({"service", "schemas"})

# Client libraries for external services. Invariant #9: no provider SDK is
# imported at a call site — only inside adapters/.
PROVIDER_SDKS = frozenset({"httpx", "anthropic", "razorpay", "boto3", "openai"})

# One deliberate exemption, and it should stay one. `db/registry.py` exists
# precisely to import every model module so `Base.metadata` is complete before
# anything resolves a foreign key. It imports models and does nothing else with
# them — no queries, no logic. Anything else appearing here is a smell.
IMPORTS_ALL_MODELS_BY_DESIGN = frozenset({"db/registry.py"})


def _imports(path: pathlib.Path) -> list[str]:
    """Every module path imported by a file, from both import forms."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append(node.module)
    return found


def _owning_module(path: pathlib.Path) -> str | None:
    """Which business module a file belongs to, if any."""
    parts = path.relative_to(SRC).parts
    if len(parts) > 2 and parts[0] == "modules":
        return parts[1]
    return None


def _python_files() -> list[pathlib.Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


def test_no_module_imports_another_modules_models() -> None:
    """The single most important rule in the codebase.

    `CLAUDE.md`: *"No module ever imports another module's SQLAlchemy models.
    A cross-module import of `models` is an automatic PR rejection."*

    It is the entire difference between "we can extract payments in a week" and
    "we can never extract anything."
    """
    violations: list[str] = []

    for path in _python_files():
        if path.relative_to(SRC).as_posix() in IMPORTS_ALL_MODELS_BY_DESIGN:
            continue
        owner = _owning_module(path)
        for imported in _imports(path):
            bits = imported.split(".")
            is_model_import = (
                len(bits) >= 4 and bits[:2] == ["hotelagent", "modules"] and bits[3] == "models"
            )
            if is_model_import and bits[2] != owner:
                violations.append(f"{path.relative_to(SRC)} imports {imported}")

    assert not violations, "cross-module model imports:\n  " + "\n  ".join(violations)


def test_the_model_registry_lists_every_module_with_models() -> None:
    """A model missing from the registry is invisible to SQLAlchemy's metadata.

    The symptom is a `NoReferencedTableError` at flush time, raised from some
    *other* table's foreign key, in whichever entry point happened to import
    less than the tests do. It hides behind import order, so it is worth a test
    rather than a convention.
    """
    registry = SRC / "db" / "registry.py"

    # `from hotelagent.modules.ops import models` puts the package in
    # `node.module` and "models" in the alias, so the two must be recombined —
    # `_imports` alone would report the package and miss the distinction.
    tree = ast.parse(registry.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    expected = {
        f"hotelagent.modules.{path.parent.name}.models" for path in SRC.glob("modules/*/models.py")
    }
    missing = expected - imported

    assert not missing, "model modules absent from db/registry.py:\n  " + "\n  ".join(
        sorted(missing)
    )


def test_cross_module_imports_only_touch_the_public_surface() -> None:
    """Modules talk through `service.py` and `schemas.py`, and nothing else.

    Reaching into another module's `router`, `models` or private helpers makes
    the boundary decorative — the coupling is the same as a shared table, just
    less visible.
    """
    violations: list[str] = []

    for path in _python_files():
        owner = _owning_module(path)
        if owner is None:
            continue
        for imported in _imports(path):
            bits = imported.split(".")
            if len(bits) < 3 or bits[:2] != ["hotelagent", "modules"]:
                continue
            target = bits[2]
            if target == owner:
                continue  # a module may use its own internals freely
            member = bits[3] if len(bits) > 3 else None
            if member is not None and member not in PUBLIC_SURFACE:
                violations.append(f"{path.relative_to(SRC)} imports {imported}")

    assert not violations, "imports bypassing the public surface:\n  " + "\n  ".join(violations)


def test_provider_sdks_are_only_imported_inside_adapters() -> None:
    """Invariant #9.

    This is what makes the hosting ladder in `docs/milestones.md` §5 a config
    change rather than a migration project, and what let S04 ship a complete
    inbound path while the BSP-versus-Cloud-API decision was still open.
    """
    violations: list[str] = []

    for path in _python_files():
        if path.relative_to(SRC).parts[0] == "adapters":
            continue
        for imported in _imports(path):
            root = imported.split(".")[0]
            if root in PROVIDER_SDKS:
                violations.append(f"{path.relative_to(SRC)} imports {root}")

    assert not violations, "provider SDKs outside adapters/:\n  " + "\n  ".join(violations)


def test_routers_do_not_import_models() -> None:
    """`CLAUDE.md`: *"Routers are thin: parse, call `service.py`, serialise. No
    business logic and no ORM queries in a router."*

    Importing a model is the cheapest reliable proxy for "this router is about
    to run a query".
    """
    violations: list[str] = []

    for path in _python_files():
        if path.name != "router.py":
            continue
        for imported in _imports(path):
            if imported.endswith(".models") or ".models." in imported:
                violations.append(f"{path.relative_to(SRC)} imports {imported}")

    assert not violations, "routers importing models:\n  " + "\n  ".join(violations)


def test_routers_do_not_run_orm_queries() -> None:
    """The other half of "routers are thin".

    Not importing models is a proxy; this is the thing itself. A router may
    accept a session and hand it to `service.py` — that is how the request's
    transaction reaches the service layer — but the moment it calls
    `session.scalar(...)` there is business logic living in the transport layer,
    invisible to every caller that is not an HTTP request.

    Matched on the verb rather than the import so that
    `select` reaching a router through any spelling still fails.
    """
    query_verbs = frozenset(
        {"execute", "scalar", "scalars", "add", "add_all", "flush", "commit", "merge", "refresh"}
    )
    violations: list[str] = []

    for path in _python_files():
        if path.name != "router.py":
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in query_verbs:
                continue
            target = node.func.value
            # `session.scalar(...)` and `self.session.scalar(...)` both count;
            # `router.add_api_route(...)` and friends do not.
            name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
            if "session" in name or name == "db":
                violations.append(
                    f"{path.relative_to(SRC)}:{node.lineno} calls {name}.{node.func.attr}()"
                )

    assert not violations, "ORM queries inside routers:\n  " + "\n  ".join(violations)


def test_http_exception_appears_only_in_routers() -> None:
    """`CLAUDE.md`: *"Never raise `HTTPException` below `router.py`."*

    A service that raises `HTTPException` has decided it is only ever called
    from a web request. The same function then cannot be used from the arq
    worker or a management command without a caller catching a web framework's
    exception and reading a status code off it to find out what went wrong.

    Services raise `HotelAgentError` subclasses instead; `errors.py` owns the
    single translation to transport.

    Read with `ast` rather than by string search, because the first draft of
    this test failed on `channel/service.py` — where the only occurrence of the
    word is a docstring explaining that services must not raise it. A checker
    that cannot tell code from prose teaches people to stop writing the prose.
    """
    violations: list[str] = []

    for path in _python_files():
        if path.name == "router.py":
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            named = (
                isinstance(node, ast.Name)
                and node.id == "HTTPException"
                or isinstance(node, ast.Attribute)
                and node.attr == "HTTPException"
                or isinstance(node, ast.alias)
                and node.name == "HTTPException"
            )
            if named:
                violations.append(f"{path.relative_to(SRC)}:{getattr(node, 'lineno', '?')}")

    assert not violations, "HTTPException below the router layer:\n  " + "\n  ".join(violations)


def test_only_config_reads_the_environment() -> None:
    """Invariant #9, the other half: *"Nothing reads `os.environ` directly."*

    One `Settings` object, read through `get_settings()`, is what keeps
    configuration discoverable and `.env.example` honest.
    """
    violations: list[str] = []

    for path in _python_files():
        if path.name == "config.py":
            continue
        source = path.read_text()
        if "os.environ" in source or "os.getenv" in source:
            violations.append(str(path.relative_to(SRC)))

    assert not violations, "files reading the environment directly:\n  " + "\n  ".join(violations)
