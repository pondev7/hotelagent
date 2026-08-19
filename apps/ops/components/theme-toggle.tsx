"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

const OPTIONS = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "system", label: "System", Icon: Monitor },
] as const;

/**
 * Light, dark, or follow the machine.
 *
 * `mounted` is not defensive clutter — it is the fix for a real class of bug.
 * The server has no idea what theme the browser has stored, so it renders the
 * default; the browser then renders the stored one, the two trees disagree, and
 * React reports a hydration mismatch. Rendering a neutral placeholder until
 * after mount makes the first client render match the server's.
 */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) {
    return <div className="h-8 w-[102px] rounded-md bg-muted" aria-hidden />;
  }

  return (
    <div className="flex items-center gap-0.5 rounded-md bg-muted p-0.5" role="group" aria-label="Theme">
      {OPTIONS.map(({ value, label, Icon }) => (
        <button
          key={value}
          type="button"
          onClick={() => setTheme(value)}
          aria-label={label}
          aria-pressed={theme === value}
          className={cn(
            "rounded px-2 py-1 text-muted-foreground transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            theme === value && "bg-background text-foreground shadow-sm",
          )}
        >
          <Icon className="h-4 w-4" aria-hidden />
        </button>
      ))}
    </div>
  );
}
