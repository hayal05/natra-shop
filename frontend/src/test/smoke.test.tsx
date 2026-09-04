import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

/**
 * Task 79: proves the test infra itself works end to end, deliberately
 * decoupled from any real app component so it doesn't overlap with
 * Tasks 80-84's actual page/component coverage (see
 * PROJECT_ROADMAP.md's Phase 7 table). Three things have to be true at
 * once for this to pass:
 *
 * 1. Vitest is wired up and can find/run this file at all.
 * 2. The `jsdom` environment (vite.config.ts's `test.environment`) is
 *    active, so `render()` has a DOM to mount into.
 * 3. `@testing-library/jest-dom/vitest` (setup.ts) has extended
 *    `expect` with `toBeInTheDocument`.
 */
describe("test infra smoke test", () => {
  it("renders a component into jsdom and finds it with Testing Library", () => {
    render(<p>NATRA test infra is working</p>);

    expect(
      screen.getByText("NATRA test infra is working"),
    ).toBeInTheDocument();
  });
});
