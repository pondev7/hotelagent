import type { ReactNode } from "react";

import { Card } from "@/components/ui/card";

/**
 * Nothing here, said deliberately.
 *
 * Distinct from the failure notice on purpose: "this city has no manual hotels"
 * is a true and useful answer, while "the API is down" is not an answer at all.
 * A console that renders both as an empty table teaches its operators to
 * distrust it.
 */
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Card className="p-10 text-center">
      <p className="font-medium">{title}</p>
      {children ? <p className="mt-1 text-sm text-muted-foreground">{children}</p> : null}
    </Card>
  );
}
