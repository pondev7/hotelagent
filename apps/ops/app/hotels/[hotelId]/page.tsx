import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import type { City, Hotel } from "@contracts";
import { AppShell } from "@/components/app-shell";
import { FailureNotice } from "@/components/failure-notice";
import { TierBadge } from "@/components/tier-badge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getHotel, listCities } from "@/lib/api";
import { formatCommission } from "@/lib/format";

/**
 * One hotel, read-only.
 *
 * The reception number is shown in full here, unlike in the list. That is the
 * point of the screen at Tier C: an operator opens it in order to ring the
 * number. `CLAUDE.md`'s redaction rule is about *logs* — a number must never be
 * written to one — and is not a rule about what the person doing the job may
 * see.
 */

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

export default async function HotelPage({
  params,
  searchParams,
}: {
  params: Promise<{ hotelId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ hotelId }, query] = await Promise.all([params, searchParams]);

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

  const requested = Array.isArray(query.city) ? query.city[0] : query.city;
  const city = cities.find((candidate) => candidate.city_id === requested) ?? cities[0];

  if (!city) {
    return (
      <main className="mx-auto max-w-2xl px-4 py-16">
        <FailureNotice error={null} what="this hotel" />
      </main>
    );
  }

  let hotel: Hotel;
  try {
    hotel = await getHotel(hotelId, city.city_id);
  } catch (error) {
    // A hotel in another city answers 404, the same as one that does not
    // exist — see `get_hotel`. The console repeats that framing rather than
    // guessing at "you do not have access", which would confirm the row exists.
    return (
      <AppShell cities={cities} cityId={city.city_id} active="/hotels">
        <BackLink cityId={city.city_id} />
        <div className="mt-4">
          <FailureNotice error={error} what="this hotel" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell cities={cities} cityId={city.city_id} active="/hotels">
      <div className="space-y-6">
        <BackLink cityId={city.city_id} />

        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{hotel.name}</h1>
          <TierBadge tier={hotel.integration_tier} />
          {hotel.is_active ? null : <Badge variant="destructive">inactive</Badge>}
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Desk facts</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-6 sm:grid-cols-2">
              <Field label="Reception">
                {hotel.reception_phone ? (
                  <a
                    href={`tel:${hotel.reception_phone}`}
                    className="font-medium tabular-nums hover:underline"
                  >
                    {hotel.reception_phone}
                  </a>
                ) : (
                  <span className="text-muted-foreground">
                    None on file — a Tier C hotel with no number cannot be checked.
                  </span>
                )}
              </Field>
              <Field label="Commission">
                <span className="tabular-nums">{formatCommission(hotel.commission_rate)}</span>
              </Field>
              <Field label="Verification">{hotel.verification_status}</Field>
              <Field label="Address">
                {hotel.address ?? <span className="text-muted-foreground">—</span>}
              </Field>
            </dl>
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}

function BackLink({ cityId }: { cityId: string }) {
  return (
    <Link
      href={`/hotels?city=${cityId}`}
      className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="h-4 w-4" aria-hidden />
      Directory
    </Link>
  );
}
