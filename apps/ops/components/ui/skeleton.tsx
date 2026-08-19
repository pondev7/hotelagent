import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A shape that stands in for content that has not arrived.
 *
 * Sized to match what replaces it. A skeleton of the wrong height is worse than
 * a spinner: the page visibly jumps when the real row lands, and the operator's
 * eye has to re-find the line it was reading.
 */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />;
}
