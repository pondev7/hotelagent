"""Structured logging.

`CLAUDE.md`: *"Log the `conversation_id`, `booking_id` and `city_id` on
anything customer-facing. Never log message bodies, phone numbers in full, or
payment identifiers."*

**Why the prohibition is absolute.** Logs go places the database does not:
aggregators, error trackers, a terminal in a shared office, a screenshot in a
support thread. They are retained on a different schedule and read by people
with different access. A message body in a log is a traveller's private
conversation sitting somewhere nobody audited, and under India's DPDP Act it is
personal data we have no basis to keep there.

The rule is easier to hold than to reason about case by case: **structured
fields only, and never the content**. Log that a message was sent, its id, its
type and its length — never what it said.
"""

import logging
import sys
from typing import Any

import structlog

_PHONE_KEEP = 4


def redact_identifier(value: str | None) -> str | None:
    """Reduce a phone number or channel id to something safe to log.

    Keeps the last four digits, which is enough for an operator to correlate a
    log line with a conversation they are looking at, and not enough to
    identify or contact anyone.
    """
    if not value:
        return value
    if len(value) <= _PHONE_KEEP:
        return "*" * len(value)
    return "*" * (len(value) - _PHONE_KEEP) + value[-_PHONE_KEEP:]


def body_shape(text: str | None) -> dict[str, Any]:
    """Describe a message body without recording it.

    Length and emptiness are useful when debugging truncation or empty sends.
    The text itself never is — if you need it, read the database, where access
    is controlled and retention is defined.
    """
    return {"body_length": len(text) if text else 0, "body_empty": not text}


def configure_logging(*, json_output: bool) -> None:
    """Configure structlog once, at startup.

    JSON in production because a log aggregator parses it; a human-readable
    renderer locally because you are reading it with your eyes.
    """
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[*shared, structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)
