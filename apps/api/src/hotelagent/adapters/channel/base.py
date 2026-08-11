"""The contract every channel adapter satisfies.

One interface, several implementations — the same shape as the availability
router arriving in S06. The service depends on this protocol, never on
`cloud_api` or `console` directly, which is what makes adding Instagram or SMS
a new file rather than a change to the sending logic.
"""

from typing import Protocol

from hotelagent.modules.channel.schemas import OutboundResult, ReplyButton


class ChannelAdapter(Protocol):
    """A channel we can send through.

    Structural, not inherited: an object satisfies this by having the right
    methods, with no base class and no registration. Python calls that
    "structural typing", and mypy checks it — so a mistyped adapter is a lint
    error rather than a runtime surprise.
    """

    async def send_text(self, *, to: str, text: str) -> OutboundResult:
        """Send a plain text message. `to` is a channel-level identity."""
        ...

    async def send_buttons(
        self, *, to: str, text: str, buttons: list[ReplyButton]
    ) -> OutboundResult:
        """Send text with quick-reply buttons.

        Present from the start because the traveller journey is button-heavy
        (`docs/vision.md` §4.2) and because a protocol with one method tends to
        acquire the second one badly.
        """
        ...
