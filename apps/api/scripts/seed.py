"""Put a city and a handful of hotels into the development database.

Why this exists: every console collection requires a `city_id`, and a `city_id`
comes from a row. Without seed data the ops console renders an empty directory
on a fresh checkout, and there is nothing to develop the loading, empty and
error states against — which is how those states end up designed by accident.

**Idempotent by natural key.** `make seed` twice produces the same three hotels,
not six. This is not the same mechanism as invariant #5: idempotency keys guard
money and inventory mutations against redelivery, whereas this is a dev
convenience that matches on the slug and the name. Nothing here touches a
booking or a ledger.

This script imports `models` directly, which the module boundary rule forbids
*between modules*. It is not a module: it has no `service.py`, nothing imports
it, and it is deleted the day real hoteliers are onboarded through the console.
`tests/unit/test_module_boundaries.py` scans `src/hotelagent` and does not reach
here — deliberately, but worth knowing rather than discovering.

Never run against production. It writes, and it is not a migration.
"""

import asyncio
import sys
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hotelagent.config import get_settings
from hotelagent.enums import IntegrationTier
from hotelagent.modules.inventory.models import City, Hotel, VerificationStatus

# Commission falls as the tier climbs — the incentive that makes a hotelier want
# to move off the telephone (`docs/vision.md` §2.4). Seeding one hotel per tier
# is what makes the directory's tier filter meaningful to look at.
HOTELS: list[dict[str, Any]] = [
    {
        "name": "Sea Breeze Residency",
        "address": "Beach Road, Kanyakumari",
        "reception_phone": "+919800000001",
        "integration_tier": IntegrationTier.MANUAL,
        "verification_status": VerificationStatus.VERIFIED,
        "commission_rate": Decimal("15.00"),
    },
    {
        "name": "Vivekananda Residency",
        "address": "Main Road, Kanyakumari",
        "reception_phone": "+919800000002",
        "integration_tier": IntegrationTier.BOT,
        "verification_status": VerificationStatus.VERIFIED,
        "commission_rate": Decimal("13.00"),
    },
    {
        "name": "Cape Comorin Grand",
        "address": "Sunrise Point, Kanyakumari",
        "reception_phone": "+919800000003",
        "integration_tier": IntegrationTier.LIVE,
        "verification_status": VerificationStatus.VERIFIED,
        "commission_rate": Decimal("11.00"),
    },
    {
        # Deliberately unverified and inactive. The directory should be
        # developed against a row that is *not* in the happy path, or the
        # verification badge and the inactive styling are never seen until a
        # real hotel is suspended.
        "name": "Shoreline Lodge",
        "address": "Kovalam Road, Kanyakumari",
        "reception_phone": None,
        "integration_tier": IntegrationTier.MANUAL,
        "verification_status": VerificationStatus.PENDING,
        "commission_rate": Decimal("15.00"),
        "is_active": False,
    },
]


async def _seed(session: AsyncSession) -> tuple[City, int, int]:
    settings = get_settings()

    city = await session.scalar(select(City).where(City.slug == settings.default_city_slug))
    if city is None:
        city = City(
            name="Kanyakumari",
            slug=settings.default_city_slug,
            state="Tamil Nadu",
            active_languages=["ta", "en", "hi"],
        )
        session.add(city)
        await session.flush()

    created = 0
    for spec in HOTELS:
        # Matched on (city, name) rather than on id: the id is a uuid7 minted at
        # insert time, so it is different on every machine and cannot be a
        # natural key. The name is what a human re-running this means by "the
        # same hotel".
        existing = await session.scalar(
            select(Hotel).where(Hotel.city_id == city.id, Hotel.name == spec["name"])
        )
        if existing is not None:
            continue
        session.add(Hotel(city_id=city.id, **spec))
        created += 1

    await session.commit()

    total = (
        await session.scalar(
            select(func.count()).select_from(Hotel).where(Hotel.city_id == city.id)
        )
        or 0
    )
    return city, created, total


async def main() -> int:
    settings = get_settings()
    if settings.is_production:
        print("refusing to seed a production database", file=sys.stderr)
        return 2

    engine = create_async_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            city, created, total = await _seed(session)
    finally:
        await engine.dispose()

    print(f"city {city.name} ({city.id})")
    print(f"hotels created: {created}, hotels in city: {total} (re-running adds none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
