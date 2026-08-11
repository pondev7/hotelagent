"""The specification for S02, expressed as tests.

Two things must hold, and the second is the one people skip:

1. The migration applies. Obvious, and tested everywhere.
2. The migration **reverses**. `CLAUDE.md` requires every migration to have a
   working `downgrade()`. An untested `downgrade()` is a guess, and you discover
   it is wrong at the worst possible moment — mid-incident, on production.

These functions are deliberately synchronous. Alembic drives its own event loop
inside `env.py`, so calling it from an async test would nest event loops.
"""

import asyncio

import asyncpg
from alembic import command
from alembic.config import Config

from hotelagent.db.mixins import uuid7


async def _inspect(url: str, query: str, *args: object) -> list[asyncpg.Record]:
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        return await conn.fetch(query, *args)
    finally:
        await conn.close()


def _table_names(url: str) -> set[str]:
    rows = asyncio.run(_inspect(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
    return {r["tablename"] for r in rows}


def _enum_type_names(url: str) -> set[str]:
    rows = asyncio.run(_inspect(url, "SELECT typname FROM pg_type WHERE typtype = 'e'"))
    return {r["typname"] for r in rows}


def _columns(url: str, table: str) -> dict[str, str]:
    rows = asyncio.run(
        _inspect(
            url,
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = $1",
            table,
        )
    )
    return {r["column_name"]: r["data_type"] for r in rows}


def test_upgrade_creates_the_expected_tables(
    alembic_config: Config, test_database_url: str
) -> None:
    command.upgrade(alembic_config, "head")

    tables = _table_names(test_database_url)
    assert "city" in tables
    assert "hotel" in tables


def test_downgrade_reverses_the_migration(alembic_config: Config, test_database_url: str) -> None:
    command.upgrade(alembic_config, "head")
    assert {"city", "hotel"} <= _table_names(test_database_url)

    command.downgrade(alembic_config, "base")

    remaining = _table_names(test_database_url)
    assert "city" not in remaining
    assert "hotel" not in remaining


TENANT_SCOPED_TABLES = [
    "hotel",
    "room_type",
    "conversation",
    "message",
    "call_task",
    "availability_observation",
    "booking",
    "booking_event",
    "ledger_entry",
]

ALL_TABLES = {*TENANT_SCOPED_TABLES, "city", "app_user", "idempotency_key"}


def test_every_tenant_scoped_table_carries_city_id(
    alembic_config: Config, test_database_url: str
) -> None:
    """Invariant #1. With one city this looks silly; adding it to a live
    database with a year of bookings is a weekend of downtime.

    `city` is the tenancy root and `app_user` is deliberately global — a
    traveller may book in more than one city, and scoping them would fragment
    exactly the history that makes repeat bookings valuable.
    """
    command.upgrade(alembic_config, "head")

    for table in TENANT_SCOPED_TABLES:
        assert "city_id" in _columns(test_database_url, table), f"{table} is missing city_id"

    assert "city_id" not in _columns(test_database_url, "app_user")


def test_the_full_entity_set_exists(alembic_config: Config, test_database_url: str) -> None:
    command.upgrade(alembic_config, "head")

    assert _table_names(test_database_url) >= ALL_TABLES


def test_re_upgrading_after_a_downgrade_succeeds(
    alembic_config: Config, test_database_url: str
) -> None:
    """The test that catches the enum trap.

    `DROP TABLE` leaves PostgreSQL enum types behind. A downgrade that forgets
    to drop them appears to succeed, and the failure only surfaces here — on
    the next upgrade, with "type already exists".
    """
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")

    assert _table_names(test_database_url) >= ALL_TABLES


def test_downgrade_removes_every_enum_type(alembic_config: Config, test_database_url: str) -> None:
    command.upgrade(alembic_config, "head")
    assert _enum_type_names(test_database_url), "expected enum types after upgrade"

    command.downgrade(alembic_config, "base")

    assert _enum_type_names(test_database_url) == set()


def test_money_is_numeric_and_timestamps_are_timezone_aware(
    alembic_config: Config, test_database_url: str
) -> None:
    """Money is never a float, and timestamps are always timestamptz."""
    command.upgrade(alembic_config, "head")

    hotel = _columns(test_database_url, "hotel")
    assert hotel["commission_rate"] == "numeric"
    assert hotel["created_at"] == "timestamp with time zone"
    assert hotel["updated_at"] == "timestamp with time zone"


def test_uuid7_values_are_time_sortable() -> None:
    """UUIDv7 embeds a millisecond timestamp in its leading bits, so lexical
    order matches creation order — which keeps b-tree index writes local
    instead of scattering them, the way UUIDv4 does."""
    ids = [uuid7() for _ in range(50)]

    assert ids == sorted(ids, key=str)
    assert all(u.version == 7 for u in ids)
    assert len(set(ids)) == 50
