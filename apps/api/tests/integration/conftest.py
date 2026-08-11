"""Fixtures for tests that need a real PostgreSQL.

Integration tests run against the Postgres from `make dev`, in a **separate
database** so they never touch development data. The database is created on
demand and the schema is torn down between tests.

If Postgres is unreachable, these tests skip with a loud reason rather than
failing — but CI always provides one, so they always run there.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import httpx
import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hotelagent.config import get_settings
from hotelagent.db.session import get_session

REPO_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPO_ROOT / "apps" / "api" / "alembic.ini"


def _dsn_parts(url: str) -> tuple[str, str]:
    """Split a SQLAlchemy URL into an asyncpg DSN and the database name."""
    plain = url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(plain)
    database = parsed.path.lstrip("/")
    maintenance = plain.replace(f"/{database}", "/postgres")
    return maintenance, database


async def _ensure_database(url: str) -> None:
    maintenance, database = _dsn_parts(url)
    conn = await asyncpg.connect(maintenance)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", database)
        if not exists:
            # CREATE DATABASE cannot run inside a transaction block.
            await conn.execute(f'CREATE DATABASE "{database}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = get_settings().test_database_url
    try:
        asyncio.run(_ensure_database(url))
    except (OSError, asyncpg.PostgresError) as exc:
        pytest.skip(f"PostgreSQL unreachable at {urlparse(url).hostname}: {exc}. Run `make dev`.")
    return url


@pytest.fixture
def migrated(alembic_config: Config) -> Config:
    """Schema at head.

    Deliberately a **synchronous** fixture. Alembic calls `asyncio.run()`
    inside `env.py`, and an async fixture already runs inside an event loop —
    nesting them raises "asyncio.run() cannot be called from a running event
    loop". Keeping the migration in sync-land avoids the whole problem.
    """
    from alembic import command

    command.upgrade(alembic_config, "head")
    return alembic_config


@pytest.fixture
async def session(migrated: Config, test_database_url: str) -> AsyncIterator[AsyncSession]:
    """A session against a freshly migrated test database.

    Transitively depends on `alembic_config`, so the schema is torn down after
    each test and no test can see another's rows.
    """
    engine = create_async_engine(test_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Let a test change configuration.

    `get_settings` is `lru_cache`d, so the cache must be cleared after the
    environment changes — and again afterwards, or the override leaks into
    every later test in the session.
    """
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


@pytest.fixture
async def seeded_city(session: AsyncSession) -> uuid.UUID:
    """The one city M1 runs. The gateway resolves `city_id` from its slug."""
    from hotelagent.modules.inventory.models import City

    city = City(name="Kanyakumari", slug=get_settings().default_city_slug)
    session.add(city)
    await session.flush()
    return city.id


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    """An HTTP client whose requests share the test's session and transaction.

    Overriding the dependency is why this works: the handler gets the test's
    session, so nothing is committed and the schema teardown still cleans up.
    """
    from hotelagent.main import app

    async def _use_test_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = _use_test_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    app.dependency_overrides.clear()


@pytest.fixture
def alembic_config(test_database_url: str) -> Iterator[Config]:
    """An Alembic config pointed at the test database.

    Yields with the schema at `base`, and tears down afterwards so one test's
    tables never leak into the next.
    """
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(REPO_ROOT / "apps" / "api" / "alembic"))
    config.set_main_option("sqlalchemy.url", test_database_url)

    from alembic import command

    command.downgrade(config, "base")
    yield config
    command.downgrade(config, "base")
