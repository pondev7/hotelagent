"""Shared column mixins: identity, timestamps and the tenancy key.

Every table in HotelAgent inherits its identity and timestamp columns from
here, and every tenant-scoped table also inherits `city_id` (invariant #1).
"""

import secrets
import threading
import time
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

# --- UUIDv7 ----------------------------------------------------------------
#
# RFC 9562 layout, most significant bit first:
#
#   48 bits  unix timestamp in milliseconds
#    4 bits  version (0b0111 = 7)
#   12 bits  counter — monotonic within a millisecond
#    2 bits  variant (0b10)
#   62 bits  random
#
# Why not UUIDv4: v4 is uniformly random, so consecutive inserts land in
# scattered pages of the primary key's b-tree, dirtying many pages per commit.
# v7 sorts by creation time, so inserts append to the right-hand edge of the
# index — the same locality an auto-increment integer gives you.
#
# Why not auto-increment: sequential integers leak business volume (a customer
# receiving booking #41 knows you have taken forty bookings), require a
# database round-trip to learn the id, and collide when merging datasets.
# UUIDv7 is safe to expose and can be generated before touching the database.
#
# The counter matters: without it, two ids generated in the same millisecond
# order randomly relative to each other. Python 3.14 gains `uuid.uuid7()` in
# the standard library; until then this is ours.

_lock = threading.Lock()
_last_ms = 0
_counter = 0
_MAX_COUNTER = 0xFFF


def uuid7() -> uuid.UUID:
    """A time-sortable UUID, monotonic even within a single millisecond."""
    global _last_ms, _counter

    with _lock:
        now_ms = int(time.time() * 1000)
        if now_ms > _last_ms:
            _last_ms = now_ms
            _counter = 0
        else:
            # Same millisecond, or a clock that moved backwards. Never emit a
            # timestamp earlier than the last one we used.
            _counter += 1
            if _counter > _MAX_COUNTER:
                _last_ms += 1
                _counter = 0
        ts_ms, counter = _last_ms, _counter

    value = (ts_ms & 0xFFFFFFFFFFFF) << 80
    value |= 0x7 << 76
    value |= counter << 64
    value |= 0b10 << 62
    value |= secrets.randbits(62)
    return uuid.UUID(int=value)


class IdMixin:
    """A UUIDv7 primary key, generated in Python rather than by the database."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)


class TimestampMixin:
    """Creation and update times, always `timestamptz`, always UTC.

    `server_default`/`onupdate` use the database clock, so rows written by a
    migration or by psql get correct timestamps too — not only rows written
    through the ORM.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CityScopedMixin:
    """Invariant #1 — the tenancy key, on every relevant row from the first
    migration.

    With one city this looks like pure overhead. Adding a tenancy key to a live
    database with a year of bookings is a weekend of downtime, so it goes in
    now, indexed, while it costs nothing.

    `declared_attr` is required because a ForeignKey object cannot be shared
    between mapped classes — each subclass needs its own instance, so the
    column is produced by a function rather than assigned once.
    """

    @declared_attr
    @classmethod
    def city_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            ForeignKey("city.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )
