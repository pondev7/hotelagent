import { Building2, ClipboardList, Inbox, Receipt } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import type { City } from "@contracts";
import { CitySwitcher } from "@/components/city-switcher";
import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/lib/utils";

/**
 * The frame every operator screen is hung inside.
 *
 * The three unbuilt destinations are listed and visibly disabled rather than
 * hidden. An operator learning the desk should be able to see the shape of the
 * job — inbox, queue, reconciliation — and a navigation that grows an item per
 * slice re-teaches the layout four times.
 */
const NAV = [
  { href: "/hotels", label: "Directory", Icon: Building2, ready: true },
  { href: "/inbox", label: "Inbox", Icon: Inbox, ready: false },
  { href: "/call-tasks", label: "Call tasks", Icon: ClipboardList, ready: false },
  { href: "/reconciliation", label: "Payments", Icon: Receipt, ready: false },
] as const;

export function AppShell({
  cities,
  cityId,
  active,
  children,
}: {
  cities: City[];
  cityId: string;
  active: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-6 px-4">
          <Link href="/hotels" className="font-semibold tracking-tight">
            HotelAgent<span className="text-muted-foreground"> ops</span>
          </Link>

          <nav className="flex items-center gap-1" aria-label="Sections">
            {NAV.map(({ href, label, Icon, ready }) =>
              ready ? (
                <Link
                  key={href}
                  href={`${href}?city=${cityId}`}
                  aria-current={active === href ? "page" : undefined}
                  className={cn(
                    "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm transition-colors",
                    active === href
                      ? "bg-muted font-medium text-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <Icon className="h-4 w-4" aria-hidden />
                  {label}
                </Link>
              ) : (
                <span
                  key={href}
                  title="Not built yet"
                  aria-disabled="true"
                  className="flex cursor-not-allowed items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm text-muted-foreground/40"
                >
                  <Icon className="h-4 w-4" aria-hidden />
                  {label}
                </span>
              ),
            )}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <CitySwitcher cities={cities} selected={cityId} />
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
    </div>
  );
}
