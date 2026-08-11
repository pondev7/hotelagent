"""The internal message schema (invariant #2).

**Read this file looking for WhatsApp. There isn't any.**

That is the entire point. The provider's payload — its envelope shape, its field
names, its id formats, its notion of "entry" and "changes" and "value" — is
normalised at the gateway boundary and never travels further. Everything
downstream sees these types.

The payoff arrives later: adding Instagram, SMS or web chat becomes a new
adapter producing `InboundMessage`, rather than a rewrite of everything that
touches a message. Retrofitting this boundary after three modules have learned
to speak WhatsApp is the rewrite invariant #2 exists to prevent.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from hotelagent.enums import Channel, MessageType


class InboundAttachment(BaseModel):
    """Media or structured content accompanying a message.

    Deliberately a *reference*, not the bytes. Downloading media requires an
    authenticated call to the provider and belongs to a later slice; recording
    that it exists does not.
    """

    model_config = ConfigDict(frozen=True)

    kind: MessageType
    external_media_id: str | None = None
    mime_type: str | None = None
    caption: str | None = None
    # For location messages, and for interactive replies (button id / title).
    data: dict[str, object] = Field(default_factory=dict)


class InboundMessage(BaseModel):
    """One message arriving from any channel.

    Immutable: a normalised inbound message is a record of something that
    already happened, so nothing downstream should be editing it.
    """

    model_config = ConfigDict(frozen=True)

    channel: Channel
    # The provider's message id. Carried because it is the natural idempotency
    # key for redelivery (invariant #5) — not because anything interprets it.
    external_message_id: str
    # The sender's channel-level identity. Never logged in full.
    external_user_id: str
    # The business account the message was addressed to. Becomes the routing
    # key when one deployment serves several cities or brands.
    external_account_id: str | None = None

    profile_name: str | None = None
    message_type: MessageType = MessageType.TEXT
    text: str | None = None
    attachments: list[InboundAttachment] = Field(default_factory=list)
    sent_at: datetime

    # Set when the traveller replies to an earlier message.
    replies_to_external_id: str | None = None


class InboundBatch(BaseModel):
    """A single webhook delivery, which may carry several messages.

    Providers batch. Handling one message per request would work today and
    silently drop messages the first time two arrive together.
    """

    model_config = ConfigDict(frozen=True)

    messages: list[InboundMessage] = Field(default_factory=list)
    # Delivery/read receipts arrive on the same webhook. Parsed and carried so
    # the shape is right; consumed in S05 with the outbound path.
    statuses: list[dict[str, object]] = Field(default_factory=list)
