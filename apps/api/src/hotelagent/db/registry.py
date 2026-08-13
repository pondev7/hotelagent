"""Imports every model module, so `Base.metadata` is complete.

**Why this file exists.** SQLAlchemy resolves a `ForeignKey("conversation.id")`
by looking up `conversation` in `Base.metadata` — which only contains tables
whose model module has actually been imported. Miss one and the failure is a
`NoReferencedTableError` at *flush* time, from whichever unrelated table
happened to point at it.

That makes the bug depend on import order, so it hides: the API works because
`main.py` transitively imports most things, the tests work because test modules
import what they assert on, and then a worker process or a one-off script
imports less and breaks. This was found exactly that way — a script exercising
the availability router failed on `call_task.conversation_id` because nothing in
its import graph had mentioned `conversation`.

Any entry point that touches the database imports this module. There are three
that matter: the API (`main.py`), Alembic (`alembic/env.py`), and the arq
worker when it arrives.
"""

from hotelagent.db import idempotency as _idempotency
from hotelagent.db.base import Base
from hotelagent.modules.availability import models as _availability
from hotelagent.modules.booking import models as _booking
from hotelagent.modules.conversation import models as _conversation
from hotelagent.modules.inventory import models as _inventory
from hotelagent.modules.ops import models as _ops
from hotelagent.modules.payments import models as _payments

# Referenced so linters keep the imports, which are the entire point of the file.
_MODEL_MODULES = (
    _idempotency,
    _availability,
    _booking,
    _conversation,
    _inventory,
    _ops,
    _payments,
)

__all__ = ["Base"]
