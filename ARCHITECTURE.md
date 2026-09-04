# NATRA — ARCHITECTURE

## Current Architecture (as of Task 27)

Sellers can register, log in, add products, and list their own products.
Buyers (no account, no auth) can list all products, view a single
product's details, see NATRA's own CBE/Telebirr payment info via
`GET /payment-info` — the step after "Buy Now" — and submit a payment
receipt URL via `POST /products/{product_id}/receipt`, which is stored
(not verified) in the `receipts` table. The Master Admin can log in via
`POST /admin/login` and has two admin-only routes guarded by the
`get_current_admin` dependency, which requires `role == "admin"` on
the JWT (rejecting a valid seller token with 403): `GET /admin/products`
— a platform-wide product listing (Task 15) — and `PUT /admin/settings`
— the write counterpart to `GET /payment-info`, letting the admin set
NATRA's own CBE/Telebirr account info (Task 16). `POST /products` and
`GET /products/mine` remain protected via `get_current_seller_id`;
`GET /products`, `GET /products/{product_id}`, `GET /payment-info`,
`POST /products/{product_id}/receipt`, and `POST /admin/login` are all
public. Phase 1 (Tasks 1–17) is complete and integration-tested against
a simulated database.

Phase 2 (Payment Verification) has begun: `GET /health/playwright`
(Task 18) confirms headless-browser automation via Playwright is
installed and working, and the `receipts` table has gained four nullable
verification columns — `status`, `transaction_ref`, `verified_amount`,
`provider` (Task 19), added via an idempotent migration in `init_db.py`
so it applies to databases that already ran Task 13's original table
creation. `app/cbe.py` (Task 20) can now load a CBE receipt URL
(`https://mbreciept.cbe.com.et/...`) and return its raw HTML/text, and
`extract_cbe_data()` (Task 21) parses that text into structured fields
(transaction reference, transferred amount, payer/receiver names, date,
reason) on a best-effort basis. `app/telebirr.py` (Task 22) mirrors
Task 20 for the other provider: `fetch_telebirr_receipt()` validates a
Telebirr receipt URL (`https://transactioninfo.ethiotelecom.et/...`)
against exactly that host, then reuses `cbe._load_page()` unchanged
(it was written host-agnostic in Task 20 for this reason) to load it
and return raw HTML/text — same success/failure dict shape as
`fetch_cbe_receipt()`. `extract_telebirr_data()` (Task 23) parses that
text into structured fields (`transaction_ref` from "Receipt No.",
`settled_amount`, `total_paid`, `payer_name`, `receiver_name` from
"Credited Party name", `payment_date`, `reason`) on a best-effort basis
— Telebirr's own bilingual field-label set, not copied from `cbe.py`'s
CBE-specific patterns, though the function's overall shape (never
raises, `found` flag, `likely_not_found` heuristic) mirrors
`extract_cbe_data()`. `parse_telebirr_receipt()` composes fetch +
extract, mirroring `parse_cbe_receipt()`. `app/validation.py`
(Task 24) adds `validate_payment(provider, extracted, expected_price)`
— provider-agnostic comparison logic, no Playwright/parsing dependency
— checking two things: the receipt was `found` (this task's scoped
definition of "status validation", since neither extractor captures an
explicit status field yet — see the module's docstring) and the paid
amount (`get_paid_amount()` picks `transferred_amount` for CBE,
`total_paid`/`settled_amount` for Telebirr) exactly matches the
product's price after rounding both to 2 decimals (exact match, not a
tolerance band — also a scoped decision recorded in the module
docstring). `app/duplicate_check.py` (Task 25) adds
`is_duplicate_transaction(transaction_ref, provider)` — an
application-level query rejecting a transaction that already backs a
`status = 'verified'` receipt row, keyed off `transaction_ref` +
`provider`, never the payer's name (per `CLAUDE_MASTER_PROMPT.md`
section 5). Backed by a database-level safety net: `init_db.py` (Task
25) adds a unique index on `receipts` scoped to only `'verified'` rows
via Oracle's function-based-index idiom (see `DATABASE_SCHEMA.md` for
the mechanics), guarding against a race between two concurrent
verification attempts — the application check remains the primary
mechanism since it produces a clear rejection reason instead of a raw
database error. `POST /receipts/{receipt_id}/verify` (Task 26) is now
the first endpoint that ties Tasks 20–25 together: given a receipt
already submitted via Task 13, it looks up the product's price,
determines the provider from the receipt URL's hostname
(`_determine_provider()`, reusing `cbe.CBE_RECEIPT_HOST` /
`telebirr.TELEBIRR_RECEIPT_HOST` so it can't drift from what each
fetcher's own URL validation accepts), calls the matching
`parse_*_receipt()`, runs `validate_payment()`, then
`is_duplicate_transaction()` if validation passed, and writes the
outcome to `receipts.status`/`transaction_ref`/`verified_amount`/
`provider` via a shared `_reject_receipt()` helper for every non-success
path. Public, no auth (a buyer verifies their own receipt), and
idempotent for an already-`'verified'` receipt — it returns the stored
result rather than re-running the pipeline. `GET
/receipts/{receipt_id}/delivery` (Task 27) is the buyer's final step:
once (and only once) a receipt's `status == 'verified'`, it returns the
owning product's `drive_link`; any other status (`'pending'`,
`'rejected'`, or `NULL`) returns 403 without revealing the link, and a
deliberate separate `GET` endpoint rather than folded into Task 26's
verify response (see the endpoint's own docstring). This is the last
Phase 2 endpoint task before Task 27's own scope closes and integration
testing; `drive_link` remains unreachable from every other endpoint
before a verified purchase. Frontend still has no API calls to the
backend.

```
natra/
  backend/
    requirements.txt   fastapi + uvicorn + oracledb + pyjwt
    .env.example        documents required ORACLE_*/JWT_SECRET_KEY env vars
    db/
      schema.sql         human-readable DDL reference (sellers, products,
                         admin_settings, receipts)
    app/
      __init__.py
      main.py           FastAPI app + /health + /health/db +
                         POST /sellers/register + POST /sellers/login +
                         POST /products + GET /products/mine (protected,
                         seller) + GET /products +
                         GET /products/{product_id} + GET /payment-info +
                         POST /products/{product_id}/receipt +
                         POST /admin/login +
                         GET /admin/products (protected, admin) +
                         PUT /admin/settings (protected, admin)
      db.py             get_connection() / check_connection() (oracledb)
      browser.py        check_browser() — Playwright headless-browser
                         liveness check (Task 18)
      cbe.py             fetch_cbe_receipt() — loads a CBE receipt URL
                         and returns raw HTML/text (Task 20);
                         extract_cbe_data() — best-effort parsing of
                         that text into structured fields (Task 21);
                         parse_cbe_receipt() composes both
      telebirr.py        fetch_telebirr_receipt() — loads a Telebirr
                         receipt URL and returns raw HTML/text (Task 22),
                         reusing cbe._load_page() as-is;
                         extract_telebirr_data() — best-effort parsing
                         of that text into structured fields, Telebirr's
                         own field-label set (Task 23);
                         parse_telebirr_receipt() composes both
      validation.py      validate_payment() — provider-agnostic amount +
                         status check against a product's price (Task 24);
                         no Playwright/network dependency
      duplicate_check.py is_duplicate_transaction() — rejects a
                         transaction_ref+provider already backing a
                         verified receipt (Task 25)
      init_db.py        applies schema.sql's DDL programmatically (idempotent);
                         also seeds the single admin_settings row
      security.py       hash_password() / verify_password() (PBKDF2-HMAC-SHA256)
      auth.py           create_access_token() / create_admin_access_token() /
                         decode_access_token() (JWT, HS256, 24h expiry,
                         role="seller"/"admin" claim)
  frontend/
    package.json        react + react-router-dom + vite + typescript
    vite.config.ts
    tsconfig*.json
    index.html
    .env.example         VITE_API_BASE_URL
    src/
      main.tsx           React entry point; wraps <App/> in <BrowserRouter>
      App.tsx            <Routes>: buyer (/, /product/:id), seller
                         (index/login/register real, other seller/*
                         sub-paths still placeholder), admin-portal/*
                         (NOT admin/* — that prefix is proxied to the
                         backend by deploy/nginx/natra.conf, see the
                         route's own comment; login (Task 58), index
                         (Task 59), settings (Task 60), settlements
                         (Task 61), and reports (Task 62 platform
                         totals, Task 63 per-seller breakdown) real —
                         admin is fully built, other sub-paths still
                         placeholder) — real views land per
                         PROJECT_ROADMAP.md's Phase 5
      index.css          imports styles/tokens.css; shared .card/.btn-primary,
                         .auth-form (Task 55, reused as-is for
                         AdminSettings's and AdminSettlements' forms in
                         Tasks 60-61), .seller-dashboard/
                         .seller-product-list (Task 56),
                         .admin-dashboard/.admin-table (Task 59, reused
                         as-is for the settlements table in Task 61
                         and the per-seller reports table in Task 63),
                         .earnings-summary (Task 57, reused as-is for
                         AdminReports' platform totals in Task 62);
                         Task 67 mobile-responsive sweep added a global
                         `code { overflow-wrap: anywhere }` rule (a
                         32-char id in a bare <code>, e.g. BuyNow.tsx's
                         receipt-id confirmation, could otherwise
                         overflow a narrow phone width) and widened
                         `.btn-primary`'s padding toward a ~44px touch
                         target; Task 69 added `.form-success` (green,
                         mirrors `.form-error`) and `.btn-text` (a
                         button reset to read as an inline link, for
                         "Resend code"/"Start over" actions inside a
                         form); Task 70 removed `.nav-link` (no longer
                         referenced — its header disappeared with
                         Layout.tsx's rewrite) and added the
                         `.app-shell`/`.app-content`/`.sidebar*`/
                         `.mobile-topbar*`/`.sidebar-backdrop` rules
                         for the sidebar nav (breakpoint `max-width:
                         767px`)
      styles/
        tokens.css       design tokens — blood-red brand palette (Task
                         50) for buttons/prices/links; Task 70 added a
                         separate cream-white `--color-sidebar-*` set
                         + `--sidebar-width` used only by the sidebar
      components/
        Layout.tsx       app shell: <Sidebar/> + mobile-only top bar
                         (hamburger + wordmark) + <Outlet/>, used by
                         every route; owns the mobile-nav-open boolean
                         state and the click-to-close backdrop (Task
                         70 — replaces the Task 55/66/67 brand-red
                         header + Seller/Admin nav-link row)
        Sidebar.tsx      nav content: logo/link, Home/Seller/Admin
                         links via react-router-dom's NavLink (active-
                         link styling built in), close button (CSS-
                         hidden on desktop); persistent (`position:
                         sticky`) on desktop, off-canvas overlay
                         (`position: fixed` + `transform`) on mobile
                         (Task 70)
      pages/
        BuyerHome.tsx        real buyer grid (Task 51)
        ProductDetail.tsx    real details view + Buy Now link (Task 52)
        BuyNow.tsx           payment info + receipt submission (Task 53)
        ReceiptStatus.tsx    verify (idempotent) + delivery link (Task 54)
        SellerHome.tsx       `/seller` index — logged out: login/register
                             links (Task 55); logged in: the add/list-
                             products dashboard (Task 56) — add-product
                             form (POST /products) + own product list
                             (GET /products/mine), both sending the
                             session token, both clearing the session
                             and redirecting to /seller/login on 401/403
        SellerLogin.tsx      `/seller/login` (Task 55)
        SellerRegister.tsx   `/seller/register` — registers then chains into
                             login so the seller only fills one form (Task 55);
                             Task 69 changed the post-login redirect from
                             `/seller` to `/seller/verify-email` (passing the
                             registered email via router state)
        VerifyEmail.tsx       `/seller/verify-email` — OTP-entry screen for
                             Task 68's signup verification (POST
                             /sellers/verify-email, .../resend), reached
                             from SellerRegister.tsx or directly; not a
                             hard gate — offers "Skip for now" to /seller,
                             since login itself doesn't require
                             email_verified (Task 68's scope decision)
                             (Task 69)
        ForgotPassword.tsx    `/seller/forgot-password` — two-step
                             password reset in one page (request code,
                             then code + new password) against Task 68's
                             POST /sellers/password-reset/request and
                             .../confirm; on success, navigates to
                             /seller/login (that endpoint returns no
                             session token, so there's nothing to
                             auto-log-in with) (Task 69)
        SellerPayments.tsx   `/seller/payment-methods` — payout account
                             (GET/PUT /sellers/payment-methods) + read-only
                             earnings summary (GET /sellers/earnings) on one
                             page (Task 57); seller side of Phase 5 is done
                             as of this task
        AdminLogin.tsx       `/admin-portal/login` (Task 58) — same form/
                             session/redirect pattern as SellerLogin.tsx,
                             against the separate admin identity (one
                             Master Admin, env-provisioned, no register
                             link) and its own session module
        AdminHome.tsx        `/admin-portal` index — platform-wide products
                             overview (GET /admin/products) in a table,
                             logged-in email + logout + links to
                             Settings, Settlements, and Reports (Task 59,
                             links added Tasks 60-62; Reports itself
                             links on to the per-seller breakdown,
                             Task 63); redirects to
                             /admin-portal/login if there's no session,
                             or if a 401/403 comes back (expired token)
        AdminSettings.tsx    `/admin-portal/settings` — NATRA's own CBE/
                             Telebirr payment account (what buyers pay
                             into) + commission_rate, one combined form
                             (GET/PUT /admin/settings, Task 60); same
                             "always send all four payment fields, blank
                             = clear" convention as SellerPayments.tsx,
                             plus a bounded 0-100 number input for
                             commission_rate (never cleared — NOT NULL
                             column, always sent as a number)
        AdminSettlements.tsx `/admin-portal/settlements` — record a
                             settlement to a seller (POST
                             /admin/settlements), list every settlement
                             platform-wide (GET /admin/settlements), and
                             mark one completed (POST
                             /admin/settlements/{id}/complete) once the
                             admin has actually paid the seller outside
                             this system (Task 61). No seller-picker —
                             NATRA has no "list sellers" endpoint yet,
                             so the admin pastes the seller ID shown in
                             AdminHome's products table; the backend
                             itself 404s an unknown seller and 422s an
                             amount exceeding the unsettled balance
                             (Task 42), surfaced as-is
        AdminReports.tsx     `/admin-portal/reports` — platform-wide
                             financial totals (GET /admin/reports, Task
                             62): the same six fields as
                             SellerPayments.tsx's earnings summary, just
                             summed across every seller instead of one —
                             reuses the .earnings-summary card grid
                             as-is. Links on to the per-seller breakdown
                             at /admin-portal/reports/by-seller (Task 63)
        AdminReportsBySeller.tsx `/admin-portal/reports/by-seller` — the
                             per-seller breakdown (GET
                             /admin/reports/by-seller, Task 63) left out
                             of AdminReports.tsx: same six fields, one
                             row per seller instead of a single
                             platform-wide row, in the .admin-table
                             style (same as AdminHome's products table)
                             — already sorted by the backend
                             (unsettled_total descending), no
                             client-side sort
        RolePlaceholder.tsx  shared stub for whatever's not built yet — now
                             just genuinely unmatched seller/* and
                             admin-portal/* paths (shows a plain "not
                             found", `roleOtherwiseBuilt`); both seller
                             (Tasks 55-57) and admin (Tasks 58-63) are
                             now fully built
      api/
        client.ts        apiFetch<T>() — shared fetch wrapper, ApiError
        products.ts      getProducts(), getProductDetail() (buyer-facing);
                         createProduct(), getMyProducts() (seller-facing,
                         token-authenticated, Task 56)
        receipts.ts      getPaymentInfo(), submitReceipt(), verifyReceipt(),
                         getReceiptDelivery(), describeRejectionReason()
        sellers.ts       registerSeller(), loginSeller() (Task 55);
                         getPaymentMethods(), updatePaymentMethods(),
                         getEarnings() (Task 57); verifyEmail(),
                         resendVerificationEmail(), requestPasswordReset(),
                         confirmPasswordReset() (Task 69, wrapping Task
                         68's four backend endpoints — untyped beyond the
                         one field each caller branches on, same as the
                         backend's own minimal response shapes)
        admin.ts         loginAdmin() (Task 58); getAdminProducts() (Task 59);
                         getAdminSettings(), updateAdminSettings() (Task 60);
                         createSettlement(), getSettlements(),
                         completeSettlement() (Task 61);
                         getAdminReports() (Task 62);
                         getAdminReportsBySeller() (Task 63)
      lib/
        format.ts        formatPrice() (hardcoded ETB)
        session.ts       seller session in localStorage — save/get/clear
                         (Task 55); email stored is display-only, from the
                         form, not decoded from the JWT
        adminSession.ts  admin session in localStorage, own storage key —
                         save/get/clear (Task 58); deliberately separate
                         from session.ts so a leftover seller/admin
                         session in the same browser can't bleed into
                         the other role's pages
      vite-env.d.ts
  CLAUDE_MASTER_PROMPT.md
  PROJECT_ROADMAP.md
  CURRENT_STATUS.md
  ARCHITECTURE.md
  DATABASE_SCHEMA.md
  SETUP.md
```

## Fixed Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React + TypeScript + Vite |
| Backend | Python + FastAPI |
| Database | Oracle Autonomous Database (via `oracledb` driver) |
| Object Storage | Oracle Object Storage (thumbnails, seller profile pictures) |
| Receipt Verification (Phase 2) | Python + Playwright |
| Authentication | FastAPI, JWT/session-based |
| Styling | CSS or Tailwind CSS |
| Production Server | Nginx + Uvicorn + FastAPI + React build, on Oracle Cloud Free Tier VM |
| Source Control | Git + GitHub |

These are fixed unless the project owner explicitly changes them.

## Important Technical Decisions

- **Buyers have no accounts.** No email/phone/password/cart for buyers, by design.
- **Buyers pay NATRA, not sellers.** The CBE/Telebirr accounts shown to buyers
  belong to NATRA (Master Admin), not individual sellers. Seller payment
  details are only used for later settlements and are never shown to buyers.
- **Digital products stay on the seller's own Google Drive.** NATRA stores only
  the seller-provided public Drive delivery link. NATRA never requests Google
  OAuth, Drive API access, or the seller's Google password.
- **Images go to Oracle Object Storage, not the database.** Product thumbnails
  and seller profile pictures are stored as objects; the database stores only
  references/URLs to them.
- **Payment receipt verification is deferred to Phase 2.** In Phase 1, a buyer's
  receipt URL is only collected/stored, not verified.
- **Duplicate payment protection (Phase 2) will key off the transaction/reference
  number extracted from the receipt — never the payer's name.**
- **Passwords are hashed with PBKDF2-HMAC-SHA256 from Python's stdlib
  `hashlib`** (260,000 iterations, random salt per password), not bcrypt/
  passlib — avoids an extra dependency while still meeting the "never store
  plain-text passwords" / secure hashing requirement.
- **Protected endpoints trust the JWT, never the request body, for
  ownership.** `POST /products` takes `seller_id` from the verified token's
  `sub` claim, not from anything the client sends — a seller can only ever
  create products for themselves.
- **`products.thumbnail_ref` exists but is unused for now.** The column is
  in the schema so Task 8 doesn't need a migration later, but no upload
  endpoint or Object Storage integration exists yet — that's a separate
  future task.
- **The public buyer grid (`GET /products`) never returns `drive_link` or
  `seller_id`.** The digital delivery link stays hidden until a purchase is
  verified (Phase 2+); buyers never need to know which seller owns which
  product to browse or buy. The same rule applies to
  `GET /products/{product_id}` (product details) — it adds `description`
  over the grid, but still never `drive_link` or `seller_id`.
- **Route order matters:** `GET /products/mine` is declared before
  `GET /products/{product_id}` so a request for `/products/mine` is never
  swallowed by the `{product_id}` path parameter. `get_product_detail`
  also validates that `product_id` looks like a 32-char hex id before
  querying, so a malformed id (or `/products/mine` reaching it in some
  future reordering) 404s cleanly instead of raising an Oracle error.
- **`admin_settings` is a singleton table (`id` fixed to 1, `CHECK (id =
  1)`).** NATRA has exactly one CBE account and one Telebirr account; a
  dedicated single-row table is simpler than a generic key/value settings
  table for two fixed fields. `init_db.py` seeds the row (all fields
  `NULL`) if missing, so `GET /payment-info` always has a row to read even
  before an admin has configured anything. `PUT /admin/settings` (Task 16)
  is the write counterpart.
- **`PUT /admin/settings` treats an omitted/null field as "leave
  unchanged", not "clear it".** Each of the four fields
  (`cbe_account_name`, `cbe_account_number`, `telebirr_account_name`,
  `telebirr_account_number`) is independently optional in the request
  body, and the endpoint builds its `UPDATE` with only the columns that
  were actually provided. This lets the admin set the CBE info in one
  call and add Telebirr later without resending everything, and matches
  how a simple settings form naturally submits (only the fields the admin
  touched). To deliberately clear a field once set, the admin sends an
  empty string `""` — that's a real value, distinct from omission, and is
  stored as-is (an empty string reads the same as "not configured" to a
  buyer via `GET /payment-info`).
- **`POST /products/{product_id}/receipt` only stores; it never verifies.**
  Per `CLAUDE_MASTER_PROMPT.md` sections 5 and 9, receipt verification is
  explicitly Phase 2. This endpoint's entire job in Phase 1 is: confirm the
  `product_id` refers to a real product, confirm `receipt_url` looks like a
  URL, insert a `receipts` row, return it. No amount/status checks, no
  reference-number extraction, no duplicate detection, and no order/sale
  row are created here. Multiple receipts per product are allowed at this
  stage (e.g. a buyer corrects a mistyped link) — there's no uniqueness
  constraint on `receipts` yet, and there shouldn't be until Phase 2 defines
  what the real duplicate key is (the provider's transaction/reference
  number, extracted during verification — never the payer's name, and
  never this table's own `id`).
- **There is exactly one Master Admin identity, and it is not a database
  row.** Unlike sellers (many, self-registering, one row each in
  `sellers`), NATRA has a single admin. Building an `admins` table plus a
  registration endpoint for a account count of exactly one would be
  unnecessary abstraction (Rule: avoid over-engineering). Instead, the
  admin's email and a password *hash* (produced by
  `security.hash_password()`, same PBKDF2 scheme as sellers — never a
  plain-text password) are provisioned via the `ADMIN_EMAIL` /
  `ADMIN_PASSWORD_HASH` environment variables. `POST /admin/login` checks
  submitted credentials against those two values and, on success, issues a
  JWT via `create_admin_access_token()`. If this ever needs to become
  multiple admins with different permissions, that's a deliberate future
  migration to a real `admins` table — not something to build speculatively
  now.
- **Seller and admin JWTs both carry a `role` claim** (`"seller"` or
  `"admin"`), added in Task 14 so a protected endpoint can require one
  role or the other. The admin token's `sub` is the fixed string
  `"admin"` (there's no admin id to put there); a seller token's `sub`
  remains the seller's actual id, unchanged from Task 7. Task 15's
  `get_current_admin` is the first dependency to actually check this
  claim — see below.
- **`POST /admin/login`'s error handling avoids a timing side-channel and
  enumeration.** It always calls `verify_password()` — even when the
  submitted email doesn't match `ADMIN_EMAIL`, and even when the admin
  account isn't configured at all in `.env` — so a wrong email can't be
  distinguished from a wrong password by response time, and the same
  generic `401 Invalid email or password` covers every failure case
  (mirrors `POST /sellers/login`'s existing anti-enumeration behavior).
- **`get_current_admin` and `get_current_seller_id` both check the `role`
  claim.** Task 15 added the first role check anywhere in the codebase,
  on `get_current_admin`: a valid seller token hitting an admin-only
  endpoint gets a clean `403 Admin access required` (authenticated, wrong
  role) rather than the `401` used for "no/invalid token". That was
  intentionally one-directional at the time — `get_current_seller_id`
  (Task 8) only checked that a token decoded and had a `sub` claim, so an
  admin token would pass it, harmlessly, since `sub="admin"` never matches
  a real `seller_id` (e.g. `GET /products/mine` with an admin token just
  returned an empty list, not another seller's data). Task 41 closes that
  gap for real rather than relying on the accidental `sub` mismatch:
  `get_current_seller_id` now also rejects a non-`"seller"`-role token
  with `403 Seller access required`, so both dependencies are symmetric.
- **`GET /admin/products` intentionally exposes `seller_id` and
  `drive_link`, unlike the buyer-facing `GET /products`.** The Master
  Admin has full platform control (`CLAUDE_MASTER_PROMPT.md` §3) and needs
  to know which seller owns which product; buyers must never see either
  field before a verified purchase. This is a read-only listing — editing,
  deleting, or publishing/unpublishing products from the admin side is a
  later task, not part of Task 15.
- **`PUT /admin/settings` reuses `PaymentInfoResponse` as its response
  model**, the same shape `GET /payment-info` already returns. There's no
  reason for the write endpoint's response to look different from the
  read endpoint's — a caller can use either to display current state, and
  keeping one model avoids a near-duplicate.
- **`receipts`'s Task 19 verification columns were added via migration
  (`ALTER TABLE ... ADD`, one column at a time, each guarded by a
  `user_tab_columns` existence check) rather than by editing Task 13's
  original `CREATE TABLE` statement.** `init_db.py`'s `apply_schema()`
  only ever *creates* a table if it's missing — it never diffs an
  existing table's columns against the DDL constant. Without a separate
  migration step, any database that already ran Task 13 (before these
  columns existed) would never receive them. `backend/db/schema.sql`
  still shows the final combined shape as one `CREATE TABLE`, since it's
  a human-readable reference for a *fresh* install, not the literal
  sequence of statements a long-lived database goes through — that
  sequence lives in `init_db.py`. Column-by-column (not one multi-column
  `ALTER`) so a migration that fails partway through still converges
  cleanly on re-run.
- **All four new `receipts` columns are nullable, with no default
  status.** A receipt starts with none of them set — exactly the same
  state as every receipt already in the table before Task 19 — since no
  verification logic exists yet to populate them (that begins at
  Task 20/22). `status` and `provider` get `CHECK` constraints
  constraining them to a small known set of values (`'pending' |
  'verified' | 'rejected'` and `'cbe' | 'telebirr'` respectively) or
  `NULL`, decided now since the possible values are already fixed by
  `PROJECT_ROADMAP.md`'s Phase 2 scope — there's no ambiguity later
  tasks would need to resolve. No uniqueness constraint on
  `transaction_ref` yet; that enforcement is explicitly Task 25's job
  (duplicate-payment protection), once real extracted values exist to
  reason about.
- **`GET /health/playwright` mirrors `GET /health/db`'s shape and
  purpose, one phase later.** Task 4 proved Oracle connectivity in
  isolation before any table/query existed; Task 18 does the same for
  Playwright before any receipt-fetching logic exists. `check_browser()`
  in `browser.py` never raises — like `check_connection()`, it launches a
  headless Chromium, loads `about:blank`, and closes it, returning
  `{"browser_ready": True}` on success or `{"browser_ready": False,
  "error": "..."}` on failure, so a broken browser install degrades to a
  clear diagnostic response instead of a 500. Unlike the Oracle
  connection, this one *is* fully verifiable in a typical dev/CI sandbox
  with no external service required — Chromium runs locally once
  installed via `playwright install chromium`.
- **`cbe.py` validates the receipt URL's host with `urlparse(...).hostname`
  equality, not a substring/`endswith` check.** A naive check like `"mbreciept.cbe.com.et"
  in url` or `url.endswith(...)` would accept attacker-controlled lookalikes
  such as `https://mbreciept.cbe.com.et.evil.com/...` (a subdomain of
  `evil.com`) or `https://evil.com/mbreciept.cbe.com.et` (the string
  appears in the path, not the host). Exact hostname equality after
  parsing closes both. Rejection happens before any network/browser
  activity — a bad URL never reaches Playwright at all.
- **`cbe.py` splits pure URL validation (`_validate_cbe_url`) from the
  actual page load (`_load_page`).** The former needs no network or
  browser and is fully unit-testable in any environment; the latter is
  host-agnostic on purpose so Task 22's Telebirr fetcher can reuse it
  as-is rather than duplicating the Playwright launch/navigate/capture
  logic — only the URL-validation function differs per provider.
- **Fetching never distinguishes "URL failed validation" from "browser/
  network failure"** in its return shape — both come back as
  `{"fetched": False, "error": "..."}`. The caller (Task 26's
  verification endpoint) only needs to know "verification can't proceed
  from this receipt," not which of several fetch-time failure reasons
  caused it; the `error` string still carries the specific reason for
  logging/debugging.
- **`extract_cbe_data()`'s patterns are evidence-based but unconfirmed
  against a real live CBE receipt page** (this sandbox cannot reach
  `mbreciept.cbe.com.et` — see `CURRENT_STATUS.md`). The field labels
  used ("Payer", "Receiver", "Reference No. (VAT Invoice No)",
  "Transferred Amount", "Total amount debited from customers account")
  and the observation that CBE reference numbers are consistently 12
  characters (e.g. `FT25057C5FS8`) come from many independently
  published CBE mobile-banking receipts showing the same structure — a
  factual, structural observation about the page layout, not content
  copied from any one of them. `found` (used by later tasks to decide
  whether verification can proceed at all) requires *both* a transaction
  reference *and* a transferred amount to be present — the two fields
  duplicate-payment protection (Task 25) and amount validation (Task 24)
  actually need — rather than treating any single extracted field as
  sufficient.
- **The reference-number regex matches an exact 12-character length
  first, falling back to a looser whitespace-bounded pattern only when
  there's an unambiguous boundary after the value.** Extracting a label's
  value from plain visible text (no HTML tags to lean on) means there's
  no reliable delimiter between one field's value and the next label
  when they run together with no separating whitespace — a real risk
  since `page.inner_text()` doesn't guarantee whitespace where a webpage
  visually implies a line break. Anchoring to the known-consistent
  12-character length avoids a greedy match silently absorbing the first
  character(s) of "Reason" (or another label) into what should have been
  the transaction reference. The fallback pattern only fires when a
  whitespace/end-of-string boundary already resolves the ambiguity, so it
  never reintroduces the run-together problem the primary pattern exists
  to avoid.
- **Task 39: required environment variables are validated once, at app
  startup, not lazily per request.** `ORACLE_USER`/`ORACLE_PASSWORD`/
  `ORACLE_DSN` and `JWT_SECRET_KEY` are things the app cannot function
  without at all (no DB, no auth) — a new `@app.on_event("startup")`
  handler now raises `StartupConfigError` and refuses to start if any
  is missing, rather than letting the app come up and 500 on whichever
  request happens to need one first. Deliberately scoped to only those
  four: `ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH` are excluded from the fatal
  check (only logged as a warning) since `POST /admin/login` already
  degrades to its normal generic 401 without them, and every
  buyer/seller flow keeps working regardless. The check runs on actual
  app startup only (e.g. under Uvicorn) — importing `app.main` for
  tooling or tests never triggers it.
- **Task 40: CORS is explicit-allowlist, not default-open.** Before
  this task there was no `CORSMiddleware` at all, which in practice
  meant every cross-origin browser request was blocked (no CORS
  headers ever sent) — including the real frontend's, once it exists.
  `CORS_ALLOWED_ORIGINS` (comma-separated exact origins) now drives
  `CORSMiddleware`'s `allow_origins`; unset/empty parses to `[]`, the
  same zero-origins-allowed behavior as before, never a `["*"]`
  fallback. `allow_credentials=False` throughout, since auth is a
  Bearer token in the `Authorization` header, never a cookie — this
  app has no reason to enable the credentialed-CORS mode that would
  also forbid a literal `"*"` origin.
- **Task 41: `get_current_seller_id` now checks `role`, mirroring
  `get_current_admin`.** Closes the one-directional gap Task 15 left
  open — an admin token reaching a seller-only endpoint now gets a
  clean `403 Seller access required` instead of relying on `sub="admin"`
  never matching a real `seller_id` to stay harmless by accident.
- **Task 42: `POST /admin/settlements` validates `amount` against the
  seller's unsettled balance.** Computes `seller_payable_total -
  settled_total` (`'completed'`-only, same formula `GET
  /sellers/earnings` reports as `unsettled_total`) before inserting, and
  rejects with `422` any amount that would drive it negative. Only
  weighs already-`'completed'` settlements — see `DATABASE_SCHEMA.md`
  for the narrower, still-open edge case around simultaneous `'pending'`
  settlements.
- **Task 43: a single `@app.exception_handler(Exception)` catches
  everything an endpoint doesn't handle itself.** Before this, an
  uncaught exception (e.g. an `oracledb.Error` from a query nothing
  wrapped in try/except) fell through to Starlette's bare default
  handler — plain-text `"Internal Server Error"`, not this API's usual
  `{"detail": "..."}` JSON, with no guarantee against leaking the
  underlying exception's message. The new handler always logs the real
  exception with a full traceback server-side (`logger.error(...,
  exc_info=exc)`) and always returns the same generic
  `{"detail": "Internal server error"}` JSON with status 500 to the
  client. Every existing `HTTPException` raise, and FastAPI's own
  `RequestValidationError` (422) handling, are both unaffected — this
  only catches what would otherwise be genuinely unhandled.
- **Task 44: `POST /sellers/login` and `POST /admin/login` are rate-
  limited, in-memory, per client IP.** A new `rate_limit.py` module
  tracks up to 5 attempts per rolling 60-second window per
  `"{endpoint_prefix}:{ip}"` key; a 6th attempt within the window gets
  `429 Too many login attempts. Please try again later.` with a
  `Retry-After` header. Deliberately in-process (no Redis/external
  store) to match the current single-Uvicorn-process deployment target
  (Task 46) — counters reset on restart, an accepted trade-off for a
  brute-force *slowdown*, not a durability guarantee. Deliberately
  keyed by IP, not by the submitted email, so an attacker can't lock a
  legitimate account out of its own login by repeatedly submitting that
  account's email from anywhere. Seller and admin login keep fully
  independent counters (different key prefix) so exhausting one doesn't
  affect the other. Behind Task 46's planned Nginx reverse proxy,
  `request.client.host` will see Nginx's address for every request
  unless Nginx is configured to forward the real client IP and
  `_rate_limit_key()` is updated to read it — intentionally deferred to
  Task 46, where the actual proxy config is decided and tested together.
- **Task 45: four plain (non-unique) indexes, added by reviewing every
  query in `main.py`/`duplicate_check.py` for a real, unindexed filter
  — not by indexing every foreign key on principle.** `products.seller_id`,
  `sales.seller_id`, and `settlements.seller_id` each back a live
  `WHERE seller_id = ...` read (a seller's own product list; `GET
  /sellers/earnings`; the Task 42 settlement balance check); Oracle
  does not create an index for a foreign-key column automatically
  (only for a primary/unique key), so each was a full-table scan.
  `idx_receipts_txn_provider` on `(transaction_ref, provider)` backs
  `duplicate_check.py`'s `is_duplicate_transaction()`, which filters on
  those two plain columns plus `status = 'verified'` — a different
  expression shape from Task 25's `uq_receipts_verified_txn`, a
  function-based unique index over `CASE WHEN status = 'verified' THEN
  ... END` expressions that Oracle will only match against a query
  using that same expression, so it didn't serve this lookup even
  though both indexes touch the same two columns. Deliberately did NOT
  add an index on `receipts.product_id`, which has the identical
  unindexed-FK shape: no query in the codebase actually filters
  `receipts` by `product_id` (every lookup goes through the primary
  key, `id`), so an index there would have no query to serve. All four
  added via the same idempotent `_create_index_if_missing` /
  `user_indexes` pattern Task 25 already established — no new tables,
  columns, or endpoints; `main.py` is otherwise untouched by this task.
- **Task 46: production deployment skeleton — systemd unit, Nginx
  config, and a `.env.production` template — with no backend code
  changes.** `deploy/systemd/natra-backend.service` runs the backend
  as `uvicorn app.main:app --host 127.0.0.1 --port 8000
  --proxy-headers`, explicitly never with multiple workers (see that
  file's own comment: Task 44's rate limiter is in-memory and
  single-process by design, and multiple workers would silently give
  an attacker N attempts per process instead of N total).
  `deploy/nginx/natra.conf` reverse-proxies everything to that Uvicorn
  process over loopback and sets `X-Forwarded-For`/
  `X-Forwarded-Proto`. Together, `--proxy-headers` (trusting
  `127.0.0.1`, its default) and Nginx setting those headers resolve
  Task 44's flagged gap — `_rate_limit_key()` reading
  `request.client.host`, which would otherwise always be Nginx's own
  address — purely through this infrastructure configuration; Starlette
  itself rewrites `request.client` from the forwarded header when the
  request originates at a trusted address, so `_rate_limit_key()`
  needed no code change. The Nginx config deliberately proxies
  *everything* rather than trying to split "static frontend" vs.
  "backend API" traffic: no frontend build exists yet (Task 47), and
  every current backend route lives at the bare root
  (`/sellers/login`, `/products`, etc., no `/api` prefix) — deciding
  how a future SPA's own root-level routes coexist with those is
  explicitly left to Task 47, once the frontend's actual routes are
  known, rather than guessed at here (see the Nginx config's own
  comment). The tracked environment template is named
  `backend/.env.production.example`, not `backend/.env.production` —
  mirroring `backend/.env.example`'s convention — so the file that
  will eventually hold real production secrets is never the one this
  task commits. Also added a root `.gitignore` (none existed before
  this task, despite `SETUP.md` referring to "gitignored" secrets
  since Task 4), covering `.env`/`.env.production`/wallet directories/
  build artifacts.
- **Task 47: React production build + static serving integration —
  resolves Task 46's flagged frontend/backend routing question, with
  no backend code changes.** `frontend/src/App.tsx` is still exactly
  Task 3's placeholder — no React Router, no client-side routes of
  its own (see `PROJECT_ROADMAP.md`'s "UI/UX polish — deliberately
  not yet numbered" note, still open) — so there was no real frontend
  route to collide with a backend one. `deploy/nginx/natra.conf` now
  proxies the backend's existing path prefixes explicitly
  (`/health`, `/sellers/`, `/products`, `/payment-info`, `/receipts/`,
  `/admin/`, matched via a single regex `location` block) and serves
  `frontend/dist/` (Vite's default `build.outDir`, unchanged in
  `frontend/vite.config.ts`) for everything else, with a `try_files
  ... /index.html` fallback so a future client-side router still
  works without a matching Nginx rule per route. No `/api` prefix was
  introduced. This sandbox has no network access this session (same
  as the general limitation noted under Task 46) and could not run
  `npm install`/`npm run build` or install `nginx` to verify with
  `nginx -t`; verification was manual review — brace-balance check on
  the config, and confirming `frontend/package.json`'s `build` script
  (`tsc -b && vite build`) and `tsconfig.app.json`'s strict settings
  don't flag anything in the current placeholder `App.tsx`/`main.tsx`.

## Data Flow (target, once Phase 1+2 are complete)

1. Seller registers/logs in → adds a product (name, price, description,
   thumbnail → Object Storage, public Drive link) → product stored in
   Oracle Autonomous Database.
2. Buyer browses the product grid (public, no auth) → opens product detail →
   clicks Buy Now → sees NATRA's CBE/Telebirr payment info → pays NATRA
   directly → pastes receipt URL, which is stored via
   `POST /products/{product_id}/receipt` (Task 13 — storage only).
3. (Phase 2) Backend verifies the stored receipt via Playwright, checks
   amount/status/duplicate transaction ID, then reveals the seller's Drive
   link to the buyer.
4. (Phase 3) Backend records commission and seller payable balance; admin
   later settles the seller manually and marks it complete.

## Storage Architecture

- **Oracle Autonomous Database**: sellers, products, admin payment settings,
  and (later) orders/receipts/settlements — all structured data.
- **Oracle Object Storage**: product thumbnail images, seller profile pictures.
- **Seller's own Google Drive**: the actual digital product files (NATRA never
  hosts these).

## Status

This file will be updated as each task introduces new architecture (schema
created, backend/frontend integration, etc.). See `CURRENT_STATUS.md` for
the most recent change.
