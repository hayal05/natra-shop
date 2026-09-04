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
 */
import "@testing-library/jest-dom/vitest";
