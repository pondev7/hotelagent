"""Engine, session factory and the FastAPI dependency.

One engine per process. The engine owns a **connection pool** — opening a
PostgreSQL connection costs milliseconds and a backend process, so connections
are borrowed and returned rather than created per request.

A `Session` is not a connection. It is a unit of work: it tracks the objects
you have loaded or changed, and flushes them in one transaction at commit.
Sessions are cheap, short-lived and emphatically not shared between requests.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from hotelagent.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.database_echo,
        # Verify a pooled connection is still alive before handing it out.
        # Without this, a connection dropped by a restart or an idle timeout is
        # discovered by the request unlucky enough to receive it.
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        # Attributes stay loaded after commit. Without this, touching any
        # attribute of a committed object triggers a fresh SELECT — which, in
        # async code, raises rather than lazily loading.
        expire_on_commit=False,
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session per request.

    The session commits if the handler returns normally and rolls back if it
    raises, so a half-applied write cannot escape a failed request.
    """
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
