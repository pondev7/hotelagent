// `toBeInTheDocument` and friends. Imported for its side effect: it registers
// the DOM matchers on Vitest's `expect`.
import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

/**
 * Unmount whatever the last test rendered.
 *
 * React Testing Library registers this itself — but only when Vitest's
 * `globals` are enabled, because it looks for a global `afterEach` to hook.
 * This project keeps globals off and imports `describe`/`it`/`expect`
 * explicitly, so the hook has to be registered by hand.
 *
 * Without it every render accumulates in one shared document, and assertions
 * start failing with "found multiple elements" — a failure that blames the
 * component for what is really a leak between tests.
 */
afterEach(cleanup);
