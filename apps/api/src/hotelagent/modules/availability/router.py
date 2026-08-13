"""The availability router.

Not a FastAPI router — this is the routing *logic* of `docs/vision.md` §3.4:
pick the provider that matches the hotel's tier, and return a result the caller
cannot distinguish by source.

```
check_availability(hotel_id, dates, guests, room_type?)
  -> { status, price, eta_seconds, source_tier, ... }
```

Hotels are never migrated en masse. They live permanently at different tiers
within the same city, and this dispatch is what makes that invisible to
everything above it.
"""

from hotelagent.enums import IntegrationTier
from hotelagent.modules.availability.providers import bot, live, manual
from hotelagent.modules.availability.providers.base import AvailabilityProvider

# The three slots. Two raise NotImplementedError today, and their presence is
# invariant #3 — filling a stub is an afternoon, retrofitting a router around
# hardcoded calendar reads is a rewrite of the agent's core flow.
#
# Note there is no cast here: mypy accepts these modules as satisfying
# `AvailabilityProvider` on their shape alone. A provider whose `check`
# signature drifts becomes a type error rather than a runtime surprise.
_PROVIDERS: dict[IntegrationTier, AvailabilityProvider] = {
    IntegrationTier.MANUAL: manual,
    IntegrationTier.BOT: bot,
    IntegrationTier.LIVE: live,
}


def provider_for(tier: IntegrationTier) -> AvailabilityProvider:
    """The provider handling a given tier.

    A missing tier is a programming error rather than a runtime condition —
    the enum and this table must stay in step, and failing loudly is how you
    find out that they have not.
    """
    try:
        return _PROVIDERS[tier]
    except KeyError as exc:  # pragma: no cover - unreachable while the enum is closed
        raise NotImplementedError(f"no availability provider for tier {tier!r}") from exc
