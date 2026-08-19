import Link from "next/link";

import type { City, Hotel, IntegrationTier, Page } from "@contracts";
import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { FailureNotice } from "@/components/failure-notice";
import { TierBadge } from "@/components/tier-badge";
import { TierFilter } from "@/components/tier-filter";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listCities, listHotels } from "@/lib/api";
import { formatCommission, maskPhone } from "@/lib/format";

/**
 * The hotel directory — the console's first real screen.
 *
 * A **server component**: it runs on the Node side, awaits the API directly and
 * sends HTML. No fetch happens in the browser, so there is no loading spinner
 * to manage, no `useEffect` to get wrong, and no API URL or CORS surface
 * exposed to the client. What the browser gets is markup plus the two small
 * client components that genuinely need interactivity.
 *
 * Read-only, per S08. Editing a hotel is not in this slice.
 */

const TIERS = new Set<string>(["live", "bot", "manual"]);

/** Narrow an untrusted `?tier=` to the union, or to nothing. */
function parseTier(raw: string | string[] | undefined): IntegrationTier | null {
  const value = Array.isArray(raw) ? raw[0] : raw;
  return value && TIERS.has(value) ? (value as IntegrationTier) : null;
}

export default async function HotelsPage({
  searchParams,
}: {
  // A promise in Next 15: search params are request data, and awaiting them is
  // what tells the framework this render depends on the request rather than
  // being statically prerenderable.
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;

  // The city list is fetched before anything else, because everything else
  // needs an id from it. If this fails there is no shell to render — the
  // switcher has nothing to show — so it gets its own failure path.
  let cities: City[];
  try {
    cities = await listCities();
  } catch (error) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-16">
        <FailureNotice error={error} what="the city list" />
      </main>
    );
  }

  if (cities.length === 0) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-16">
        <EmptyState title="No cities are configured.">
          Run <code className="rounded bg-muted px-1 py-0.5">make seed</code> to create
          Kanyakumari and a few hotels to look at.
        </EmptyState>
      </main>
    );
  }

  const requested = Array.isArray(params.city) ? params.city[0] : params.city;
  // An unknown or absent `?city=` falls back to the first city rather than
  // erroring. Falling back is safe *here* because the list came from the API
  // and contains only cities this console may see — unlike a default in
  // `params.py`, which would have invented a scope the caller never asked for.
  const city = cities.find((candidate) => candidate.city_id === requested) ?? cities[0];
  const tier = parseTier(params.tier);

  let page: Page<Hotel>;
  try {
    page = await listHotels({ cityId: city.city_id, tier });
  } catch (error) {
    return (
      <AppShell cities={cities} cityId={city.city_id} active="/hotels">
        <FailureNotice error={error} what="the hotel directory" />
      </AppShell>
    );
  }

  return (
    <AppShell cities={cities} cityId={city.city_id} active="/hotels">
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Hotel directory</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {page.total} {page.total === 1 ? "hotel" : "hotels"} in {city.name}
            {tier ? ` at the ${tier} tier` : null}.
          </p>
        </div>

        <TierFilter cityId={city.city_id} active={tier} />

        {page.items.length === 0 ? (
          <EmptyState title={tier ? `No ${tier}-tier hotels in ${city.name}.` : `No hotels in ${city.name} yet.`}>
            {tier
              ? "Every hotel launches at the manual tier; commission is the incentive to climb."
              : "Seed the development database, or sign a hotel."}
          </EmptyState>
        ) : (
          <Card className="overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Hotel</TableHead>
                  <TableHead>Tier</TableHead>
                  <TableHead>Commission</TableHead>
                  <TableHead>Reception</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {page.items.map((hotel) => (
                  <TableRow key={hotel.hotel_id}>
                    <TableCell>
                      <Link
                        href={`/hotels/${hotel.hotel_id}?city=${city.city_id}`}
                        className="font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {hotel.name}
                      </Link>
                      {hotel.address ? (
                        <p className="text-xs text-muted-foreground">{hotel.address}</p>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <TierBadge tier={hotel.integration_tier} />
                    </TableCell>
                    {/* Tabular numerals so the column compares down the page
                        rather than shimmying by a pixel per digit. */}
                    <TableCell className="tabular-nums">
                      {formatCommission(hotel.commission_rate)}
                    </TableCell>
                    <TableCell className="tabular-nums text-muted-foreground">
                      {maskPhone(hotel.reception_phone)}
                    </TableCell>
                    <TableCell>
                      {hotel.is_active ? (
                        <Badge variant={hotel.verification_status === "verified" ? "success" : "neutral"}>
                          {hotel.verification_status}
                        </Badge>
                      ) : (
                        <Badge variant="destructive">inactive</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}

        {page.total > page.items.length ? (
          <p className="text-sm text-muted-foreground">
            Showing {page.items.length} of {page.total}. Paging arrives when a city has more
            hotels than a screen.
          </p>
        ) : null}
      </div>
    </AppShell>
  );
}
