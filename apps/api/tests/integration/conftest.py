"""Fixtures for tests that need a real PostgreSQL.

Integration tests run against the Postgres from `make dev`, in a **separate
database** so they never touch development data. The database is created on
demand and the schema is torn down between tests.

If Postgres is unreachable, these tests skip with a loud reason rather than
failing — but CI always provides one, so they always run there.
"""

import asyncio
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import pytest
from alembic.config import Config

from hotelagent.config import get_settings

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
