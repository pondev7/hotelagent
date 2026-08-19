import { Skeleton } from "@/components/ui/skeleton";

/**
 * Shown while the server component above is still fetching.
 *
 * `loading.tsx` is a Next convention: the App Router wraps the route in a
 * Suspense boundary using this as the fallback, so the shell paints
 * immediately and only the table waits. Nothing here is wired up by hand.
 *
 * The rows are the height of real rows. A skeleton that does not match causes
 * the page to jump when data lands, which is worse than showing nothing.
 */
export default function Loading() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-7 w-40" />
        <Skeleton className="h-4 w-64" />
      </div>
      <Skeleton className="h-8 w-56" />
      <div className="space-y-px rounded-lg border p-3">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-12 w-full" />
        ))}
      </div>
    </div>
  );
}
