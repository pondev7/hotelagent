import type { IntegrationTier } from "@contracts";

import { Badge } from "@/components/ui/badge";

/**
 * How we learn whether a room is free, as one glanceable mark.
 *
 * The label says the tier and the title says what it costs us in operator time,
 * because "manual" means nothing to someone new on the desk and "an operator
 * telephones reception" means everything. Commission is shown in its own column
 * rather than here — it is a number that gets compared down a column, not a
 * property of a badge.
 */
const TIERS: Record<IntegrationTier, { label: string; hint: string; variant: "success" | "default" | "warning" }> = {
  live: {
    label: "Live",
    hint: "Tier A — calendar in our dashboard or a PMS. Instant.",
    variant: "success",
  },
  bot: {
    label: "Bot",
    hint: "Tier B — hotelier WhatsApp bot. One to three minutes.",
    variant: "default",
  },
  manual: {
    label: "Manual",
    hint: "Tier C — an operator telephones reception. Five to fifteen minutes.",
    variant: "warning",
  },
};

export function TierBadge({ tier }: { tier: IntegrationTier }) {
  // Typed as the generated union, so adding a fourth tier in Python fails the
  // frontend build here rather than rendering `undefined` at 2am.
  const { label, hint, variant } = TIERS[tier];
  return (
    <Badge variant={variant} title={hint}>
      {label}
    </Badge>
  );
}
