import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge class names, letting the caller override a component's defaults.
 *
 * `clsx` flattens conditionals; `tailwind-merge` then resolves conflicts by
 * Tailwind's own rules, so `cn("px-4", "px-6")` is `px-6` rather than both.
 * Without the second half, a variant prop that tries to widen a button's
 * padding loses to whatever the base class happened to declare, and which one
 * wins depends on stylesheet order — a bug that moves when you rename a file.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
