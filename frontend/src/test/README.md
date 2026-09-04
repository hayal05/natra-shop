# Frontend tests

Task 79. Test infra setup: Vitest + React Testing Library + jsdom,
wired into `vite.config.ts`'s `test` block (so there's no separate
`vitest.config.ts` to keep in sync with the app's own Vite config) and
`package.json`'s `test`/`test:watch` scripts. `setup.ts` extends
Vitest's `expect` with jest-dom's matchers via
`@testing-library/jest-dom/vitest`, loaded before every test file.
`smoke.test.tsx` proves the three pieces (Vitest, jsdom, Testing
Library) actually run together — it renders a plain element with no
dependency on real app code, deliberately, since Tasks 80-84 (see
`PROJECT_ROADMAP.md`'s Phase 7 table) are where actual pages/components
get covered.

## Running

```
cd frontend
npm install
npm test
```

(`npm run test:watch` for watch mode during development.)

Not yet run for real in this project's sandbox: outbound npm registry
access returns 403 here (`npm install` fails the same way it has since
earlier phases — see `CURRENT_STATUS.md`/`backend/tests/README.md`'s
own notes on sandbox network access), so this task's config and test
file were written and manually reviewed rather than executed. The
config follows Vitest's documented Vite integration (`defineConfig`
from `vitest/config`, which is Vite's own `defineConfig` with the
`test` key's types merged in) and jest-dom's documented Vitest setup
(`@testing-library/jest-dom/vitest`), not a novel pattern — but running
`npm test` for real is the first thing to do once `npm install` is
possible, before Task 80 builds on top of this.

## Conventions for Tasks 80-84

- One test file per component/page, colocated or grouped by area per
  PROJECT_ROADMAP.md's Phase 7 table (seller auth pages, admin +
  seller dashboard, buyer pages, admin pages, shared).
- Mock `api/sellers.ts` (and the equivalent buyer/admin API modules)
  rather than hitting a real backend — this suite has no fake backend
  the way `backend/tests/fake_oracle.py` gives the Python suite one.
- Reuse `setup.ts`'s global jest-dom matchers; no per-file setup needed
  beyond `render`/`screen` (and `@testing-library/user-event`, already
  a devDependency, for click/type interactions) from
  `@testing-library/react`.
