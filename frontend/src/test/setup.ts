/**
 * Task 79: loaded automatically before every test file (see
 * `vite.config.ts`'s `test.setupFiles`).
 *
 * `@testing-library/jest-dom/vitest` (as opposed to the plain
 * `@testing-library/jest-dom` entry point, which targets Jest) does two
 * things in one import: it calls `expect.extend(...)` with jest-dom's
 * matchers (`toBeInTheDocument`, `toHaveTextContent`, etc.) against
 * Vitest's own `expect`, and it ships the ambient `.d.ts` that makes
 * TypeScript aware those matchers exist on `Assertion` — so no separate
 * types package or manual `expect.extend` call is needed anywhere else.
 *
 * Bug fix (found while auditing the frontend suite for CI): React
 * Testing Library only unmounts/removes the DOM tree a `render()` call
 * produced automatically if it detects a global `afterEach` — which
 * requires Vitest's `test.globals: true` in `vite.config.ts`. This
 * project deliberately does NOT set `globals: true` (every test file
 * imports `describe`/`it`/`expect`/etc. explicitly from "vitest"
 * instead), so that auto-cleanup never registered. Every `render()` in
 * a multi-test file was piling another full copy of the component on
 * top of the previous test's leftover DOM, which is why so many
 * suites failed with "found multiple elements" once actually run for
 * real (see CURRENT_STATUS.md). Explicitly importing `cleanup` and
 * calling it here fixes this for every test file at once, without
 * needing `test.globals: true`.
 */
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});
