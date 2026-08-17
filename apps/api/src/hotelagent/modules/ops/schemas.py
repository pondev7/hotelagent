"""Public data shapes for the ops module."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from hotelagent.enums import CallOutcome
from hotelagent.modules.ops.models import CallTaskStatus

# Re-exported for the same reason as `conversation.schemas`: `CallTaskStatus` is
# the vocabulary of the queue, it lives beside the table whose column constrains
# it, and `models.py` is off-limits to every other file including our router.
__all__ = ["CallTaskStatus", "CallTaskSummary"]


class CallTaskSummary(BaseModel):
    """A unit of work for an operator: which hotel to ring, and what to ask.

    The question is carried as fields rather than prose so the console can
    render a script. Optimising for operator seconds is not polish — at Tier C
    that number *is* our gross margin (`docs/vision.md` §3.5).
    """

    model_config = ConfigDict(frozen=True)

    call_task_id: uuid.UUID
    city_id: uuid.UUID
    hotel_id: uuid.UUID
    hotel_name: str | None = None
    reception_phone: str | None = None
    conversation_id: uuid.UUID | None = None
    room_type_id: uuid.UUID | None = None

    check_in: date
    check_out: date
    guests: int
    status: CallTaskStatus
    outcome: CallOutcome | None = None
    quoted_price: Decimal | None = None
    rooms_available: int | None = None

    assigned_to: str | None = None
    opened_at: datetime | None = None
    claimed_at: datetime | None = None
    resolved_at: datetime | None = None
