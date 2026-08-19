"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";

/**
 * A one-line wrapper, and it earns its file.
 *
 * `next-themes` needs React context, which only exists in a client component.
 * `app/layout.tsx` is a server component, and marking the whole layout
 * `"use client"` to accommodate one provider would drag every page it wraps
 * into the browser bundle. Isolating the boundary here keeps the layout — and
 * everything rendered inside it that does not itself opt in — on the server.
 */
export function ThemeProvider({ children, ...props }: ComponentProps<typeof NextThemesProvider>) {
  return <NextThemesProvider {...props}>{children}</NextThemesProvider>;
}
