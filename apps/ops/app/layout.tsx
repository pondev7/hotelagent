import type { Metadata } from "next";

import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "HotelAgent Ops",
  description: "The operator's console: directory, inbox, call tasks and payments.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // `suppressHydrationWarning` belongs here and nowhere else. next-themes
    // writes the theme class onto <html> before React hydrates, so this one
    // element legitimately differs between the server's HTML and the browser's
    // first render. Suppressing it anywhere else would hide real mismatches.
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
