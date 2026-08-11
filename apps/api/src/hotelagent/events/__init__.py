"""Append-only event log and its enforcement (invariant #6)."""

from hotelagent.events.append_only import AppendOnlyError, AppendOnlyMixin

__all__ = ["AppendOnlyError", "AppendOnlyMixin"]
