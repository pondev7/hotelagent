import { AlertTriangle, PlugZap } from "lucide-react";

import { ApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";

/**
 * What the screen shows when the API does not answer.
 *
 * S08's exit criterion in one component: *"it survives the API being down
 * without a blank screen."* The navigation stays, the operator keeps their
 * bearings, and the message names the failure rather than apologising for it.
 *
 * The distinction the client draws between `unreachable` and `http` is spent
 * here — "the desk is offline" and "that hotel is not in this city" call for
 * different things from the person reading them, and one shared "something went
 * wrong" would tell them neither.
 */
export function FailureNotice({ error, what }: { error: unknown; what: string }) {
  const apiError = error instanceof ApiError ? error : null;
  const offline = apiError?.kind === "unreachable" || apiError?.kind === "timeout";
  const Icon = offline ? PlugZap : AlertTriangle;

  return (
    <Card className="border-destructive/30 bg-destructive/5 p-6">
      <div className="flex items-start gap-3">
        <Icon className="mt-0.5 h-5 w-5 shrink-0 text-destructive" aria-hidden />
        <div className="space-y-1">
          <p className="font-medium text-foreground">
            {offline ? `Cannot reach the API to load ${what}.` : `Could not load ${what}.`}
          </p>
          <p className="text-sm text-muted-foreground">
            {apiError?.operatorMessage ?? "An unexpected error occurred."}
          </p>
          {offline ? (
            <p className="pt-1 text-sm text-muted-foreground">
              Start it with <code className="rounded bg-muted px-1 py-0.5">make dev</code>, then
              reload. Bookings in progress are unaffected — this console is a view, not the
              record.
            </p>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
