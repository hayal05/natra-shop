# Backend tests

Task 72. Automated tests for the seller email-verification flow
(Task 68) and the login gate on top of it (Task 71).

Task 73. Extends the suite with the Products endpoints (`POST
/products`, `GET /products/mine`, `GET /products`,
`GET /products/{id}`, `GET /payment-info`) — see
`test_products.py`.

Task 74. Extends the suite with seller earnings and seller payment
methods (`GET /sellers/earnings`, `GET`/`PUT /sellers/payment-methods`)
— see `test_seller_earnings_and_payment_methods.py`.

Task 75. Extends the suite with the receipts flow (`POST
/products/{product_id}/receipt`, `POST /receipts/{id}/verify`,
`GET /receipts/{id}/delivery`) — see `test_receipts.py`.

Task 76. Extends the suite with admin auth + catalog (`POST
/admin/login`, `GET /admin/products`, `GET`/`PUT /admin/settings`) —
see `test_admin_auth_and_catalog.py`.

Task 77. Extends the suite with admin settlements + reports (`POST`/
`GET /admin/settlements`, `POST /admin/settlements/{id}/complete`,
`GET /admin/reports`, `GET /admin/reports/by-seller`) — see
`test_admin_settlements_and_reports.py`.

Task 78. Extends the suite with the cross-cutting backend surface —
`/health*` endpoints, the Task 43 generic-500 handler, Task 39's
startup config validation, and Task 40's CORS origin parsing — see
`test_health_and_startup.py`. Sixth and final item in Phase 7's
backend schedule.

## Running

```
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

As of Task 78, the full suite (Tasks 72-78) has been run in a sandbox
with `pip install` access (a fresh virtualenv sidesteps the
`PyJWT`/debian-package uninstall conflict noted since Task 72) — all
154 tests pass. See `CURRENT_STATUS.md` for the run details.

With coverage:

```
pytest --cov=app.main --cov=app.otp --cov-report=term-missing
```

## How this runs without a real Oracle DB or Brevo account

There's no Oracle Autonomous DB instance available in a sandbox/CI
environment, so the suite doesn't try to spin one up. Instead
(`conftest.py`, `fake_oracle.py`):

- `db.get_connection` is swapped for an in-memory fake that recognizes
  the specific queries `app/main.py`, `app/otp.py`, and
  `app/duplicate_check.py` issue against
  `sellers`/`otp_codes`/`products`/`admin_settings`/`sales`/`receipts`
  and answers them the way Oracle would for those exact statements
  (unique-email conflicts raise `oracledb.IntegrityError`,
  `RAWTOHEX`/`HEXTORAW` are simulated as plain hex strings, etc).
  Everything *around* those queries — routing, request validation,
  password hashing (`security.py`), OTP hashing/expiry/attempt-counting
  (`otp.py`), JWT issuance (`auth.py`), rate limiting (`rate_limit.py`),
  payment validation (`validation.py`) — is the real, unmodified code.
- The two Brevo-sending calls in `main.py`
  (`send_signup_otp_email`/`send_password_reset_otp_email`) are
  swapped for fakes that record `(email, code)` instead of calling
  Brevo's API, via the `sent_emails` fixture — this is also the only
  way a test can recover a plaintext OTP code, since codes are hashed
  at rest.
- **Task 75**: `app.main.parse_cbe_receipt`/`parse_telebirr_receipt`
  (the two functions that actually drive Playwright) are monkeypatched
  per-test to return a canned extraction dict — see
  `test_receipts.py`'s `_patch_cbe`/`_patch_telebirr` helpers. No
  fake for `browser.py`/`cbe.py`/`telebirr.py` was needed: `main.py`
  imports these two functions by name, so patching them on `app.main`
  is enough to keep the rest of the pipeline (provider detection,
  `validate_payment()`, `is_duplicate_transaction()`, `_record_sale()`)
  real while never touching an actual browser or network call.
- **Task 76**: `POST /admin/login` doesn't touch the database at all
  (the Master Admin is provisioned entirely via `ADMIN_EMAIL`/
  `ADMIN_PASSWORD_HASH` env vars — see that endpoint's docstring), so
  its tests set/unset those two vars directly with `monkeypatch`
  rather than seeding anything in `fake_oracle.py`. `GET /admin/products`
  and `GET`/`PUT /admin/settings` reuse the existing `admin_settings`
  fake (extended with an `UPDATE admin_settings SET ...` branch and the
  5-column select `_fetch_admin_settings_row()` needs, both new in this
  task) and the existing `products` store.
- **Task 77**: `SettlementRow` gains a real `id_hex`/`created_at`/
  `completed_at` (defaulted, so Task 74's direct-seed
  `SettlementRow(seller_id_hex=..., amount=..., status=...)` calls
  keep working) now that `POST /admin/settlements` performs a real
  `INSERT` and `GET /admin/settlements` / `POST .../complete` return
  a real id and timestamps. New query shapes: a seller-existence check
  against `sellers` by id, a single-column `SUM(seller_payable)`
  against `sales` for one seller (the Task 42 over-payment guard —
  distinct from `GET /sellers/earnings`' 4-column aggregate), and
  platform-wide / `GROUP BY seller_id` versions of both the `sales`
  and `settlements` aggregates for `GET /admin/reports` and
  `GET /admin/reports/by-seller`.

- **Task 78**: `/health*`, the generic-500 handler, startup config
  validation, and CORS origin parsing don't touch
  `sellers`/`otp_codes`/`products`/`admin_settings`/`sales`/
  `settlements`/`receipts` at all, so `fake_oracle.py` itself is
  untouched by this task. `GET /health/db`/`GET /health/playwright`
  monkeypatch `app.main.check_connection`/`check_browser` directly
  (the same imported-by-name pattern Task 75 already uses for
  `parse_cbe_receipt`/`parse_telebirr_receipt`), so a real Oracle
  connection or headless-browser launch is never attempted. Startup
  validation and CORS parsing both run once — on FastAPI's "startup"
  event or at module-import time — rather than per-request, so those
  tests build their own fresh `TestClient(main.app)` (optionally after
  `importlib.reload(app.main)` for the CORS cases) instead of reusing
  the shared `client` fixture; see `test_health_and_startup.py`'s own
  module docstring for why.

If a future task adds a new query against these tables that this fake
doesn't recognize yet, tests exercising it will fail loudly
(`NotImplementedError` from `fake_oracle.py`) rather than silently
passing without having actually run that code path — add a branch to
`FakeCursor.execute()` for it. Query matching is by distinctive
substring, not a SQL parser, so a new branch should be specific enough
not to also swallow a different query against the same table — see the
comment on the `admin_settings` branch for why (`_get_commission_rate()`
and `_fetch_admin_settings_row()` both query that table with different
column lists than `GET /payment-info`).

## Scope

- **Task 72** — the seller auth/verification surface
  (`/sellers/register`, `/sellers/login`, `/sellers/verify-email`
  (+ `/resend`), `/sellers/password-reset/request` (+ `/confirm`)) —
  the area Task 71 changed and the area with the highest cost if it
  silently regresses (an unenforced login gate is exactly the kind of
  bug that doesn't show up until it's already a problem).
- **Task 73** — the Products endpoints (`POST /products`,
  `GET /products/mine`, `GET /products`, `GET /products/{id}`,
  `GET /payment-info`).
- **Task 74** — seller earnings and seller payment methods
  (`GET /sellers/earnings`, `GET`/`PUT /sellers/payment-methods`).
  `sales`/`settlements` rows are seeded directly via
  `store.sales`/`store.settlements` (see `fake_oracle.py`) since no
  in-scope endpoint writes them yet.
- **Task 75** — the receipts flow (`POST
  /products/{product_id}/receipt`, `POST /receipts/{id}/verify`,
  `GET /receipts/{id}/delivery`): submission, every distinct
  `verify` reject reason (`unsupported_provider`, `fetch_failed`,
  `not_found`, `not_completed`, `amount_mismatch`,
  `duplicate_transaction`), the success path for both CBE and
  Telebirr including the `sales` row `_record_sale()` writes,
  idempotency for an already-verified receipt, and delivery's
  verified-only `drive_link` gate.
- **Task 76** — admin auth + catalog (`POST /admin/login`,
  `GET /admin/products`, `GET`/`PUT /admin/settings`): login success/
  wrong-password/wrong-email/unconfigured (all the same generic 401)
  and its own independent rate-limit counter; the products listing's
  admin-only guard, newest-first ordering, and seller_id/drive_link
  inclusion; settings read (including the 10.00 default commission
  rate and the "row missing" degrade path) and write (independent
  optional fields, empty-string clearing a payment field,
  commission_rate's [0, 100] bound and inability to be cleared).
- **Task 77** — admin settlements + reports (`POST`/
  `GET /admin/settlements`, `POST /admin/settlements/{id}/complete`,
  `GET /admin/reports`, `GET /admin/reports/by-seller`): settlement
  creation within/over the unsettled balance (the Task 42 guard,
  including that a 'pending' settlement doesn't reduce the balance but
  a 'completed' one does), 404s for a nonexistent/malformed seller or
  settlement id, platform-wide newest-first listing across every
  seller, idempotent completion, `GET /admin/reports`' all-zero/
  aggregated totals, and `GET /admin/reports/by-seller`'s "only
  sellers with sales appear" / sums-back-to-platform-totals /
  sort-by-unsettled-descending behavior. Admin-only guard (401/403)
  on every endpoint.

- **Task 78** — the cross-cutting backend surface: `GET /health`
  (always-ok liveness); `GET /health/db`/`GET /health/playwright`
  (both the connected/ready and the degraded-but-still-200 cases,
  matching `check_connection()`/`check_browser()`'s own
  never-raises contract); the Task 43 generic-500 handler (an
  unexpected exception gets the fixed, non-leaking
  `{"detail": "Internal server error"}` body and is still logged
  server-side, while an ordinary `HTTPException` is unaffected);
  Task 39's startup validation (missing critical env var(s) raise
  `StartupConfigError` and are named in the message, every critical
  var present starts cleanly, missing recommended vars only warn);
  and Task 40's CORS origin parsing (`_parse_cors_origins()`'s
  parsing rules directly, plus an end-to-end check that a configured
  origin is allowed, an unconfigured one is not, credentials are
  never allowed, and only the configured HTTP methods are granted on
  preflight).

Not yet covered: any of the frontend/E2E work — see
`PROJECT_ROADMAP.md`'s Phase 7 table for the planned follow-ups
(Tasks 79-88).
