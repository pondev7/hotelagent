"""Append-only enforcement for the event log (invariant #6).

`BookingEvent` and `LedgerEntry` are the system's memory. A booking's mutable
`status` column tells you where it is now; the event log tells you how it got
there — which is what you need for audit, dispute resolution, analytics and
replay, and what you cannot reconstruct after the fact.

A convention that says "please do not UPDATE this table" is not a guarantee.
This module makes it one, at the ORM level, by refusing to flush a modification
or deletion of an append-only row.

This is defence in depth, not the last word: a raw `UPDATE` in psql still gets
through. Database-level enforcement (a rule or a trigger) is the complement,
and belongs with the hardening work in M5.
"""

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session


class AppendOnlyError(RuntimeError):
    """Raised when something tries to modify or delete an append-only row."""


class AppendOnlyMixin:
    """Marks a model as write-once.

    Rows may be inserted and read. Any attempt to update or delete one raises
    `AppendOnlyError` at flush time, before it reaches the database.
    """


@event.listens_for(Session, "before_flush")
def _forbid_mutation(session: Session, flush_context: Any, instances: Any) -> None:
    for obj in session.dirty:
        if isinstance(obj, AppendOnlyMixin) and session.is_modified(obj):
            raise AppendOnlyError(
                f"{type(obj).__name__} is append-only and cannot be updated. "
                "Record a new event describing the change instead."
            )

    for obj in session.deleted:
        if isinstance(obj, AppendOnlyMixin):
            raise AppendOnlyError(
                f"{type(obj).__name__} is append-only and cannot be deleted. "
                "The history is the point; nothing is removed from it."
            )
