import Link from "next/link";

import type { IntegrationTier } from "@contracts";
import { cn } from "@/lib/utils";

const TIERS: { value: IntegrationTier | null; label: string }[] = [
  { value: null, label: "All" },
  { value: "live", label: "Live" },
  { value: "bot", label: "Bot" },
  { value: "manual", label: "Manual" },
];

/**
 * Filter by tier, as links rather than as a controlled component.
 *
 * Deliberately not a client component. Each option is a URL, so the filter
 * costs no JavaScript, survives a reload, can be bookmarked, and opens in a new
 * tab if an operator wants two tiers side by side. The filter itself is applied
 * in SQL — see `list_hotels` — so the count under it is the count of matching
 * rows, not of the ones that happened to be on this page.
 */
export function TierFilter({
  cityId,
  active,
}: {
  cityId: string;
  active: IntegrationTier | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Filter by tier">
      {TIERS.map(({ value, label }) => {
        const params = new URLSearchParams({ city: cityId });
        if (value) params.set("tier", value);
        const isActive = value === active;

        return (
          <Link
            key={label}
            href={`/hotels?${params.toString()}`}
            aria-current={isActive ? "true" : undefined}
            className={cn(
              "rounded-md px-2.5 py-1 text-sm transition-colors",
              isActive
                ? "bg-foreground text-background"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {label}
          </Link>
        );
      })}
    </div>
  );
}
