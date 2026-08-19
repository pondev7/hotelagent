"use client";

import { ChevronDown } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";

import type { City } from "@contracts";
import { cn } from "@/lib/utils";

/**
 * Invariant #1, made visible.
 *
 * With one city this control looks like decoration. It is not: every request
 * the console makes carries the city it selects, and the day a second city
 * launches the difference between "we have a tenancy key" and "we have a
 * tenanted product" is exactly this widget existing.
 *
 * The selection lives in the URL rather than in React state or a cookie, so an
 * operator can send a colleague a link to what they are looking at and get the
 * same city — and so a mis-scoped screen is diagnosable by reading the address
 * bar instead of inspecting a store.
 */
export function CitySwitcher({ cities, selected }: { cities: City[]; selected: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [pending, startTransition] = useTransition();

  function choose(cityId: string) {
    const next = new URLSearchParams(searchParams);
    next.set("city", cityId);
    // Changing city invalidates a page offset — page 3 of Kanyakumari is not
    // page 3 of anything else.
    next.delete("offset");
    // `startTransition` keeps the current screen interactive while the server
    // renders the new one, instead of blanking it. The alternative reads as a
    // hang on a slow connection.
    startTransition(() => router.push(`?${next.toString()}`));
  }

  return (
    <div className="relative">
      <select
        value={selected}
        onChange={(event) => choose(event.target.value)}
        aria-label="City"
        className={cn(
          "h-8 appearance-none rounded-md border bg-background py-1 pl-2.5 pr-8 text-sm",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          pending && "opacity-60",
        )}
      >
        {cities.map((city) => (
          <option key={city.city_id} value={city.city_id}>
            {city.name}
          </option>
        ))}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-2 top-2 h-4 w-4 text-muted-foreground"
        aria-hidden
      />
    </div>
  );
}
