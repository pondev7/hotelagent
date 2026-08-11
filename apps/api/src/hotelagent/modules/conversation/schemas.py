"""Public data shapes for the conversation module.

These cross module boundaries. ORM instances never do — an ORM object carries a
session, lazy-loading behaviour and a mutation surface, and handing one to
another module makes the boundary decorative.
"""

import uuid

from pydantic import BaseModel, ConfigDict


class RecordedMessage(BaseModel):
    """The outcome of recording one inbound message."""

    model_config = ConfigDict(frozen=True)

    message_id: uuid.UUID
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    is_duplicate: bool
    """True when this provider message id had already been recorded — the
    webhook was redelivered and nothing new was written (invariant #5)."""
