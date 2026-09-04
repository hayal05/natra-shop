# NATRA — PROJECT ROADMAP

This roadmap is fixed unless explicitly changed by the project owner.
Development proceeds **one small task at a time**, in the order below.
Never skip ahead to a future phase without explicit instruction
("Start Phase 2", "Start Phase 3", etc.).

---

## PHASE 1 — BASIC MARKETPLACE FOUNDATION

Goal: a minimal working marketplace with no payment verification yet.

- Buyer product browsing (homepage/grid)
- Buyer product details
- Buyer Buy Now
- NATRA CBE/Telebirr payment information shown to buyer
- Buyer receipt URL submission (stored only, not verified)
- Seller registration
- Seller login
- Seller add product
- Seller view own products
- Admin login
- Admin view products
- Admin set NATRA CBE payment information
- Admin set NATRA Telebirr payment information

### Phase 1 Task Order

| # | Task |
|---|------|
| 1 | Minimal project structure |
| 2 | Backend starts successfully |
| 3 | Frontend starts successfully |
| 4 | Oracle database connection |
| 5 | Initial database schema |
| 6 | Seller registration |
| 7 | Seller login |
| 8 | Seller Add Product |
| 9 | Seller View Products |
| 10 | Buyer Product Grid |
| 11 | Buyer Product Details |
| 12 | Buy Now + NATRA payment information |
| 13 | Receipt URL submission |
| 14 | Admin login |
| 15 | Admin product viewing |
| 16 | Admin CBE/Telebirr settings |
| 17 | Phase 1 integration testing |

Explicitly excluded from Phase 1: receipt verification, Playwright,
duplicate payment protection, commission calculation, seller earnings,
seller settlements, buyer accounts/email/phone, shopping cart, search,
filters, notifications, reviews, messaging, advanced analytics/dashboards,
Google Drive API/OAuth, recommendation systems.

---

## PHASE 2 — PAYMENT VERIFICATION

Goal: verify buyer-submitted receipts and release product access automatically.

- Telebirr receipt verification
- CBE receipt verification
- Playwright browser automation where necessary
- Amount validation
- Status validation
- Transaction/reference number extraction
- Duplicate payment protection (using transaction/reference ID, never payer name)
- Successful payment confirmation
- Product delivery release (buyer receives seller's Drive link)

### Phase 2 Task Order

Defined at the start of Phase 2 (mirrors how Phase 1's task table was
fixed up front), following the same "small task, fixed order" rule as
Phase 1. Not to be skipped ahead of without explicit instruction.

| # | Task |
|---|------|
| 18 | Playwright installed and working (browser automation environment ready) |
| 19 | Receipts table gains verification fields (status, transaction_ref, verified_amount, provider) |
| 20 | CBE receipt page fetching (Playwright loads a receipt URL, returns raw content) |
| 21 | CBE data extraction (amount / status / transaction reference parsing) |
| 22 | Telebirr receipt page fetching |
| 23 | Telebirr data extraction (amount / status / transaction reference parsing) |
| 24 | Amount + status validation against the product's price |
| 25 | Duplicate payment protection (unique transaction/reference id) |
| 26 | Verification endpoint (ties fetch + extract + validate + duplicate check together) |
| 27 | Successful payment confirmation + product delivery release (buyer receives seller's Drive link) |
| 28 | Phase 2 integration testing |

This order may be adjusted if a task turns out to need splitting further
once its details become clear (e.g. Task 20/21 might turn out small
enough to merge) — any such change will be reflected here, not just
mentioned in passing.

---

## PHASE 3 — MARKETPLACE FINANCE

Goal: commissions, seller earnings, and settlements.

- Commission calculation
- Seller earnings tracking
- Unsettled seller balances
- Settlement records
- Seller payment methods (CBE/Telebirr, for receiving settlement, not shown to buyers)
- Admin settlement management (mark settlements completed)
- Financial reporting (sales, revenue, commissions)

### Phase 3 Task Order

Defined at the start of Phase 3, same "small task, fixed order" rule as
Phases 1-2. Numbering continues from Phase 2's last task (28). Not to
be skipped ahead of without explicit instruction.

| # | Task |
|---|------|
| 29 | `admin_settings` gains a `commission_rate` field (NOT NULL, defaults to 10.00) |
| 30 | Record NATRA's commission + seller payable on a verified sale (new `sales` table, populated by `verify_receipt()`) |
| 31 | Admin read/write access to `commission_rate` (GET + PUT /admin/settings) |
| 32 | Seller earnings summary (GET /sellers/earnings — totals from `sales`) |
| 33 | Seller payment methods (GET/PUT /sellers/payment-methods — CBE/Telebirr payout account, for receiving a future settlement, never shown to buyers) |
| 34 | Settlement records (POST/GET /admin/settlements — admin records that NATRA settled an amount to a seller; starts `status='pending'`, no 'completed' transition yet) |
| 35 | Admin settlement management (POST /admin/settlements/{id}/complete — marks a settlement `'completed'` and stamps `completed_at`, idempotent) |
| 36 | Settled/unsettled split (GET /sellers/earnings gains `settled_total`/`unsettled_total`, from this seller's `'completed'` settlements) |
| 37 | Admin financial reporting — platform totals (GET /admin/reports, admin-only, same six fields as GET /sellers/earnings but summed across every seller, no grouping) |
| 38 | Admin financial reporting — per-seller breakdown (GET /admin/reports/by-seller, admin-only, same query as Task 37 grouped by `seller_id`) |

Phase 3 is complete — Task 38 was the last item on its task list. The
next phase (Phase 4 — Production) will only begin on explicit
instruction ("Start Phase 4"), per the phase-control rule in
CLAUDE_MASTER_PROMPT.md.

---

## PHASE 4 — PRODUCTION

Goal: harden and deploy the production system.

- Security hardening
- Permission improvements
- Validation improvements
- Error handling improvements
- UI/UX polish
- Performance improvements
- Oracle Cloud Free Tier deployment (Nginx + Uvicorn + FastAPI + React build)
- Monitoring
- Backup strategy

### Phase 4 Task Order

Defined at the start of Phase 4, same "small task, fixed order" rule as
Phases 1-3. Numbering continues from Phase 3's last task (38). Not to
be skipped ahead of without explicit instruction. Ordered by
dependency: closing known auth/validation gaps and hardening
configuration first (nothing downstream should build on top of a known
hole), then error handling and performance, then the deployment
mechanics that assume a hardened backend, then monitoring/backup, which
assume a defined deployment target.

| # | Task |
|---|------|
| 39 | Fail-fast startup configuration check (`ORACLE_*`/`JWT_SECRET_KEY` required to start; `ADMIN_*` warn-only) |
| 40 | CORS configuration (restrict allowed origins via env var, instead of no CORS policy at all) |
| 41 | Tighten `get_current_seller_id` to reject an admin-role token (closes the one-directional gap flagged in `get_current_admin`'s docstring since Task 15) |
| 42 | Settlement over-payment validation (`POST /admin/settlements` rejects an amount that would push a seller's unsettled balance negative — closes the gap flagged since Task 34) |
| 43 | Centralized error handling (a single exception handler so uncaught errors return a consistent, non-leaking JSON shape) |
| 44 | Rate limiting on `POST /sellers/login` and `POST /admin/login` (brute-force protection) |
| 45 | Database indexes review (`sales.seller_id`, `settlements.seller_id`, `receipts` transaction-ref lookup, etc.) |
| 46 | Production environment configuration (`.env.production` template, systemd service file for Uvicorn, Nginx reverse-proxy config skeleton) |
| 47 | React production build + static serving integration (Vite build served via Nginx, per Task 46's config) |
| 48 | Monitoring (structured logging; confirm `/health`, `/health/db`, `/health/playwright` are suitable for external checks) |
| 49 | Backup strategy documentation (Oracle Autonomous DB backup/restore approach) — **done** |

### Phase 5 — Frontend Build

The project owner decided (after Task 49) to build the frontend now,
as its own sub-sequence, rather than defer it. Brand color for this
phase: **blood red** (supersedes any earlier color note — this is the
first place a brand color has actually been recorded in the project
docs). Numbering continues from Phase 4's last task (49). Ordered by
dependency: shared shell/design system/routing/API-client first
(nothing else can be built without it), then the buyer flow (no auth,
simplest, and the thing a visitor sees first), then seller (needs its
own auth), then admin (needs its own auth, depends on data the other
two roles produce), then a final integration/responsive pass.

| # | Task |
|---|------|
| 50 | Frontend foundation: routing (`react-router-dom`) + design-system tokens (blood-red brand palette) + base layout shell + shared API client — replaces Task 3's placeholder |
| 51 | Buyer: product grid / browse view (`GET /products`) |
| 52 | Buyer: product details view (`GET /products/{id}`) |
| 53 | Buyer: Buy Now flow — payment info display + receipt URL submission (`GET /payment-info`, `POST /receipts...`) |
| 54 | Buyer: receipt status + delivery link view (`GET /receipts/{id}/delivery`) |
| 55 | Seller: register/login UI + session handling (`POST /sellers/register`, `POST /sellers/login`) |
| 56 | Seller: dashboard — add/list products (`POST /products`, `GET /products/mine`) |
| 57 | Seller: payment methods + earnings UI (`GET`/`PUT /sellers/payment-methods`, `GET /sellers/earnings`) |
| 58 | Admin: login UI at `/admin-portal/login` (`POST /admin/login`) — frontend route is `/admin-portal`, not `/admin`, because `deploy/nginx/natra.conf` proxies `/admin/...` to the backend API (decided in Task 50) |
| 59 | Admin: products overview UI (`GET /admin/products`) — **done** |
| 60 | Admin: settings UI (`GET`/`PUT /admin/settings`) — **done** |
| 61 | Admin: settlements UI (`POST`/`GET /admin/settlements`, `POST .../complete`) — **done** |
| 62 | Admin: reports UI — platform totals (`GET /admin/reports`) — **done** |
| 63 | Admin: reports UI — per-seller breakdown (`GET /admin/reports/by-seller`) — **done** |
| 64 | Frontend integration pass — buyer flow click-through against the real backend — **done** |
| 65 | Frontend integration pass — seller flow click-through against the real backend — **done** |
| 66 | Frontend integration pass — admin flow click-through against the real backend — **done** |
| 67 | Frontend integration pass — mobile-first responsive sweep of all three roles — **done** |

Same "small task, fixed order" rule as Phases 1-4; not to be skipped
ahead of without explicit instruction.

This order may be adjusted if a task turns out to need splitting
further once its details become clear, same as Phases 2-3 — any such
change will be reflected here, not just mentioned in passing.

**Renumbered after Task 58**, at the project owner's request, to keep
each task to one response: the original Task 59 ("products/sellers
overview + settings UI") split into 59 (products overview) and 60
(settings); the original Task 61 ("reports UI") split into 62/63
(platform totals / per-seller); the original Task 62 (one combined
"integration pass") split into 64-67 (one pass per role, plus a
dedicated responsive sweep). Total remaining task count went from 4 to
9 — numbering above is final.

Phase 5 is complete — Task 67 was the last item on its task list, and
every role's flow (buyer, seller, admin) has now had both an
endpoint-by-endpoint correctness trace (Tasks 64-66) and a mobile
responsiveness pass (Task 67). The next phase would only begin on
explicit instruction, per the phase-control rule in
CLAUDE_MASTER_PROMPT.md — none is currently defined past Phase 5,
since it was itself an ad hoc addition after Phase 4 (see this
section's own opening note).

---

### Phase 6 — Backend Hardening / Ops (ad hoc)

Opened by Task 68, the same way Phase 5 was opened after Task 49: not
one of the four phases in `CLAUDE_MASTER_PROMPT.md` section 20, but a
project-owner-requested addition once a gap was found (unverified
seller emails, no password-reset path) rather than deferred to a
future numbered phase. No fixed task list defined in advance — each
task here is added to this table once it's actually done, per the
same "explicit instruction only" phase-control rule as every other
phase.

| # | Task |
|---|------|
| 68 | Backend: email-based OTP verification (signup + password reset) via Brevo — `app/otp.py`, `app/brevo_email.py`, four new `/sellers/...` endpoints — **done** |
| 69 | Frontend: UI for Task 68's OTP endpoints — post-registration email-verification screen (`/seller/verify-email`) + forgot-password flow (`/seller/forgot-password`) — **done** |
| 70 | Frontend: sidebar navigation (persistent on desktop, overlay on mobile) replacing the top header/nav, cream-white nav background instead of blood-red — **done** |
| 71 | Backend + frontend: `POST /sellers/login` now gates on `email_verified` (Task 68's deferred scope decision), with `SellerRegister.tsx`'s auto-login removed and `SellerLogin.tsx` handling the new 403 — **done** |
| 72 | Backend: automated test suite for the seller email-verification flow and Task 71's login gate (`backend/tests/`, pytest + a fake in-memory Oracle double) — **done** |

---

### Phase 7 — Automated Test Coverage (full project)

Opened by Task 72, at the project owner's explicit request to schedule
out full backend + frontend test coverage as a sequence of
one-response-sized tasks up front, rather than Phase 6's usual "add
each task to this table once it's actually done" pattern. That's a
deliberate, one-time deviation for this phase only — the tasks below
are planned, not done, and each still only starts on explicit
instruction per the standing phase-control rule; this table just names
what "next" will be before it's asked for.

Split by dependency and blast radius, same reasoning as every prior
phase's split: each task is independently reviewable, and a task that
turns out to need splitting further gets split the same way Phases
2-3 and 5 were (reflected here, not just mentioned in passing).

**Backend (extends Task 72's pytest + `fake_oracle.py` pattern):**

| # | Task | Status |
|---|------|--------|
| 73 | Products endpoints — `POST /products`, `GET /products/mine`, `GET /products`, `GET /products/{id}`, `GET /payment-info` | done |
| 74 | Seller earnings & payment methods — `GET /sellers/earnings`, `GET`/`PUT /sellers/payment-methods` | done |
| 75 | Receipts flow — `POST /receipts`, `POST /receipts/{id}/verify`, `GET /receipts/{id}/delivery`. Heaviest of the backend tasks: needs new fakes for `browser.py`/`cbe.py`/`telebirr.py` (receipt-page scraping) and `duplicate_check.py`, on top of `fake_oracle.py` | done |
| 76 | Admin auth + catalog — `POST /admin/login`, `GET /admin/products`, `GET`/`PUT /admin/settings` | done |
| 77 | Admin settlements + reports — `POST`/`GET /admin/settlements`, `POST /admin/settlements/{id}/complete`, `GET /admin/reports`, `GET /admin/reports/by-seller` | done |
| 78 | Cross-cutting backend — `/health*` endpoints, the Task 43 generic-500 handler, Task 39's startup config validation, CORS origin parsing; anything not naturally covered by Tasks 73-77 | done |

**Frontend (new infrastructure — no test runner exists yet):**

| # | Task | Status |
|---|------|--------|
| 79 | Test infra setup — Vitest + React Testing Library + jsdom, `vite.config.ts`/`package.json` wiring, one smoke test proving it runs | done |
| 80 | Unit tests — seller auth pages: `SellerLogin.tsx`, `SellerRegister.tsx`, `VerifyEmail.tsx`, `ForgotPassword.tsx` (mock `api/sellers.ts`) | done |
| 81 | Unit tests — admin auth + seller dashboard: `AdminLogin.tsx`, `SellerHome.tsx`, `SellerPayments.tsx` | done |
| 82 | Unit tests — buyer pages: `BuyerHome.tsx`, `ProductDetail.tsx`, `BuyNow.tsx`, `ReceiptStatus.tsx` | done |
| 83 | Unit tests — admin pages: `AdminHome.tsx`, `AdminSettings.tsx`, `AdminSettlements.tsx`, `AdminReports.tsx`, `AdminReportsBySeller.tsx` | done |
| 84 | Unit tests — shared: `Sidebar.tsx`, `Layout.tsx`, `lib/session.ts`, `lib/adminSession.ts`, `lib/format.ts`, `api/client.ts` | done |

**End-to-end (new use of the `playwright` dependency — currently only
used for CBE receipt scraping in `app/browser.py`, not testing):**

| # | Task | Status |
|---|------|--------|
| 85 | E2E infra setup — Playwright test config, scripted way to bring up backend + frontend together for a run | not started |
| 86 | E2E — seller flow: register → verify email → log in → add a product | not started |
| 87 | E2E — buyer flow: browse → buy now → submit receipt → check status | not started |
| 88 | E2E — admin flow: log in → review settlements → view reports | not started |

---

## PHASE 8 — PRODUCT THUMBNAILS

Goal: sellers upload a thumbnail when adding/editing a product; buyers
see it on listings and detail pages. Uses Oracle Object Storage (per
`CLAUDE_MASTER_PROMPT.md` section 7 — images never go in the database)
and the `products.thumbnail_ref` column that has sat reserved-but-unused
since Task 8 (see `ARCHITECTURE.md` and `DATABASE_SCHEMA.md`).

Scheduled out as a sequence of one-response-sized tasks up front, same
one-time deviation as Phase 7's table — the tasks below are planned,
not done, and each still only starts on explicit instruction per the
standing phase-control rule. Numbering continues from Phase 7's last
task (88). Split by dependency and blast radius, same reasoning as
every prior phase's split; a task that turns out to need splitting
further gets split the same way (reflected here, not just mentioned in
passing).

**Split after initial planning, at the project owner's request:** the
original Task 89 ("Object Storage client wrapper — config/env vars,
connection setup, a health check") bundled three separable pieces —
config, a client module, and an endpoint — into one task, unlike Task
18 (Playwright), which only needed a client module + health check
because Playwright has no separate credential/bucket configuration
step. Object Storage does (namespace, region, bucket name, auth
method), so that config step is pulled out on its own, mirroring how
`db.py` (Task 4) and Task 39's fail-fast startup check already treat
Oracle's connection config as separate from Oracle's own client setup.
Split into three: **89** (config/env vars only, no client code), **90**
(client wrapper module, mirrors `db.py`'s Task 4 role), **91** (health
check endpoint, mirrors Task 18's `check_browser()`/`GET
/health/playwright` pattern). Every task from the old 90 onward shifts
up by two — numbering below is final. Total task count for the phase
went from 10 to 12.

**Split a second time, at the project owner's request:** the tasks from
the old Task 92 onward were still bundling multiple separable pieces
into one response each, unlike 89-91's now-proven one-concern-per-task
granularity. Same dependency/blast-radius reasoning as the first split:

- Old **92** ("Upload helper — validate file type/size, generate a
  stable object name, upload bytes, return the object's URL") bundled
  a pure validation function with a separate Object-Storage-calling
  upload function. Split into **92** (validation only, no Object
  Storage interaction, unit-testable with no fake needed) and **93**
  (name generation + upload + URL, using Task 90's client).
- Old **93** (the upload endpoint) is unchanged in scope, just
  renumbered to **94**, since auth + ownership check + one helper call
  + one column write is already comparable in size to Task 8/Task 93's
  existing precedent ("Implement Add Product").
- Old **94** ("surface `thumbnail_ref` in `GET /products`, `GET
  /products/{id}`, and `GET /products/mine`") bundled three separate
  endpoint changes into one task, the same pattern Task 38 and Phase
  5's per-role split already treat as three tasks, not one. Split into
  **95**, **96**, **97** — one endpoint each.
- Old **95** ("backend tests for Tasks 89-94") bundled tests for six
  tasks' worth of code into one response, the same pattern Phase 7's
  73-78/80-84 already treat as one task per feature area, not one task
  per phase. Split into **98** (client wrapper + health check, i.e.
  Tasks 90-91), **99** (validation + upload helper, Tasks 92-93),
  **100** (the upload endpoint, Task 94), **101** (the three surfaced
  GET endpoints, Tasks 95-97).
- Old **96-99** (frontend feature work) are unchanged in scope, just
  renumbered to **102-105** — each was already one concern (one form,
  one API wiring call, one page's display logic).
- Old **100** ("frontend tests for Tasks 96-99") bundled tests for four
  tasks into one response, same issue as old 95. Split into **106**,
  **107**, **108**, **109** — one per frontend task, mirroring Phase
  7's 80-84 per-page test split.

Every task from the old 92 onward shifts up — numbering below is
final. Total task count for the phase went from 12 to 21.

**Backend:**

| # | Task | Status |
|---|------|--------|
| 89 | Object Storage config — env vars (bucket name, namespace, region, auth credentials) added to `.env.example`/`.env.production.example`; extends Task 39's startup check to cover the new vars (as recommended/warn-only, not fatal — see `app/main.py`'s Task 89 docstring note for why). No client code yet. | done |
| 90 | Object Storage client wrapper — `app/object_storage.py`, initializes the OCI SDK client from Task 89's config (mirrors `db.py`'s Task 4 role) | done |
| 91 | Object Storage health check — `GET /health/object-storage` (mirrors Task 18's `check_browser()`/`GET /health/playwright` pattern), using Task 90's client | done |
| 92 | Thumbnail file validation — `validate_thumbnail_file()`: content-type/extension allowlist + max-size check, raises a clear error; pure function, no Object Storage interaction, no endpoint | not started |
| 93 | Thumbnail upload helper — `upload_thumbnail()`: stable/unique object name generation, upload bytes via Task 90's client, return the object's URL (uses Task 92's validator; still no endpoint) | not started |
| 94 | `POST /products/{product_id}/thumbnail` — seller-auth via existing `get_current_seller_id`, ownership check, calls Task 93's helper, writes `thumbnail_ref` | not started |
| 95 | Surface `thumbnail_ref` (as a full URL) in `GET /products` only (buyer grid) | not started |
| 96 | Surface `thumbnail_ref` (as a full URL) in `GET /products/{id}` only (buyer detail) | not started |
| 97 | Surface `thumbnail_ref` (as a full URL) in `GET /products/mine` only (seller dashboard) | not started |
| 98 | Backend tests — Object Storage client wrapper + health check (Tasks 90-91); new fake for Object Storage, mirrors `fake_oracle.py`'s pattern | not started |
| 99 | Backend tests — validation + upload helper (Tasks 92-93), using Task 98's fake | not started |
| 100 | Backend tests — thumbnail upload endpoint (Task 94): auth, ownership, happy path, validation-error and upload-error cases | not started |
| 101 | Backend tests — thumbnail surfaced across the three GET endpoints (Tasks 95-97) | not started |

**Frontend:**

| # | Task | Status |
|---|------|--------|
| 102 | File input + local preview in the seller's add-product form | not started |
| 103 | Wire the upload call — `api/products.ts` gets an `uploadThumbnail()` function, invoked after product create | not started |
| 104 | Display thumbnails on the buyer product grid (`BuyerHome.tsx`), with a placeholder for products that have none | not started |
| 105 | Display the thumbnail on `ProductDetail.tsx` | not started |
| 106 | Frontend tests — file input + preview (Task 102) | not started |
| 107 | Frontend tests — upload wiring (Task 103) | not started |
| 108 | Frontend tests — buyer grid thumbnail display (Task 104) | not started |
| 109 | Frontend tests — product detail thumbnail display (Task 105) | not started |

---

## Current Position

See `CURRENT_STATUS.md` for the current phase, the last completed task,
and the exact next task.
