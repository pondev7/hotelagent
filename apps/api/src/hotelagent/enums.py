"""Vocabulary shared across module boundaries.

The module boundary rule forbids one module importing another's **models**. It
does not forbid sharing a vocabulary, and duplicating these would be worse: two
definitions of "manual tier" that can drift apart is exactly the kind of bug
that surfaces as a mismatched string in production.

Only enums genuinely used by more than one module belong here. Module-specific
vocabulary (booking status, call-task status) stays in its own module.
"""

import enum


class IntegrationTier(enum.StrEnum):
    """How we learn whether a room is free (`docs/vision.md` §2.4).

    Used by `inventory` as a property of a hotel, and by `availability` as the
    source of an observation — which is why it lives here rather than in either.

    Every hotel launches at MANUAL. Commission is the incentive to climb, and
    our cost falls exactly where our margin improves.
    """

    LIVE = "live"  # Tier A — calendar in our dashboard or a PMS. Instant, 11%.
    BOT = "bot"  # Tier B — hotelier WhatsApp bot. 1-3 min, 13%.
    MANUAL = "manual"  # Tier C — an operator telephones reception. 5-15 min, 15%.


class Channel(enum.StrEnum):
    """Where a conversation happens.

    Invariant #2: the internal message schema is channel-agnostic. WhatsApp is
    the only channel today, and this enum existing at all is what makes adding
    Instagram or SMS a new adapter rather than a rewrite.
    """

    WHATSAPP = "whatsapp"
    SMS = "sms"
    INSTAGRAM = "instagram"
    WEB = "web"
    CONSOLE = "console"  # the development adapter


class MessageType(enum.StrEnum):
    """The kind of a message, in our vocabulary rather than any provider's.

    Shared because `channel` produces it while normalising an inbound payload
    and `conversation` stores it — the two ends of invariant #2's boundary.
    """

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"
    LOCATION = "location"
    INTERACTIVE = "interactive"  # buttons and list replies
    TEMPLATE = "template"
    SYSTEM = "system"
    UNSUPPORTED = "unsupported"  # a type we do not handle yet, recorded not dropped


class SenderKind(enum.StrEnum):
    """Who composed a message.

    Shared because `channel` names it when sending and `conversation` stores
    it. Internal only — the traveller sees one constant persona whichever this
    says (`docs/vision.md` §4.1). It exists because the share of messages sent
    by AGENT rather than OPERATOR is the containment metric the entire
    automation ladder is measured by.
    """

    CUSTOMER = "customer"
    OPERATOR = "operator"
    AGENT = "agent"
    SYSTEM = "system"


class AutomationLevel(enum.StrEnum):
    """The Automation Governor's setting for a conversation (`docs/vision.md` §2.3).

    Stored from M1 even though nothing reads it until M2, because it is a column
    on a table that will already have rows by then. Defaults to L0 — a human
    does everything — which is exactly true today.
    """

    L0 = "l0"  # Manual desk. Human does everything.
    L1 = "l1"  # AI copilot. Agent drafts, human approves and sends.
    L2 = "l2"  # Agent front, human middle.
    L3 = "l3"  # Fully agentic; humans on escalation only.
