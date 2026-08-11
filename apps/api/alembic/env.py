"""Alembic environment, wired for async SQLAlchemy.

Alembic's own API is synchronous, so with an async driver the pattern is:
open an async connection, then hand it to `connection.run_sync()`, which runs
Alembic's sync migration machinery on that connection.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from hotelagent.config import get_settings
from hotelagent.db.base import Base

# Importing the models is what populates Base.metadata. Autogenerate compares
# that metadata against the live database — so a model that is not imported
# here is invisible, and Alembic will happily generate a migration dropping the
# table it cannot see. Every new module's models are added to this list.
from hotelagent.modules.inventory import models as inventory_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Tests set sqlalchemy.url in-process; everything else uses Settings."""
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Detect column type changes as well as added/removed columns.
        compare_type=True,
        # Detect changes to server-side defaults.
        compare_server_default=True,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting — useful for review or for a DBA."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    engine = async_engine_from_config(section, prefix="sqlalchemy.")

    async with engine.connect() as connection:
        await connection.run_sync(_run)

    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
