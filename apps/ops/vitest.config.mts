/**
 * The console's test runner.
 *
 * Vitest rather than Playwright, deliberately. S08's exit criterion is about a
 * read-only screen and its failure states, which are unit-testable; there is no
 * interaction worth driving a real browser for until the inbox composer (S09)
 * and the two-click call-task claim (S10). Adding a browser download to CI now
 * would be paying that cost four slices early.
 */

import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Mirrors the two path aliases in tsconfig.json. Vitest resolves modules
      // itself and does not read tsconfig `paths`, so a component importing
      // `@contracts` would fail here while typechecking cleanly — the classic
      // way these two configurations drift apart.
      "@contracts": fileURLToPath(
        new URL("../../packages/contracts/src/index.ts", import.meta.url),
      ),
      "@": fileURLToPath(new URL("./", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules/**", ".next/**"],
  },
});
