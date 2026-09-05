"""
NATRA backend — FastAPI application entry point.

Phase 1, Task 7: adds seller login (POST /sellers/login) on top of Task 6
registration. Issues a JWT on success.

Phase 1, Task 8: adds the first protected endpoint, POST /products
(Seller Add Product), guarded by `get_current_seller_id` which verifies
the seller's JWT from the `Authorization: Bearer <token>` header.

Phase 1, Task 9: adds GET /products/mine (Seller View Products), protected
the same way — returns only the authenticated seller's own products.

Phase 1, Task 10: adds GET /products (Buyer Product Grid) — public, no
auth, all sellers' products, minimal fields (no seller_id/description/
drive_link).

Phase 1, Task 11: adds GET /products/{product_id} (Buyer Product Details)
— public, no auth, fuller per-product info (adds description) but still
never seller_id or drive_link.

Phase 1, Task 12: adds GET /payment-info (Buy Now + NATRA payment
information) — public, no auth, returns NATRA's own CBE/Telebirr account
info from the new admin_settings table. No admin write endpoint yet
(Task 16); the single row is seeded (all-NULL) by init_db.py.

Phase 1, Task 13: adds POST /products/{product_id}/receipt (Receipt URL
submission) — public, no auth. Stores a buyer-submitted receipt URL in
the new `receipts` table. No verification happens here (that's Phase 2)
and no order/sale record is created, since nothing is verified yet.

Phase 1, Task 14: adds POST /admin/login (Admin login). There is exactly
one Master Admin identity, provisioned via the ADMIN_EMAIL/
ADMIN_PASSWORD_HASH environment variables rather than a database table
(see ARCHITECTURE.md) — no admin self-registration exists or is planned.
Issues a JWT with role="admin" on success, the same shape as a seller's
token but distinguishable by its `role` claim for admin-only endpoints
starting Task 15.

Phase 1, Task 15: adds GET /admin/products (Admin product viewing) — the
first endpoint guarded by the new `get_current_admin` dependency, which
requires the JWT's `role` claim to be "admin" (rejecting a valid seller
token with 403). Platform-wide, all sellers' products, with fuller
fields than the buyer-facing GET /products (includes seller_id and
drive_link — appropriate for an admin, never for a buyer pre-purchase).

Phase 1, Task 16: adds PUT /admin/settings (Admin CBE/Telebirr settings)
— the write counterpart to GET /payment-info (Task 12), admin-only via
`get_current_admin`. Updates the singleton `admin_settings` row (id=1)
seeded all-NULL by init_db.py. This is the last task before Phase 1
integration testing (Task 17).

Phase 1, Task 17: Phase 1 integration testing. Testing-only, no code
changes to this file.

Phase 2, Task 18: adds GET /health/playwright — confirms Playwright
browser automation is installed and working (mirrors GET /health/db's
role for the Oracle connection at Task 4). No receipt-fetching/scraping
logic exists yet; that starts at Task 20 (CBE) and Task 22 (Telebirr).

Phase 2, Task 26: adds POST /receipts/{receipt_id}/verify — the first
endpoint that wires Tasks 18-25 together into one pipeline: given a
receipt already submitted via POST /products/{product_id}/receipt
(Task 13), it looks up the product's price, determines the provider
from the receipt URL's hostname, fetches + extracts the receipt
(`cbe.parse_cbe_receipt()` / `telebirr.parse_telebirr_receipt()`),
validates the amount (`validation.validate_payment()`), checks for a
duplicate transaction (`duplicate_check.is_duplicate_transaction()`),
and writes the outcome back to the `receipts` row. Public, no auth — a
buyer triggers verification of their own receipt, same as Task 13.
Idempotent for a receipt already `'verified'`: returns the stored
result instead of re-running the pipeline. Product delivery release
(showing the buyer the seller's Drive link) is explicitly Task 27, not
this task.

Phase 2, Task 27: adds GET /receipts/{receipt_id}/delivery — the
buyer's last step, revealing the seller's public Google Drive link once
(and only once) `receipts.status == 'verified'` (Task 26). A separate
GET endpoint rather than folded into Task 26's verify response — see
this endpoint's own docstring for the reasoning. `drive_link` is still
never exposed by any other endpoint before a verified purchase.

Phase 3, Task 30: `verify_receipt()` now records a `sales` row the
moment a receipt is written `status = 'verified'` — gross amount,
NATRA's commission, and the seller's payable balance, computed from
`admin_settings.commission_rate` (Task 29) and snapshotted onto the row
so a later change to the rate never rewrites a past sale's numbers.
Same transaction/connection as the `receipts` UPDATE so the two can
never diverge (a receipt marked verified with no matching sale, or vice
versa). No endpoint reads `sales` yet — that's a later Phase 3 task
(seller earnings / admin financial reporting).

Phase 3, Task 31: adds GET /admin/settings (admin-only) — the first way
to actually read `commission_rate` (previously set only by Task 29's
NOT NULL/DEFAULT column, readable only via direct SQL) — and extends
PUT /admin/settings to optionally update it, same "omit = leave
unchanged" convention already used for the four CBE/Telebirr fields.
Both return the new `AdminSettingsResponse`, which is `PaymentInfoResponse`
plus `commission_rate`; the public, buyer-facing GET /payment-info is
unchanged and still never exposes the commission rate to a buyer.

Phase 3, Task 32: adds GET /sellers/earnings (seller-only, via the
existing `get_current_seller_id`) — the first thing that actually reads
the `sales` table (Task 30). Returns an aggregate summary (sale count,
total gross, total commission, total payable) for the authenticated
seller's own sales only. Deliberately does not track "settled" vs
"unsettled" yet — there is no settlements mechanism at all yet (a later
Phase 3 task), so every payable amount returned here is, for now,
implicitly unsettled in its entirety.

Phase 3, Task 33: adds GET/PUT /sellers/payment-methods (seller-only,
via the existing `get_current_seller_id`) — lets a seller set the
CBE/Telebirr account they want to be paid out to for a future
settlement. Mirrors GET/PUT /admin/settings' shape and "omit = leave
unchanged" convention, but this is a seller's own payout account, on
`sellers` (new columns this task), never shown to buyers and never the
account a buyer pays into (buyers only ever see NATRA's own
`admin_settings` account via GET /payment-info; see ARCHITECTURE.md's
payment architecture). No settlement logic reads these columns yet —
that's a later Phase 3 task.

Phase 3, Task 34: adds POST/GET /admin/settlements (admin-only, via the
existing `get_current_admin`) — records that NATRA settled (or intends
to settle) a given amount to a given seller. NATRA still pays the
seller manually, outside this system, to the payout account from Task
33; this endpoint just records that a settlement happened/is happening.
Every new settlement starts `status = 'pending'` — nothing transitions
it to `'completed'` yet (a later Phase 3 task, admin settlement
management, adds that). Deliberately does not validate `amount` against
the seller's actual outstanding `sales.seller_payable` balance yet
(no settled/unsettled split exists in GET /sellers/earnings either —
also a later task); this task is just the settlement record itself.

Phase 3, Task 35: adds POST /admin/settlements/{settlement_id}/complete
(admin-only) — the transition Task 34 deliberately left out: marks a
`'pending'` settlement `'completed'` and stamps `completed_at`. Mirrors
POST /receipts/{receipt_id}/verify's idempotency shape: calling this
again on an already-`'completed'` settlement just returns the stored
result rather than re-running the update or erroring. This is the first
thing that ever sets `completed_at`; still no settled/unsettled split
in GET /sellers/earnings (a later task) and still no reconciliation
against `sales.seller_payable` (Task 34's same open gap).

Phase 3, Task 36: extends GET /sellers/earnings (Task 32) with the
settled/unsettled split it deliberately left out — `settled_total`
(sum of this seller's `'completed'` settlements, Task 34/35) and
`unsettled_total` (`seller_payable_total - settled_total`). No new
endpoint; same seller-only access as before.

Phase 3, Task 37: adds GET /admin/reports (admin-only, via the existing
`get_current_admin`) — the first piece of admin-facing financial
reporting. Platform-wide totals across every seller's `sales` and
`settlements`: same six fields GET /sellers/earnings (Task 32/36)
already returns for one seller, just without the `WHERE seller_id = ...`
filter. Deliberately the platform-totals slice only, not a per-seller
breakdown — a grouped-by-seller view is a natural next step but reuses
this same query shape (add `GROUP BY seller_id`), so it makes sense as
its own later task rather than folded in here.

Phase 3, Task 38: adds GET /admin/reports/by-seller (admin-only) — the
per-seller breakdown Task 37 deliberately left out. Same underlying
`sales`/`settlements` aggregation, `GROUP BY seller_id` instead of
summed platform-wide, so `GET /admin/reports`' single totals row and
this endpoint's list of per-seller rows always agree (the list's rows
sum to the single row's totals). Only sellers with at least one sale
appear — a seller with zero sales has nothing to report and no
`seller_id` to group by in `sales`. This is the last item on Phase 3's
task list (see PROJECT_ROADMAP.md).

Phase 4, Task 39: adds a fail-fast startup configuration check (a new
`@app.on_event("startup")` handler, `_validate_startup_config()`) —
the first Phase 4 task. Before this, every required environment
variable (`ORACLE_USER`/`ORACLE_PASSWORD`/`ORACLE_DSN`, `JWT_SECRET_KEY`)
was only checked lazily, per request, the first time something
actually needed it — surfacing as a 500 on whichever request happened
to hit it first, possibly long after a broken deploy started accepting
traffic. Those four now stop the app from starting at all if any is
missing. `ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH` are deliberately not fatal
(POST /admin/login already degrades gracefully without them); a
missing one only logs a warning, so a deployment mid-provisioning the
admin account isn't blocked from serving buyers/sellers. Runs on actual
app startup only, never on a plain import (e.g. tooling or tests
importing `app.main`), so per-request runtime behavior is unchanged.

Phase 4, Task 40: adds CORS configuration via `fastapi.middleware.cors.
CORSMiddleware`, restricting cross-origin requests to an explicit,
configurable allowlist instead of the implicit all-or-nothing state
before this task (no CORS headers at all meant every browser blocked
every cross-origin call, including the real frontend's — CORS was
never actually usable, not "open"). The new `CORS_ALLOWED_ORIGINS`
env var is a comma-separated list of exact origins (scheme + host +
port, e.g. `http://localhost:5173`); unset/empty means zero origins
allowed (same net effect as before this task — nothing regresses to
being more open by accident), not `allow_origins=["*"]`. `allow_
credentials=False` throughout, since the frontend authenticates via a
Bearer token in the `Authorization` header, never cookies — the more
restrictive `*`-incompatible credentialed-CORS mode this app doesn't
need. See `_cors_allowed_origins()` and the `app.add_middleware(...)`
call below for the exact behavior.

Phase 4, Task 41: `get_current_seller_id` gains the mirror-image role
check `get_current_admin` (Task 15) already had — an admin token is now
rejected with 403 there too, instead of merely being harmless by
accident (`sub="admin"` never matching a real `seller_id`).

Phase 4, Task 42: `POST /admin/settlements` gains an over-payment
check — an `amount` that would push a seller's `unsettled_total`
(the same formula `GET /sellers/earnings`, Task 36, already computes)
negative is now rejected with 422 before any row is inserted.

Phase 4, Task 43: adds `handle_unexpected_error`, a single
`@app.exception_handler(Exception)` catch-all. Before this, any
uncaught exception — an `oracledb.Error` from a query no endpoint
happened to wrap in try/except, or anything else unexpected — fell
through to Starlette's bare-bones default handler, which returns
plain-text "Internal Server Error", not this API's usual JSON
`{"detail": "..."}` shape, and offers no guarantee against leaking the
underlying exception's message. Every existing `HTTPException` raise
throughout this file is unaffected (FastAPI's own, more specific
handler for those still runs first); this handler only catches what
would otherwise be unhandled, always logs the real exception
server-side, and always returns the same generic, non-leaking 500
JSON body to the client.

Phase 6, Task 68: adds email-based OTP verification (`app/otp.py`,
emailed via Brevo — `app/brevo_email.py`) for two previously-missing
flows: confirming a seller's email after registration
(`POST /sellers/verify-email`, `POST /sellers/verify-email/resend`)
and self-service password reset
(`POST /sellers/password-reset/request`,
`POST /sellers/password-reset/confirm`). `POST /sellers/register` now
also fires off the first signup OTP email (best-effort — a send
failure there is logged, not raised, since the account is already
created by that point; the seller can always hit the resend endpoint).
Every new endpoint here is rate-limited per-IP the same way as
`POST /sellers/login` (Task 44), and the two `request`-style endpoints
(`verify-email/resend`, `password-reset/request`) return the exact
same response whether or not the email is registered/already
verified, for the same anti-enumeration reason `POST /sellers/login`
already documents. Deliberately NOT in scope for this task: gating
`POST /sellers/login` on `email_verified` — see `sellers.email_verified`'s
own comment in `backend/db/schema.sql` for why. (Task 71 later closed
this gap — see that task's notes and `login_seller()`'s own docstring.)

Phase 8, Task 89: adds Object Storage configuration — `OCI_NAMESPACE`,
`OCI_REGION`, `OCI_BUCKET_NAME`, `OCI_TENANCY_OCID`, `OCI_USER_OCID`,
`OCI_FINGERPRINT`, `OCI_KEY_FILE` (required), plus `OCI_KEY_FILE_
PASSPHRASE` (optional — only needed if that key file itself has one) —
to `_RECOMMENDED_ENV_VARS`, `.env.example`, and `.env.production.example`.
First of three Phase 8 backend tasks split out of a single originally
bigger task (see `PROJECT_ROADMAP.md`'s Phase 8 section for why); this
one is config only — no `app/object_storage.py`, no `import oci`
anywhere in this codebase yet (that's Task 90).

Deliberately RECOMMENDED (warns, doesn't block startup), not added to
`_REQUIRED_CRITICAL_ENV_VARS`, even though the task list calls this
"extends Task 39's fail-fast startup check to cover the new required
vars" — "required" there describes the *variables themselves* (all
eight, if Object Storage is configured at all, since a half-configured
client is worse than an absent one — see Task 90), not that they must
be *fatal at startup* the way `ORACLE_*`/`JWT_SECRET_KEY` are. Nothing
in this codebase reads these eight vars yet (Task 90 adds the client
that does), and product thumbnails remain an optional, additive
feature on top of an already-complete buyer/seller/admin app — the
same reasoning `ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH` (Task 39) already
documents for "missing this degrades one feature, not the whole app."
Making these fatal now, before Task 91-93 give them anything to do,
would stop every existing deployment from starting over an unused
feature the moment this task's code is deployed. Task 91's health
check (`GET /health/object-storage`) is the right place to surface a
missing/broken Object Storage config as an operational signal — the
same division of responsibility Task 18's Playwright health check and
`ORACLE_*`'s fatal-at-startup check already split between "won't start
at all" vs. "started, but here's a live health signal" for the two
existing external dependencies.

Phase 8, Task 91: adds that health check — `GET /health/object-storage`,
using Task 90's `get_client()`/`get_namespace()`/`get_bucket_name()` via
`check_object_storage()`. Mirrors `GET /health/playwright` (Task 18)
field-for-field: a thin route handler that calls a same-named `check_*`
function and merges its result dict into `{"service": ...}`, no logic
of its own. Last of the three Phase 8 backend tasks split out of the
original Task 89 (see `PROJECT_ROADMAP.md`). Still no upload/download
logic anywhere in this codebase — that started at Task 93, in the new
`app/thumbnail.py`.

Phase 8, Task 94: adds `POST /products/{product_id}/thumbnail` — the
first file-upload endpoint in this codebase (`UploadFile`, imported
from `fastapi` alongside `File`). Seller-auth via the existing
`get_current_seller_id`; an explicit ownership check (the product's
`seller_id` column must match the caller's own, not just "some
seller" per the role check) before any file is read; then a single
call to Task 93's `upload_thumbnail()` and one `UPDATE products SET
thumbnail_ref = ...`. See `upload_product_thumbnail()`'s own
docstring for the sync-route-with-UploadFile and error-mapping
reasoning.

Phase 8, Tasks 95-96: surfacing `thumbnail_ref` on the two buyer-facing
GET endpoints (`GET /products`'s `ProductGridItem`, `GET
/products/{id}`'s `ProductDetailResponse`) needed no code changes —
both models and both queries already carried the column, unused, since
before Phase 8 existed (Task 8). Confirmed and left as-is; see
`CURRENT_STATUS.md` for how this was verified.

Phase 8, Task 97: adds `thumbnail_ref` to `ProductResponse` and to
`list_my_products()`'s query/construction — the one place of the three
GET endpoints that actually needed a code change, since the seller
dashboard (`GET /products/mine`) had never selected the column at all.
`ProductResponse` is also `POST /products`'s response model; that
route doesn't pass `thumbnail_ref` when constructing it, so it
continues to default to `None` there, matching that route's own
docstring.
"""

import logging
import os
from urllib.parse import urlparse

import oracledb
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .auth import (
    InvalidTokenError,
    JWTConfigError,
    create_access_token,
    create_admin_access_token,
    decode_access_token,
)
from .brevo_email import BrevoConfigError, BrevoSendError
from .browser import check_browser
from .cbe import CBE_RECEIPT_HOST, parse_cbe_receipt
from .db import check_connection, get_connection
from .duplicate_check import REASON_DUPLICATE_TRANSACTION, is_duplicate_transaction
from .logging_config import RequestLoggingMiddleware, setup_logging
from .object_storage import check_object_storage
from .otp import (
    OTPResult,
    PURPOSE_PASSWORD_RESET,
    PURPOSE_SIGNUP,
    issue_otp,
    send_password_reset_otp_email,
    send_signup_otp_email,
    verify_otp,
)
from .rate_limit import RateLimitExceeded, check_rate_limit
from .security import hash_password, verify_password
from .telebirr import TELEBIRR_RECEIPT_HOST, parse_telebirr_receipt
from .thumbnail import ThumbnailUploadError, ThumbnailValidationError, upload_thumbnail
from .validation import PROVIDER_CBE, PROVIDER_TELEBIRR, validate_payment

# Task 48. Configured before the app object and before any of the
# logger.warning(...) calls below (CORS/recommended-env-var checks run at
# import time, not inside a request) — otherwise those warnings would hit
# logging.lastResort instead of the structured JSON handler this sets up.
setup_logging()

app = FastAPI(title="NATRA API")
app.add_middleware(RequestLoggingMiddleware)

logger = logging.getLogger("natra")

_REQUIRED_CRITICAL_ENV_VARS = [
    "ORACLE_USER",
    "ORACLE_PASSWORD",
    "ORACLE_DSN",
    "JWT_SECRET_KEY",
]

_ADMIN_ENV_VARS = [
    "ADMIN_EMAIL",
    "ADMIN_PASSWORD_HASH",
]

# Task 89. Object Storage (product thumbnails, Phase 8). Recommended, not
# critical — see this module's Task 89 docstring paragraph above for why
# these don't stop the app from starting. OCI_KEY_FILE_PASSPHRASE is
# deliberately excluded from this list: it's optional even once Object
# Storage IS configured (only needed if the key file itself is
# passphrase-protected), so its absence alone shouldn't warn the way a
# genuinely missing var should.
_OBJECT_STORAGE_ENV_VARS = [
    "OCI_NAMESPACE",
    "OCI_REGION",
    "OCI_BUCKET_NAME",
    "OCI_TENANCY_OCID",
    "OCI_USER_OCID",
    "OCI_FINGERPRINT",
    "OCI_KEY_FILE",
]

# Kept for any external reference to "the non-fatal set" as a whole
# (e.g. tests); the startup check itself (below) warns on each group
# separately so one feature's missing vars don't get blamed on the other.
_RECOMMENDED_ENV_VARS = _ADMIN_ENV_VARS + _OBJECT_STORAGE_ENV_VARS


class StartupConfigError(RuntimeError):
    """Raised when a critical environment variable is missing at app startup."""


def _validate_startup_config() -> None:
    """
    Task 39. Fail-fast configuration check. Critical vars — `ORACLE_USER`,
    `ORACLE_PASSWORD`, `ORACLE_DSN`, `JWT_SECRET_KEY` — are things the app
    is non-functional without (no DB, no auth at all), so a missing one
    raises `StartupConfigError`, which stops the app from starting.
    Refusing to come up is better than coming up and 500ing on whichever
    request happens to hit the missing piece first — which, before this
    task, could be minutes or hours after a broken deploy started
    accepting traffic (`db.get_connection()` and `auth._get_secret()`
    both already raised their own config errors, but only lazily, per
    request, the first time something actually called them).

    `ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH` are deliberately NOT fatal here:
    `POST /admin/login` already handles their absence gracefully (a
    generic "Invalid email or password" 401, the same anti-enumeration
    response as a wrong password — see that endpoint's docstring), and
    every buyer/seller flow keeps working without them. A missing one
    only logs a warning, so a deployment that's mid-provisioning the
    admin account isn't blocked from serving buyers and sellers in the
    meantime.

    Task 89 adds the eight Object Storage vars (`OCI_NAMESPACE` etc.,
    product thumbnails) to that same non-fatal, warning-only list, for
    the equivalent reason — see this module's Task 89 docstring
    paragraph above. Unlike the admin vars, nothing reads these yet
    (Task 90 adds the client), so today they'd only ever warn.
    """
    missing_critical = [name for name in _REQUIRED_CRITICAL_ENV_VARS if not os.environ.get(name)]
    if missing_critical:
        raise StartupConfigError(
            "Missing required environment variable(s): " + ", ".join(missing_critical)
        )

    # Task 89: split into two independent warnings, one per feature, now
    # that _RECOMMENDED_ENV_VARS covers two unrelated features (admin
    # login; Object Storage/thumbnails) — a single combined message
    # would misleadingly claim admin login is at risk from a missing
    # OCI_* var, or vice versa.
    missing_admin = [name for name in _ADMIN_ENV_VARS if not os.environ.get(name)]
    if missing_admin:
        logger.warning(
            "Admin login will fail until these are set: %s",
            ", ".join(missing_admin),
        )

    missing_object_storage = [name for name in _OBJECT_STORAGE_ENV_VARS if not os.environ.get(name)]
    if missing_object_storage:
        logger.warning(
            "Object Storage (product thumbnails) is not configured — "
            "these are unset: %s",
            ", ".join(missing_object_storage),
        )


@app.on_event("startup")
def _on_startup() -> None:
    """
    Runs once, only when the app actually starts serving (e.g. under
    Uvicorn) — never on a plain `import app.main`, so tooling and tests
    that import this module (including this repo's own throwaway
    fake-cursor tests) are unaffected.
    """
    _validate_startup_config()


def _parse_cors_origins(raw: str | None) -> list[str]:
    """
    Task 40. Parses `CORS_ALLOWED_ORIGINS` (comma-separated exact
    origins, e.g. "http://localhost:5173,https://natra.example.com")
    into a list, trimming whitespace and dropping empty entries (so a
    trailing comma or accidental double comma doesn't produce a blank
    "allow everything" origin — `CORSMiddleware` treats "" as a wildcard
    match for some Starlette versions, which this app never wants).
    `None` or an all-whitespace/empty string both parse to `[]` — zero
    origins allowed, not `["*"]`.
    """
    if not raw or not raw.strip():
        return []
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


_cors_allowed_origins = _parse_cors_origins(os.environ.get("CORS_ALLOWED_ORIGINS"))

if not _cors_allowed_origins:
    # Not fatal (see Task 39's docstring for what IS fatal) — CORS only
    # affects browser-based cross-origin calls; same-origin requests,
    # curl, Postman, mobile apps, etc. are entirely unaffected either
    # way. Warn, don't crash: a backend-only deployment (see Task 39's
    # "Errors Encountered" note about the frontend not existing yet)
    # has nothing to put here yet, and that's a legitimate state.
    logger.warning(
        "CORS_ALLOWED_ORIGINS is not set — no cross-origin browser "
        "requests will be allowed until it's configured."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.exception_handler(Exception)
def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """
    Task 43. Centralized handler for any exception that reaches here
    uncaught — i.e. everything that ISN'T an `HTTPException` (FastAPI
    keeps its own, more specific handler for those, registered before
    this one in Starlette's exception-handler lookup, so every existing
    `raise HTTPException(status_code=..., detail=...)` throughout this
    file is completely unaffected) and isn't a Pydantic
    `RequestValidationError` (FastAPI's default handler for those also
    stays in place, still returning its usual structured 422).

    Before this task, an uncaught exception — an `oracledb.Error` from a
    query no endpoint wrapped in try/except, a `TypeError`, anything
    unexpected — fell through to Starlette's own default handler, which
    (with debug mode off, as this app always runs in production) returns
    a bare `"Internal Server Error"` *plain-text* body, not JSON. That's
    inconsistent with every other error response in this API (all
    `{"detail": "..."}` JSON), and — more importantly — depending on
    what the underlying exception was, the OLD default handler's
    behavior wasn't guaranteed not to leak internals (e.g. a raw
    `oracledb.Error`'s message can include SQL fragments or connection
    details) into the response body in every deployment configuration.

    This handler makes both problems go away by construction: it always
    logs the real exception with a full traceback server-side (via
    `logger.error(..., exc_info=exc)` — the exception object is passed
    explicitly rather than relying on `logger.exception()`'s ambient
    `sys.exc_info()`, which testing showed isn't reliably populated by
    the time Starlette's exception middleware invokes this handler), so
    nothing is lost for debugging, and always returns the exact same
    generic, non-leaking
    `{"detail": "Internal server error"}` JSON body with status 500 to
    the client — regardless of what the underlying exception actually
    was. The client never sees exception messages, stack traces, SQL,
    or connection details for anything unexpected.
    """
    logger.error(
        "Unhandled exception on %s %s", request.method, request.url.path,
        exc_info=exc,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def _rate_limit_key(prefix: str, request: Request) -> str:
    """
    Task 44. Builds the per-client key `check_rate_limit()` counts
    attempts under, for a given login endpoint. Uses
    `request.client.host` — the direct TCP peer address as Starlette
    sees it. Behind Task 46's planned Nginx reverse proxy, that will be
    Nginx's own address for every request unless Nginx is configured to
    forward the real client IP (e.g. via `X-Forwarded-For`) and this
    function is updated to read it — deliberately not done speculatively
    here, since Task 46 (which introduces the actual proxy) is where
    that config needs to be decided and tested together, not guessed at
    now. Falls back to the literal string "unknown" if `request.client`
    is `None` (happens in some test/ASGI-transport setups), which still
    rate-limits correctly — just as one shared bucket across every
    client without a discoverable address, rather than not rate-limiting
    them at all.
    """
    host = request.client.host if request.client else "unknown"
    return f"{prefix}:{host}"


@app.get("/health")
def health_check() -> dict:
    """Simple liveness check used to verify the backend is running."""
    return {"status": "ok", "service": "natra-backend"}


@app.get("/health/db")
def health_check_db() -> dict:
    """
    Verifies the backend can actually connect to Oracle Autonomous Database
    using the ORACLE_* environment variables and run a trivial query.
    """
    result = check_connection()
    return {"service": "natra-backend", **result}


@app.get("/health/playwright")
def health_check_playwright() -> dict:
    """
    Verifies Playwright browser automation is installed and working by
    launching a headless browser and loading a trivial page. Phase 2's
    receipt verification (Tasks 20+/22+) will reuse the same underlying
    launch mechanism to load real CBE/Telebirr receipt URLs.
    """
    result = check_browser()
    return {"service": "natra-backend", **result}


@app.get("/health/object-storage")
def health_check_object_storage() -> dict:
    """
    Verifies Oracle Object Storage is reachable and correctly configured
    by building a client from the OCI_* environment variables (Task 89)
    and fetching the configured bucket's metadata. Phase 8's thumbnail
    upload/download work (Tasks 93+) will reuse the same client.
    """
    result = check_object_storage()
    return {"service": "natra-backend", **result}


class SellerRegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=255)


class SellerRegisterResponse(BaseModel):
    id: str
    email: str


@app.post("/sellers/register", response_model=SellerRegisterResponse, status_code=201)
def register_seller(payload: SellerRegisterRequest) -> SellerRegisterResponse:
    """
    Register a new seller account. Hashes the password (never stored in
    plain text) and inserts a row into `sellers`, starting
    `email_verified = 'N'`. Rejects a duplicate email cleanly (the
    table's unique constraint enforces this at the DB level).

    Task 68: also issues a signup-verification OTP and emails it via
    Brevo. This is best-effort: the account row is already committed
    by the time the email is sent, so a Brevo failure here is logged
    and swallowed rather than turning a successful registration into
    an error response — the seller can always retry via
    `POST /sellers/verify-email/resend`.
    """
    email = payload.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(status_code=422, detail="Invalid email address")

    password_hash = hash_password(payload.password)

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                id_out = cur.var(str)
                cur.execute(
                    """
                    INSERT INTO sellers (email, password_hash)
                    VALUES (:email, :password_hash)
                    RETURNING RAWTOHEX(id) INTO :id_out
                    """,
                    email=email,
                    password_hash=password_hash,
                    id_out=id_out,
                )
                conn.commit()
                seller_id = id_out.getvalue()[0]
    except oracledb.IntegrityError:
        raise HTTPException(status_code=409, detail="Email already registered")

    try:
        code = issue_otp(email, PURPOSE_SIGNUP)
        send_signup_otp_email(email, code)
    except (BrevoConfigError, BrevoSendError) as exc:
        logger.error("Failed to send signup OTP email to %s: %s", email, exc)

    return SellerRegisterResponse(id=seller_id, email=email)


class SellerLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)


class SellerLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@app.post("/sellers/login", response_model=SellerLoginResponse)
def login_seller(payload: SellerLoginRequest, request: Request) -> SellerLoginResponse:
    """
    Verify seller credentials and return a JWT on success. Returns the same
    generic error for "no such email" and "wrong password" so a caller
    can't use this endpoint to enumerate registered emails.

    Task 71: once credentials check out, also requires
    `sellers.email_verified = 'Y'` — an unverified seller gets a 403
    ("Please verify your email before logging in.") instead of a token.
    This used to be explicitly out of scope (see Task 68's note, still
    visible in `backend/db/schema.sql`'s comment on the column) to
    avoid breaking the register-then-auto-login chain in
    `SellerRegister.tsx`; that chain no longer auto-logs-in (Task 71
    frontend change), so the gate is safe to add here now.

    Task 44: rate-limited per client IP (see `rate_limit.py`) before any
    credential check runs, so a brute-force/credential-stuffing attempt
    against this endpoint is slowed down regardless of whether the
    emails/passwords it's trying are valid. Deliberately keyed by IP
    only, not by the submitted email — keying by email would let an
    attacker rotate source IPs to bypass the limit per-target-email, but
    it would ALSO let an attacker lock a legitimate seller out of their
    own account just by submitting that seller's email repeatedly from
    anywhere. IP-keying avoids that second problem; see `rate_limit.py`
    for the shared-NAT trade-off this implies.
    """
    limit_key = _rate_limit_key("seller_login", request)
    try:
        check_rate_limit(limit_key)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        )

    email = payload.email.strip().lower()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT RAWTOHEX(id), password_hash, email_verified FROM sellers"
                " WHERE email = :email",
                email=email,
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    seller_id, password_hash, email_verified = row
    if not verify_password(payload.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Task 71: gate on email_verified. Deliberately checked *after* the
    # password check above, not before/instead of it — checking this
    # first would mean a wrong password against an unverified email
    # returns a different error than a wrong password against a
    # verified one, which leaks whether an email is verified (and,
    # combined with register's 409, whether it's registered at all) to
    # anyone willing to guess passwords. 403 (distinct from the generic
    # 401 above) is safe to use here specifically because "verified"
    # isn't itself a secret once you already know the password is
    # correct.
    if email_verified != "Y":
        raise HTTPException(
            status_code=403,
            detail="Please verify your email before logging in.",
        )

    try:
        token = create_access_token(seller_id, email)
    except JWTConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return SellerLoginResponse(access_token=token)


# --- Task 68: email verification (signup OTP) -----------------------------

_OTP_RESULT_MESSAGES = {
    OTPResult.NOT_FOUND: "This code has expired or wasn't found. Request a new one.",
    OTPResult.EXPIRED: "This code has expired. Request a new one.",
    OTPResult.TOO_MANY_ATTEMPTS: "Too many incorrect attempts. Request a new code.",
    OTPResult.INVALID: "Incorrect code. Please try again.",
}


class VerifyEmailRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    otp: str = Field(..., min_length=6, max_length=6)


class VerifyEmailResponse(BaseModel):
    verified: bool = True


@app.post("/sellers/verify-email", response_model=VerifyEmailResponse)
def verify_seller_email(payload: VerifyEmailRequest, request: Request) -> VerifyEmailResponse:
    """
    Confirm a seller's email address using the OTP sent by
    `POST /sellers/register` (or `.../verify-email/resend`). On a
    valid, unexpired code within the attempt limit, flips
    `sellers.email_verified` to 'Y'. Rate-limited per-IP like
    `POST /sellers/login` — this endpoint is unauthenticated (the
    seller may not have a token yet if verification happens before
    first login), so it needs its own brute-force guard independent of
    `otp.py`'s own per-code attempt counter.
    """
    limit_key = _rate_limit_key("verify_email", request)
    try:
        check_rate_limit(limit_key)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        )

    email = payload.email.strip().lower()
    result = verify_otp(email, PURPOSE_SIGNUP, payload.otp.strip())

    if result != OTPResult.VALID:
        raise HTTPException(
            status_code=400,
            detail=_OTP_RESULT_MESSAGES.get(result, "Invalid or expired code."),
        )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sellers SET email_verified = 'Y' WHERE email = :email",
                email=email,
            )
            conn.commit()

    return VerifyEmailResponse(verified=True)


class ResendVerificationRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)


class ResendVerificationResponse(BaseModel):
    message: str = "If that email needs verification, a new code has been sent."


@app.post("/sellers/verify-email/resend", response_model=ResendVerificationResponse)
def resend_verification_email(
    payload: ResendVerificationRequest, request: Request
) -> ResendVerificationResponse:
    """
    Re-send a signup-verification OTP. Always returns the same generic
    message whether the email is registered, already verified, or
    doesn't exist — same anti-enumeration reasoning as
    `POST /sellers/login` and `POST /sellers/password-reset/request`
    below — so this can't be used to test which emails have a seller
    account. Rate-limited per-IP so it can't be used to spam a
    victim's inbox.
    """
    limit_key = _rate_limit_key("resend_verification", request)
    try:
        check_rate_limit(limit_key)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        )

    email = payload.email.strip().lower()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT email_verified FROM sellers WHERE email = :email",
                email=email,
            )
            row = cur.fetchone()

    if row is not None and row[0] != "Y":
        try:
            code = issue_otp(email, PURPOSE_SIGNUP)
            send_signup_otp_email(email, code)
        except (BrevoConfigError, BrevoSendError) as exc:
            logger.error("Failed to resend signup OTP email to %s: %s", email, exc)

    return ResendVerificationResponse()


# --- Task 68: password reset (OTP) -----------------------------------------


class PasswordResetRequestRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)


class PasswordResetRequestResponse(BaseModel):
    message: str = "If that email is registered, a reset code has been sent."


@app.post("/sellers/password-reset/request", response_model=PasswordResetRequestResponse)
def request_password_reset(
    payload: PasswordResetRequestRequest, request: Request
) -> PasswordResetRequestResponse:
    """
    Start a password reset: if `email` belongs to a registered seller,
    emails an OTP via Brevo. Always returns the same generic message
    either way — the same anti-enumeration reasoning
    `POST /sellers/login` already documents applies here too, since a
    distinguishable response would let a caller test which emails have
    a seller account. Rate-limited per-IP for the same reason as
    `.../verify-email/resend`.
    """
    limit_key = _rate_limit_key("password_reset_request", request)
    try:
        check_rate_limit(limit_key)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        )

    email = payload.email.strip().lower()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM sellers WHERE email = :email", email=email)
            row = cur.fetchone()

    if row is not None:
        try:
            code = issue_otp(email, PURPOSE_PASSWORD_RESET)
            send_password_reset_otp_email(email, code)
        except (BrevoConfigError, BrevoSendError) as exc:
            logger.error("Failed to send password-reset OTP email to %s: %s", email, exc)

    return PasswordResetRequestResponse()


class PasswordResetConfirmRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    otp: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=255)


class PasswordResetConfirmResponse(BaseModel):
    reset: bool = True


@app.post("/sellers/password-reset/confirm", response_model=PasswordResetConfirmResponse)
def confirm_password_reset(
    payload: PasswordResetConfirmRequest, request: Request
) -> PasswordResetConfirmResponse:
    """
    Complete a password reset: verifies the OTP from
    `.../password-reset/request` and, if valid, hashes and stores
    `new_password`. Rate-limited per-IP like `verify_seller_email()`
    above, for the same reason (unauthenticated endpoint, needs its
    own brute-force guard independent of `otp.py`'s per-code attempt
    counter).
    """
    limit_key = _rate_limit_key("password_reset_confirm", request)
    try:
        check_rate_limit(limit_key)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        )

    email = payload.email.strip().lower()
    result = verify_otp(email, PURPOSE_PASSWORD_RESET, payload.otp.strip())

    if result != OTPResult.VALID:
        raise HTTPException(
            status_code=400,
            detail=_OTP_RESULT_MESSAGES.get(result, "Invalid or expired code."),
        )

    password_hash = hash_password(payload.new_password)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sellers SET password_hash = :password_hash WHERE email = :email",
                password_hash=password_hash,
                email=email,
            )
            conn.commit()

    return PasswordResetConfirmResponse(reset=True)


def get_current_seller_id(authorization: str | None = Header(default=None)) -> str:
    """
    FastAPI dependency for protected seller endpoints. Reads and verifies
    the `Authorization: Bearer <token>` header and returns the seller id
    encoded in it (`sub` claim). Raises 401 for anything wrong with the
    token so it can't be distinguished from "no token at all".

    Task 41: also requires the token's `role` claim to equal "seller" —
    the mirror image of `get_current_admin`'s role check (Task 15). Before
    this task an admin token reaching a seller endpoint wasn't rejected by
    role at all; it happened to be harmless because `sub="admin"` never
    matches a real seller_id, so e.g. GET /products/mine just returned an
    empty list. That was accidental safety, not an access-control
    decision, so it's closed here the same way: authenticated but wrong
    role is 403, not 401. See `get_current_admin`'s docstring and
    ARCHITECTURE.md.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization[len("Bearer ") :].strip()
    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    except JWTConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if payload.get("role") != "seller":
        raise HTTPException(status_code=403, detail="Seller access required")

    seller_id = payload.get("sub")
    if not seller_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return seller_id


class ProductCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    price: float = Field(..., gt=0)
    description: str = Field(default="", max_length=4000)
    drive_link: str = Field(..., min_length=1, max_length=2048)


class ProductResponse(BaseModel):
    id: str
    seller_id: str
    name: str
    price: float
    description: str
    drive_link: str
    thumbnail_ref: str | None = None


@app.post("/products", response_model=ProductResponse, status_code=201)
def create_product(
    payload: ProductCreateRequest,
    seller_id: str = Depends(get_current_seller_id),
) -> ProductResponse:
    """
    Add a product owned by the authenticated seller (first protected
    endpoint). No thumbnail upload yet — Object Storage integration is a
    later task, so `thumbnail_ref` is simply left null here.
    """
    drive_link = payload.drive_link.strip()
    if not drive_link.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="drive_link must be a valid URL")

    name = payload.name.strip()
    description = payload.description.strip()

    with get_connection() as conn:
        with conn.cursor() as cur:
            id_out = cur.var(str)
            cur.execute(
                """
                INSERT INTO products (seller_id, name, price, description, drive_link)
                VALUES (HEXTORAW(:seller_id), :name, :price, :description, :drive_link)
                RETURNING RAWTOHEX(id) INTO :id_out
                """,
                seller_id=seller_id,
                name=name,
                price=payload.price,
                description=description,
                drive_link=drive_link,
                id_out=id_out,
            )
            conn.commit()
            product_id = id_out.getvalue()[0]

    return ProductResponse(
        id=product_id,
        seller_id=seller_id,
        name=name,
        price=payload.price,
        description=description,
        drive_link=drive_link,
    )


@app.get("/products/mine", response_model=list[ProductResponse])
def list_my_products(
    seller_id: str = Depends(get_current_seller_id),
) -> list[ProductResponse]:
    """
    List only the products owned by the authenticated seller. Protected
    the same way as POST /products; `seller_id` comes from the verified
    JWT, never from a query parameter, so a seller can never list another
    seller's products.

    Task 97: also surfaces `thumbnail_ref` (already a full public Object
    Storage URL — see Task 93 — not a bare object name needing later
    construction), so a seller can see their own product's thumbnail on
    the dashboard, the same way Tasks 95-96 already surfaced it on the
    two buyer-facing GET endpoints. `ProductResponse` is shared with
    POST /products, whose own docstring already covers why that endpoint
    leaves the field null.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT RAWTOHEX(id), name, price, description, drive_link, thumbnail_ref
                FROM products
                WHERE seller_id = HEXTORAW(:seller_id)
                ORDER BY created_at DESC
                """,
                seller_id=seller_id,
            )
            rows = cur.fetchall()

    return [
        ProductResponse(
            id=row[0],
            seller_id=seller_id,
            name=row[1],
            price=row[2],
            description=row[3] or "",
            drive_link=row[4],
            thumbnail_ref=row[5],
        )
        for row in rows
    ]


class ThumbnailUploadResponse(BaseModel):
    thumbnail_ref: str


@app.post("/products/{product_id}/thumbnail", response_model=ThumbnailUploadResponse)
def upload_product_thumbnail(
    product_id: str,
    file: UploadFile = File(...),
    seller_id: str = Depends(get_current_seller_id),
) -> ThumbnailUploadResponse:
    """
    Phase 8, Task 94: seller uploads/replaces a product's thumbnail
    image. First endpoint in this codebase that accepts a file upload,
    and comparable in size to Task 8's "Implement Add Product"
    precedent (auth + ownership check + one helper call + one column
    write) — everything else (validation rules, object naming, the
    actual Object Storage call) already lives in Task 92/93's
    `thumbnail.py`, so this route is deliberately thin.

    Kept a sync `def`, not `async def`, matching every other route in
    this module: `get_connection()`/`cur.execute()` are blocking calls
    with no async variant, so an `async def` handler here would block
    the event loop on every DB round trip instead of FastAPI's
    automatic threadpool offload for sync routes. `UploadFile` still
    works fine in a sync route — `file.file` is the underlying
    (sync) `SpooledTemporaryFile`, read directly below instead of
    `await file.read()`.

    Auth + ownership: `get_current_seller_id` (Task 15/41) proves the
    caller is *some* authenticated seller; a product's `seller_id`
    column then has to independently match that seller before this
    endpoint touches it — the same "resource-level ownership beyond
    just role" check `PROJECT_ROADMAP.md`'s Phase 4 hardening pass
    established elsewhere (e.g. settlement/product actions never
    trust a client-supplied seller_id). A product that exists but
    belongs to someone else 403s, exactly like a product that doesn't
    exist at all 404s — both checked before any file is read or
    uploaded, so a seller can't probe for another seller's product
    ids by uploading garbage and comparing error codes... except that
    they still can, in principle, distinguish 404 from 403: that
    tradeoff (informative errors vs. hiding product existence) matches
    every other product/receipt endpoint in this file, none of which
    hide 404s behind a generic 403 either.

    Error mapping: `ThumbnailValidationError` (Task 92 — bad content
    type/extension/size) becomes 400, the caller's fault.
    `ThumbnailUploadError` (Task 93 — the file was fine but Object
    Storage itself failed) becomes 502, since NATRA's own backend
    correctly rejected nothing and the failure is downstream. Both are
    raised by `upload_thumbnail()` before any database write, so a
    failed upload never leaves `thumbnail_ref` partially updated.
    """
    normalized_id = product_id.strip().upper()
    if len(normalized_id) != 32 or not all(c in "0123456789ABCDEF" for c in normalized_id):
        # Not a well-formed RAW(16) hex id — mirrors the same guard used
        # in get_product_detail/submit_receipt so a malformed id 404s
        # cleanly instead of reaching HEXTORAW and raising an Oracle error.
        raise HTTPException(status_code=404, detail="Product not found")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT RAWTOHEX(seller_id) FROM products WHERE id = HEXTORAW(:product_id)",
                product_id=normalized_id,
            )
            row = cur.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Product not found")

            owner_seller_id = row[0]
            if owner_seller_id != seller_id:
                raise HTTPException(status_code=403, detail="You do not own this product")

            file_bytes = file.file.read()
            try:
                thumbnail_url = upload_thumbnail(
                    file_bytes,
                    file.filename or "",
                    file.content_type or "",
                )
            except ThumbnailValidationError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            except ThumbnailUploadError as exc:
                raise HTTPException(status_code=502, detail=str(exc))

            cur.execute(
                "UPDATE products SET thumbnail_ref = :thumbnail_ref WHERE id = HEXTORAW(:product_id)",
                thumbnail_ref=thumbnail_url,
                product_id=normalized_id,
            )
            conn.commit()

    return ThumbnailUploadResponse(thumbnail_ref=thumbnail_url)


class SellerEarningsResponse(BaseModel):
    total_sales: int
    gross_amount_total: float
    commission_total: float
    seller_payable_total: float
    settled_total: float
    unsettled_total: float


@app.get("/sellers/earnings", response_model=SellerEarningsResponse)
def get_seller_earnings(
    seller_id: str = Depends(get_current_seller_id),
) -> SellerEarningsResponse:
    """
    Task 32. First endpoint that reads `sales` (Task 30). Aggregates the
    authenticated seller's own sales only — protected the same way as
    POST /products and GET /products/mine, `seller_id` comes from the
    verified JWT, never a query parameter, so a seller can never see
    another seller's earnings.

    `SUM(...)` over zero rows returns NULL in Oracle, not 0 — coalesced
    to 0.0 here so a seller with no sales yet gets a clean all-zero
    response instead of nulls. Same coalescing applies to the
    settlements sum below.

    Task 36: adds the settled/unsettled split that Task 32 deliberately
    left out (there was no settlements mechanism at all then).
    `settled_total` sums this seller's `'completed'` settlements
    (Task 34/35 — `POST /admin/settlements` then
    `POST /admin/settlements/{id}/complete`); `'pending'` settlements
    are not counted as settled, matching the plain English meaning of
    the word. `unsettled_total` is simply `seller_payable_total -
    settled_total`. Not clamped to zero: nothing in this codebase yet
    prevents an admin from recording more in completed settlements than
    a seller's `sales` actually earned (Task 34/35's own open gap — see
    their docstrings), so a negative `unsettled_total` is possible and
    left visible rather than silently hidden.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*),
                       SUM(gross_amount),
                       SUM(commission_amount),
                       SUM(seller_payable)
                FROM sales
                WHERE seller_id = HEXTORAW(:seller_id)
                """,
                seller_id=seller_id,
            )
            sales_row = cur.fetchone()

            cur.execute(
                """
                SELECT SUM(amount)
                FROM settlements
                WHERE seller_id = HEXTORAW(:seller_id)
                  AND status = 'completed'
                """,
                seller_id=seller_id,
            )
            (settled_sum,) = cur.fetchone()

    total_sales, gross_total, commission_total, payable_total = sales_row
    payable_total = payable_total or 0.0
    settled_total = settled_sum or 0.0
    unsettled_total = round(payable_total - settled_total, 2)

    return SellerEarningsResponse(
        total_sales=total_sales or 0,
        gross_amount_total=gross_total or 0.0,
        commission_total=commission_total or 0.0,
        seller_payable_total=payable_total,
        settled_total=settled_total,
        unsettled_total=unsettled_total,
    )


class SellerPaymentMethodsResponse(BaseModel):
    cbe_account_name: str | None = None
    cbe_account_number: str | None = None
    telebirr_account_name: str | None = None
    telebirr_account_number: str | None = None


class SellerPaymentMethodsUpdateRequest(BaseModel):
    cbe_account_name: str | None = Field(default=None, max_length=255)
    cbe_account_number: str | None = Field(default=None, max_length=64)
    telebirr_account_name: str | None = Field(default=None, max_length=255)
    telebirr_account_number: str | None = Field(default=None, max_length=64)


def _fetch_seller_payment_methods(cur, seller_id: str):
    cur.execute(
        """
        SELECT cbe_account_name, cbe_account_number,
               telebirr_account_name, telebirr_account_number
        FROM sellers
        WHERE id = HEXTORAW(:seller_id)
        """,
        seller_id=seller_id,
    )
    return cur.fetchone()


@app.get("/sellers/payment-methods", response_model=SellerPaymentMethodsResponse)
def get_seller_payment_methods(
    seller_id: str = Depends(get_current_seller_id),
) -> SellerPaymentMethodsResponse:
    """
    Task 33. Seller-only read of the authenticated seller's own payout
    account — protected the same way as GET /sellers/earnings and
    friends, `seller_id` comes from the verified JWT, never a query
    parameter, so a seller can never read another seller's payment
    methods.

    This is where NATRA will eventually *send* a settlement to this
    seller. It is never the account a buyer pays into (that's always
    NATRA's own `admin_settings` row, via GET /payment-info) and it is
    never exposed to buyers by any endpoint. All four fields are NULL
    until the seller sets them via PUT /sellers/payment-methods.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            row = _fetch_seller_payment_methods(cur, seller_id)

    if row is None:
        # Shouldn't happen — seller_id came from a verified JWT for an
        # existing seller row — but degrade to "nothing configured"
        # rather than a 500, mirroring GET /payment-info's/GET
        # /admin/settings' behavior for the same edge case.
        return SellerPaymentMethodsResponse()

    return SellerPaymentMethodsResponse(
        cbe_account_name=row[0],
        cbe_account_number=row[1],
        telebirr_account_name=row[2],
        telebirr_account_number=row[3],
    )


@app.put("/sellers/payment-methods", response_model=SellerPaymentMethodsResponse)
def update_seller_payment_methods(
    payload: SellerPaymentMethodsUpdateRequest,
    seller_id: str = Depends(get_current_seller_id),
) -> SellerPaymentMethodsResponse:
    """
    Task 33. Seller-only write of the authenticated seller's own payout
    account — the write counterpart to GET /sellers/payment-methods
    above. `seller_id` comes from the verified JWT, never the request
    body, so a seller can only ever update their own row.

    Same "omit = leave unchanged" convention as PUT /admin/settings: any
    field left out (or sent as null) leaves that column unchanged rather
    than clearing it, so a seller can set just their CBE info first and
    add Telebirr later without resending everything. To actually clear a
    field once set, send an empty string "" (stored as-is; GET
    /sellers/payment-methods already treats NULL as "not configured",
    and an empty string reads the same way).
    """
    fields = {
        "cbe_account_name": payload.cbe_account_name,
        "cbe_account_number": payload.cbe_account_number,
        "telebirr_account_name": payload.telebirr_account_name,
        "telebirr_account_number": payload.telebirr_account_number,
    }
    # Strip strings but keep None as None (None means "leave unchanged").
    fields = {k: (v.strip() if v is not None else None) for k, v in fields.items()}

    set_clauses = [f"{column} = :{column}" for column, value in fields.items() if value is not None]
    bind_params = {k: v for k, v in fields.items() if v is not None}

    with get_connection() as conn:
        with conn.cursor() as cur:
            if set_clauses:
                bind_params["seller_id"] = seller_id
                cur.execute(
                    f"""
                    UPDATE sellers
                    SET {", ".join(set_clauses)}
                    WHERE id = HEXTORAW(:seller_id)
                    """,
                    **bind_params,
                )
                conn.commit()

            row = _fetch_seller_payment_methods(cur, seller_id)

    if row is None:
        # Shouldn't happen — same edge case as the GET above.
        return SellerPaymentMethodsResponse()

    return SellerPaymentMethodsResponse(
        cbe_account_name=row[0],
        cbe_account_number=row[1],
        telebirr_account_name=row[2],
        telebirr_account_number=row[3],
    )


class ProductGridItem(BaseModel):
    id: str
    name: str
    price: float
    thumbnail_ref: str | None = None


@app.get("/products", response_model=list[ProductGridItem])
def list_all_products() -> list[ProductGridItem]:
    """
    Public buyer-facing product grid — no authentication, lists products
    from every seller. Deliberately minimal fields: no `seller_id`,
    `description`, or `drive_link`. The digital delivery link must never be
    exposed here; it's only revealed after a verified purchase (Phase 2+).
    Fuller per-product info (e.g. description) belongs to the upcoming
    product-details endpoint (Task 11), not this grid.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT RAWTOHEX(id), name, price, thumbnail_ref
                FROM products
                ORDER BY created_at DESC
                """
            )
            rows = cur.fetchall()

    return [
        ProductGridItem(id=row[0], name=row[1], price=row[2], thumbnail_ref=row[3])
        for row in rows
    ]


class ProductDetailResponse(BaseModel):
    id: str
    name: str
    price: float
    description: str
    thumbnail_ref: str | None = None


@app.get("/products/{product_id}", response_model=ProductDetailResponse)
def get_product_detail(product_id: str) -> ProductDetailResponse:
    """
    Public buyer-facing product details page — no authentication. Shows
    the full buyer-visible info for one product. Still **never** returns
    `drive_link` or `seller_id`: the delivery link stays hidden until a
    purchase is verified (Phase 2+), and buyers don't need to know which
    seller owns a product.

    Must be declared after `GET /products/mine` so that path takes
    precedence over being matched here as `product_id="mine"`.
    """
    normalized_id = product_id.strip().upper()
    if len(normalized_id) != 32 or not all(c in "0123456789ABCDEF" for c in normalized_id):
        # Not a well-formed RAW(16) hex id — can't possibly match a row,
        # and passing it to HEXTORAW would raise an Oracle error instead.
        raise HTTPException(status_code=404, detail="Product not found")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT RAWTOHEX(id), name, price, description, thumbnail_ref
                FROM products
                WHERE id = HEXTORAW(:product_id)
                """,
                product_id=normalized_id,
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return ProductDetailResponse(
        id=row[0],
        name=row[1],
        price=row[2],
        description=row[3] or "",
        thumbnail_ref=row[4],
    )


class PaymentInfoResponse(BaseModel):
    cbe_account_name: str | None = None
    cbe_account_number: str | None = None
    telebirr_account_name: str | None = None
    telebirr_account_number: str | None = None


@app.get("/payment-info", response_model=PaymentInfoResponse)
def get_payment_info() -> PaymentInfoResponse:
    """
    Public, no authentication — NATRA's own CBE/Telebirr payment account
    info, shown to a buyer after clicking "Buy Now". This is NATRA's
    account, never a seller's (buyers pay NATRA directly, per
    ARCHITECTURE.md). Fields are NULL until an admin sets them via
    PUT /admin/settings (Task 16).
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT cbe_account_name, cbe_account_number,
                       telebirr_account_name, telebirr_account_number
                FROM admin_settings
                WHERE id = 1
                """
            )
            row = cur.fetchone()

    if row is None:
        # Shouldn't happen — init_db.py seeds this row — but degrade to
        # "nothing configured yet" rather than a 500 if it's ever missing.
        return PaymentInfoResponse()

    return PaymentInfoResponse(
        cbe_account_name=row[0],
        cbe_account_number=row[1],
        telebirr_account_name=row[2],
        telebirr_account_number=row[3],
    )


class ReceiptSubmitRequest(BaseModel):
    receipt_url: str = Field(..., min_length=1, max_length=2048)


class ReceiptSubmitResponse(BaseModel):
    id: str
    product_id: str
    receipt_url: str


@app.post(
    "/products/{product_id}/receipt",
    response_model=ReceiptSubmitResponse,
    status_code=201,
)
def submit_receipt(product_id: str, payload: ReceiptSubmitRequest) -> ReceiptSubmitResponse:
    """
    Public, no authentication — a buyer pastes their payment receipt URL
    here after paying NATRA's CBE/Telebirr account (see GET /payment-info).

    Task 13 scope is storage only: the URL is recorded in `receipts` and
    nothing more. No verification, no amount/status checks, no duplicate
    detection, and no order/sale record — all of that is explicitly
    deferred to Phase 2 (CLAUDE_MASTER_PROMPT.md sections 5 and 9). A
    product can receive more than one submission (e.g. a buyer re-pastes
    a corrected link); that's fine and by design at this stage.
    """
    normalized_id = product_id.strip().upper()
    if len(normalized_id) != 32 or not all(c in "0123456789ABCDEF" for c in normalized_id):
        # Not a well-formed RAW(16) hex id — mirrors the same guard used
        # in get_product_detail so a malformed id 404s cleanly instead of
        # reaching HEXTORAW and raising an Oracle error.
        raise HTTPException(status_code=404, detail="Product not found")

    receipt_url = payload.receipt_url.strip()
    if not receipt_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="receipt_url must be a valid URL")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM products WHERE id = HEXTORAW(:product_id)",
                product_id=normalized_id,
            )
            (product_count,) = cur.fetchone()
            if product_count == 0:
                raise HTTPException(status_code=404, detail="Product not found")

            id_out = cur.var(str)
            cur.execute(
                """
                INSERT INTO receipts (product_id, receipt_url)
                VALUES (HEXTORAW(:product_id), :receipt_url)
                RETURNING RAWTOHEX(id) INTO :id_out
                """,
                product_id=normalized_id,
                receipt_url=receipt_url,
                id_out=id_out,
            )
            conn.commit()
            receipt_id = id_out.getvalue()[0]

    return ReceiptSubmitResponse(
        id=receipt_id,
        product_id=normalized_id,
        receipt_url=receipt_url,
    )


class ReceiptVerifyResponse(BaseModel):
    id: str
    product_id: str
    status: str
    reason: str | None = None
    transaction_ref: str | None = None
    verified_amount: float | None = None
    provider: str | None = None


REASON_FETCH_FAILED = "fetch_failed"
REASON_UNSUPPORTED_PROVIDER = "unsupported_provider"


def _determine_provider(receipt_url: str) -> str | None:
    """
    Decide which provider a receipt URL belongs to, purely from its
    hostname — reusing `cbe.CBE_RECEIPT_HOST` /
    `telebirr.TELEBIRR_RECEIPT_HOST` directly rather than duplicating
    the host strings here, so this can never drift out of sync with
    what `_validate_cbe_url()` / `_validate_telebirr_url()` actually
    accept. Returns `None` for any other host (also covers a malformed
    URL, since `urlparse(...).hostname` is `None` for one).
    """
    hostname = urlparse(receipt_url).hostname
    if hostname == CBE_RECEIPT_HOST:
        return PROVIDER_CBE
    if hostname == TELEBIRR_RECEIPT_HOST:
        return PROVIDER_TELEBIRR
    return None


def _reject_receipt(
    receipt_id: str,
    product_id: str,
    reason: str,
    provider: str | None,
    transaction_ref: str | None = None,
) -> ReceiptVerifyResponse:
    """
    Shared write path for every "this receipt did not verify" outcome.
    Always writes status='rejected'; `transaction_ref`/`provider` are
    recorded when known (useful for support/debugging later) but never
    put this row at risk of the `uq_receipts_verified_txn` index (Task
    25) — that index only constrains `'verified'` rows, so a rejected
    receipt's `transaction_ref` can never collide with a genuinely
    verified one, even if two different buyers' rejected attempts
    happen to share a reference.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE receipts
                SET status = 'rejected',
                    transaction_ref = :transaction_ref,
                    provider = :provider
                WHERE id = HEXTORAW(:receipt_id)
                """,
                transaction_ref=transaction_ref,
                provider=provider,
                receipt_id=receipt_id,
            )
            conn.commit()

    return ReceiptVerifyResponse(
        id=receipt_id,
        product_id=product_id,
        status="rejected",
        reason=reason,
        transaction_ref=transaction_ref,
        provider=provider,
    )


def _get_commission_rate(cur) -> float:
    """
    Task 30. Reads the single `admin_settings` row's `commission_rate`
    (Task 29). That row always exists by the time this runs (seeded by
    `init_db.py`) and the column is `NOT NULL`, so no "not configured"
    fallback is needed here the way GET /payment-info needs one for the
    nullable CBE/Telebirr fields.
    """
    cur.execute("SELECT commission_rate FROM admin_settings WHERE id = 1")
    (rate,) = cur.fetchone()
    return rate


def _record_sale(cur, *, receipt_id: str, product_id: str, seller_id: str, gross_amount: float) -> None:
    """
    Task 30. Inserts the one `sales` row for a receipt the moment it's
    written `status = 'verified'` — called from the same cursor/
    transaction as that UPDATE (see `verify_receipt()`) so the two can
    never diverge. Snapshots the *current* `commission_rate` onto the
    row rather than referencing `admin_settings` live, so a later change
    to the rate never rewrites what a past sale actually earned.
    Rounds to 2 decimals throughout, matching every money column's
    `NUMBER(12,2)` precision and `validation.py`'s existing convention
    for this codebase (plain floats, not Decimal).
    """
    commission_rate = _get_commission_rate(cur)
    gross_amount = round(gross_amount, 2)
    commission_amount = round(gross_amount * commission_rate / 100, 2)
    seller_payable = round(gross_amount - commission_amount, 2)
    cur.execute(
        """
        INSERT INTO sales (
            receipt_id, product_id, seller_id,
            gross_amount, commission_rate, commission_amount, seller_payable
        ) VALUES (
            HEXTORAW(:receipt_id), HEXTORAW(:product_id), HEXTORAW(:seller_id),
            :gross_amount, :commission_rate, :commission_amount, :seller_payable
        )
        """,
        receipt_id=receipt_id,
        product_id=product_id,
        seller_id=seller_id,
        gross_amount=gross_amount,
        commission_rate=commission_rate,
        commission_amount=commission_amount,
        seller_payable=seller_payable,
    )


@app.post("/receipts/{receipt_id}/verify", response_model=ReceiptVerifyResponse)
def verify_receipt(receipt_id: str) -> ReceiptVerifyResponse:
    """
    Task 26: the first endpoint that actually wires together fetching
    (Tasks 18-23), amount validation (Task 24), and duplicate
    protection (Task 25) into one pipeline, given a receipt a buyer
    already submitted via POST /products/{product_id}/receipt (Task
    13).

    Public, no auth — mirrors the receipt-submission endpoint; a buyer
    triggers verification of their own receipt, no seller/admin action
    is involved. Decision made explicitly here (left open in
    CURRENT_STATUS.md before this task): verification is a separate,
    buyer-triggered step rather than run inline during submission —
    this keeps Task 13 unchanged and keeps this pipeline independently
    retryable (e.g. if the buyer pasted the receipt URL before the
    provider's page had fully processed the transaction).

    Idempotent for a receipt that's already `'verified'`: returns the
    stored result without re-fetching or re-running any check, rather
    than re-running a pipeline whose own duplicate check (Task 25)
    would otherwise just find the receipt colliding with itself.

    Product delivery release (showing the buyer the seller's Drive
    link) is explicitly Task 27, not this task — this endpoint's job
    ends at writing `receipts.status`/`transaction_ref`/
    `verified_amount`/`provider`.
    """
    normalized_id = receipt_id.strip().upper()
    if len(normalized_id) != 32 or not all(c in "0123456789ABCDEF" for c in normalized_id):
        # Not a well-formed RAW(16) hex id — mirrors the same guard used
        # elsewhere so a malformed id 404s cleanly instead of reaching
        # HEXTORAW and raising an Oracle error.
        raise HTTPException(status_code=404, detail="Receipt not found")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT RAWTOHEX(product_id), receipt_url, status,
                       transaction_ref, verified_amount, provider
                FROM receipts
                WHERE id = HEXTORAW(:receipt_id)
                """,
                receipt_id=normalized_id,
            )
            receipt_row = cur.fetchone()

    if receipt_row is None:
        raise HTTPException(status_code=404, detail="Receipt not found")

    (
        product_id,
        receipt_url,
        current_status,
        stored_transaction_ref,
        stored_verified_amount,
        stored_provider,
    ) = receipt_row

    if current_status == "verified":
        return ReceiptVerifyResponse(
            id=normalized_id,
            product_id=product_id,
            status="verified",
            transaction_ref=stored_transaction_ref,
            verified_amount=stored_verified_amount,
            provider=stored_provider,
        )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT price, RAWTOHEX(seller_id) FROM products WHERE id = HEXTORAW(:product_id)",
                product_id=product_id,
            )
            product_row = cur.fetchone()

    if product_row is None:
        # Shouldn't happen — receipts.product_id has a FK to products —
        # but degrade to a clean 404 rather than a confusing 500.
        raise HTTPException(status_code=404, detail="Product not found")

    (expected_price, seller_id) = product_row

    provider = _determine_provider(receipt_url)
    if provider is None:
        return _reject_receipt(normalized_id, product_id, REASON_UNSUPPORTED_PROVIDER, provider=None)

    parse_fn = parse_cbe_receipt if provider == PROVIDER_CBE else parse_telebirr_receipt
    parsed = parse_fn(receipt_url)

    if not parsed.get("fetched"):
        return _reject_receipt(normalized_id, product_id, REASON_FETCH_FAILED, provider=provider)

    validation = validate_payment(provider, parsed, expected_price)
    if not validation["valid"]:
        return _reject_receipt(
            normalized_id,
            product_id,
            validation["reason"],
            provider=provider,
            transaction_ref=parsed.get("transaction_ref"),
        )

    transaction_ref = parsed.get("transaction_ref")
    if is_duplicate_transaction(transaction_ref, provider):
        return _reject_receipt(
            normalized_id,
            product_id,
            REASON_DUPLICATE_TRANSACTION,
            provider=provider,
            transaction_ref=transaction_ref,
        )

    paid_amount = validation["paid_amount"]
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE receipts
                SET status = 'verified',
                    transaction_ref = :transaction_ref,
                    verified_amount = :verified_amount,
                    provider = :provider
                WHERE id = HEXTORAW(:receipt_id)
                """,
                transaction_ref=transaction_ref,
                verified_amount=paid_amount,
                provider=provider,
                receipt_id=normalized_id,
            )
            _record_sale(
                cur,
                receipt_id=normalized_id,
                product_id=product_id,
                seller_id=seller_id,
                gross_amount=paid_amount,
            )
            conn.commit()

    return ReceiptVerifyResponse(
        id=normalized_id,
        product_id=product_id,
        status="verified",
        transaction_ref=transaction_ref,
        verified_amount=paid_amount,
        provider=provider,
    )


class ReceiptDeliveryResponse(BaseModel):
    receipt_id: str
    product_id: str
    drive_link: str


@app.get("/receipts/{receipt_id}/delivery", response_model=ReceiptDeliveryResponse)
def get_receipt_delivery(receipt_id: str) -> ReceiptDeliveryResponse:
    """
    Task 27: product delivery release — once a receipt is `'verified'`
    (Task 26), lets the buyer retrieve the seller's public Google Drive
    link for the product they paid for.

    Public, no auth — same access level as Task 13/26; the buyer holds
    no account, so the receipt id itself (a random RAW(16) GUID they
    already have from submitting the receipt) is the only credential.

    Decision made explicitly here (left open in Task 26's
    CURRENT_STATUS.md): this is a separate `GET` endpoint, not folded
    into `POST /receipts/{receipt_id}/verify`'s response. Reasons:
      - `verify_receipt()`'s own docstring already scoped its job to
        ending at writing `receipts.status`/etc — mixing delivery in
        would widen that endpoint's responsibility after the fact.
      - A `GET` here is naturally re-callable (the buyer can revisit
        the page and fetch their link again) without re-running or
        re-triggering any verification side effect, whereas the `POST`
        verify endpoint is about causing a state change.
      - It keeps the "only a verified receipt can ever reveal
        `drive_link`" rule enforced in exactly one place, rather than
        two response paths that both need to get it right.

    `drive_link` is **only** ever returned through this endpoint for a
    `'verified'` receipt. Every other product-facing endpoint
    (`GET /products`, `GET /products/{product_id}`) deliberately never
    includes it (see their own docstrings) — that invariant is
    unchanged by this task.
    """
    normalized_id = receipt_id.strip().upper()
    if len(normalized_id) != 32 or not all(c in "0123456789ABCDEF" for c in normalized_id):
        # Not a well-formed RAW(16) hex id — mirrors the same guard used
        # by verify_receipt() and elsewhere.
        raise HTTPException(status_code=404, detail="Receipt not found")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT RAWTOHEX(product_id), status
                FROM receipts
                WHERE id = HEXTORAW(:receipt_id)
                """,
                receipt_id=normalized_id,
            )
            receipt_row = cur.fetchone()

    if receipt_row is None:
        raise HTTPException(status_code=404, detail="Receipt not found")

    product_id, status = receipt_row

    if status != "verified":
        # Deliberately 403, not 404: the receipt does exist, it just
        # hasn't (yet, or won't ever) earn delivery — distinct from "no
        # such receipt id at all", and lets the frontend show "still
        # verifying" / "verification failed" rather than a generic
        # not-found. Never reveals drive_link either way.
        raise HTTPException(status_code=403, detail="Receipt is not verified")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT drive_link FROM products WHERE id = HEXTORAW(:product_id)",
                product_id=product_id,
            )
            product_row = cur.fetchone()

    if product_row is None:
        # Shouldn't happen — receipts.product_id has a FK to products —
        # but degrade to a clean 404 rather than a confusing 500.
        raise HTTPException(status_code=404, detail="Product not found")

    (drive_link,) = product_row

    return ReceiptDeliveryResponse(
        receipt_id=normalized_id,
        product_id=product_id,
        drive_link=drive_link,
    )


class AdminLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@app.post("/admin/login", response_model=AdminLoginResponse)
def login_admin(payload: AdminLoginRequest, request: Request) -> AdminLoginResponse:
    """
    Verify Master Admin credentials and return a JWT on success.

    There is exactly one Master Admin identity for NATRA. It is NOT a
    database row and there is no self-registration endpoint — the admin
    account is provisioned entirely via the ADMIN_EMAIL/ADMIN_PASSWORD_HASH
    environment variables (see backend/.env.example and ARCHITECTURE.md).
    ADMIN_PASSWORD_HASH must already be a hash produced by
    `security.hash_password()`, never a plain-text password.

    Returns the same generic "Invalid email or password" for a wrong email,
    a wrong password, or the admin account not being configured at all —
    mirrors POST /sellers/login's anti-enumeration behavior.

    Task 44: rate-limited per client IP the same way, before this
    behaves as it did before this task — this endpoint arguably matters
    more to protect, since there's exactly one Master Admin account to
    brute-force (vs. many seller accounts), so a successful guess here
    is a bigger blast radius. Uses its own separate `rate_limit_key`
    prefix ("admin_login") so an attacker hammering seller logins from
    one IP doesn't also exhaust that IP's admin-login attempt budget for
    a legitimate admin sharing it (or vice versa) — each endpoint keeps
    its own independent counter per IP.
    """
    limit_key = _rate_limit_key("admin_login", request)
    try:
        check_rate_limit(limit_key)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        )

    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_password_hash = os.environ.get("ADMIN_PASSWORD_HASH")
    if not admin_email or not admin_password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    submitted_email = payload.email.strip().lower()
    expected_email = admin_email.strip().lower()

    # Always run verify_password, even on an email mismatch, so a wrong
    # email doesn't short-circuit into a measurably faster response than a
    # wrong password (same care as POST /sellers/login's generic error).
    password_ok = verify_password(payload.password, admin_password_hash)
    if submitted_email != expected_email or not password_ok:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    try:
        token = create_admin_access_token(expected_email)
    except JWTConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return AdminLoginResponse(access_token=token)


def get_current_admin(authorization: str | None = Header(default=None)) -> str:
    """
    FastAPI dependency for admin-only endpoints. Verifies the
    `Authorization: Bearer <token>` header the same way
    `get_current_seller_id` does, but additionally requires the token's
    `role` claim to equal "admin" — so a seller's own valid JWT is
    correctly rejected here with 403 (authenticated, wrong role), not 401
    (not authenticated). Returns the admin's email (from the token's
    `email` claim).

    `get_current_seller_id` now applies the same role check in the other
    direction (Task 41), so both dependencies reject a wrong-role token
    with 403.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization[len("Bearer ") :].strip()
    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    except JWTConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return email


class AdminProductItem(BaseModel):
    id: str
    seller_id: str
    name: str
    price: float
    description: str
    thumbnail_ref: str | None = None
    drive_link: str


@app.get("/admin/products", response_model=list[AdminProductItem])
def list_all_products_admin(
    _admin_email: str = Depends(get_current_admin),
) -> list[AdminProductItem]:
    """
    Admin-only, platform-wide product listing. Protected by
    `get_current_admin` — the first endpoint to require role=="admin".

    Deliberately fuller than the buyer-facing GET /products: includes
    `seller_id` and `drive_link`, which buyers must never see before a
    verified purchase, but which the Master Admin needs for platform
    management (identifying which seller owns a product, moderating
    content). This is a read-only view — editing/deleting/publishing
    products is a later admin task, not part of Task 15.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT RAWTOHEX(id), RAWTOHEX(seller_id), name, price,
                       description, thumbnail_ref, drive_link
                FROM products
                ORDER BY created_at DESC
                """
            )
            rows = cur.fetchall()

    return [
        AdminProductItem(
            id=row[0],
            seller_id=row[1],
            name=row[2],
            price=row[3],
            description=row[4] or "",
            thumbnail_ref=row[5],
            drive_link=row[6],
        )
        for row in rows
    ]


class AdminSettingsUpdateRequest(BaseModel):
    cbe_account_name: str | None = Field(default=None, max_length=255)
    cbe_account_number: str | None = Field(default=None, max_length=64)
    telebirr_account_name: str | None = Field(default=None, max_length=255)
    telebirr_account_number: str | None = Field(default=None, max_length=64)
    commission_rate: float | None = Field(default=None, ge=0, le=100)


class AdminSettingsResponse(PaymentInfoResponse):
    """
    Task 31. Everything `PaymentInfoResponse` has, plus `commission_rate`
    — admin-only (GET/PUT /admin/settings), never returned from the
    public GET /payment-info, since a buyer has no need to see NATRA's
    commission rate.
    """
    commission_rate: float


def _fetch_admin_settings_row(cur):
    cur.execute(
        """
        SELECT cbe_account_name, cbe_account_number,
               telebirr_account_name, telebirr_account_number,
               commission_rate
        FROM admin_settings
        WHERE id = 1
        """
    )
    return cur.fetchone()


@app.get("/admin/settings", response_model=AdminSettingsResponse)
def get_admin_settings(_admin_email: str = Depends(get_current_admin)) -> AdminSettingsResponse:
    """
    Task 31. Admin-only read of the full `admin_settings` row, including
    `commission_rate` (Task 29) — previously only settable/readable via
    direct SQL, since PUT /admin/settings (Task 16) predates that column
    and the public GET /payment-info (Task 12) intentionally never
    returns it. Same singleton row as both of those endpoints.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            row = _fetch_admin_settings_row(cur)

    if row is None:
        # Shouldn't happen — init_db.py seeds this row, and
        # commission_rate is NOT NULL — but this mirrors the same
        # degrade-rather-than-500 behavior as GET /payment-info.
        return AdminSettingsResponse(commission_rate=0)

    return AdminSettingsResponse(
        cbe_account_name=row[0],
        cbe_account_number=row[1],
        telebirr_account_name=row[2],
        telebirr_account_number=row[3],
        commission_rate=row[4],
    )


@app.put("/admin/settings", response_model=AdminSettingsResponse)
def update_admin_settings(
    payload: AdminSettingsUpdateRequest,
    _admin_email: str = Depends(get_current_admin),
) -> AdminSettingsResponse:
    """
    Admin-only write endpoint for NATRA's own CBE/Telebirr payment account
    info — the write counterpart to the public, read-only GET
    /payment-info (Task 12). Updates the singleton `admin_settings` row
    (id=1), which init_db.py seeds all-NULL and which, until now, could
    only be changed via a direct SQL UPDATE.

    All four payment fields are optional and independent: any field
    omitted (or sent as null) leaves that column unchanged rather than
    clearing it, so the Master Admin can set just the CBE info first and
    add Telebirr later without resending everything. To actually clear a
    field once set, send an empty string "" (stored as-is; GET
    /payment-info already treats NULL as "not configured", and an empty
    string reads the same way to a buyer).

    Task 31: `commission_rate` follows the same "omit = leave unchanged"
    convention, bounded to [0, 100] by the request model. Unlike the four
    payment fields it can never be cleared to "unset" (the column is
    `NOT NULL`) — there is no empty-string equivalent for a rate; sending
    it always means "change it to this value".

    Returns the full updated settings, including `commission_rate` (see
    `AdminSettingsResponse` — a superset of GET /payment-info's shape).
    """
    fields = {
        "cbe_account_name": payload.cbe_account_name,
        "cbe_account_number": payload.cbe_account_number,
        "telebirr_account_name": payload.telebirr_account_name,
        "telebirr_account_number": payload.telebirr_account_number,
    }
    # Strip strings but keep None as None (None means "leave unchanged").
    fields = {k: (v.strip() if v is not None else None) for k, v in fields.items()}

    set_clauses = [f"{column} = :{column}" for column, value in fields.items() if value is not None]
    bind_params = {k: v for k, v in fields.items() if v is not None}

    if payload.commission_rate is not None:
        set_clauses.append("commission_rate = :commission_rate")
        bind_params["commission_rate"] = payload.commission_rate

    with get_connection() as conn:
        with conn.cursor() as cur:
            if set_clauses:
                cur.execute(
                    f"""
                    UPDATE admin_settings
                    SET {", ".join(set_clauses)}, updated_at = SYSTIMESTAMP
                    WHERE id = 1
                    """,
                    **bind_params,
                )
                conn.commit()

            row = _fetch_admin_settings_row(cur)

    if row is None:
        # Shouldn't happen — init_db.py seeds this row — but degrade to
        # "nothing configured" rather than a 500, mirroring GET
        # /payment-info's behavior for the same edge case.
        return AdminSettingsResponse(commission_rate=0)

    return AdminSettingsResponse(
        cbe_account_name=row[0],
        cbe_account_number=row[1],
        telebirr_account_name=row[2],
        telebirr_account_number=row[3],
        commission_rate=row[4],
    )


class SettlementCreateRequest(BaseModel):
    seller_id: str = Field(..., min_length=32, max_length=32)
    amount: float = Field(..., gt=0)


class SettlementResponse(BaseModel):
    id: str
    seller_id: str
    amount: float
    status: str
    created_at: str
    completed_at: str | None = None


@app.post("/admin/settlements", response_model=SettlementResponse, status_code=201)
def create_settlement(
    payload: SettlementCreateRequest,
    _admin_email: str = Depends(get_current_admin),
) -> SettlementResponse:
    """
    Task 34. Admin-only — records that NATRA settled (or intends to
    settle) `amount` to `seller_id`. NATRA still pays the seller
    manually, outside this system, to the payout account the seller set
    via PUT /sellers/payment-methods (Task 33); this endpoint's job is
    only to record that a settlement happened/is happening, not to move
    any money itself.

    Every new settlement starts `status = 'pending'` — nothing in this
    task transitions it to `'completed'` (that's a later Phase 3 task,
    admin settlement management).

    Task 42: `amount` is now checked against the seller's unsettled
    balance — `seller_payable_total - settled_total`, the exact same
    formula `GET /sellers/earnings` (Task 36) already reports as
    `unsettled_total`, using the same `'completed'`-only definition of
    `settled_total` (a `'pending'` settlement isn't "settled" yet, so it
    doesn't reduce the balance available to record a new one against).
    An `amount` greater than that balance is rejected with `422` before
    any row is inserted — it would make `unsettled_total` go negative,
    the exact gap flagged in this docstring since Task 34 and in
    `GET /sellers/earnings`' docstring since Task 36. Reconciling
    multiple simultaneous `'pending'` settlements against each other
    (e.g. two pending settlements that are each individually within
    balance but would together overdraw it once both complete) is left
    out of scope for this task — this check only looks at
    already-`'completed'` settlements, matching what `unsettled_total`
    itself currently measures.
    """
    normalized_seller_id = payload.seller_id.strip().upper()
    if len(normalized_seller_id) != 32 or not all(
        c in "0123456789ABCDEF" for c in normalized_seller_id
    ):
        # Not a well-formed RAW(16) hex id — mirrors the same guard used
        # elsewhere so a malformed id 404s cleanly instead of reaching
        # HEXTORAW and raising an Oracle error.
        raise HTTPException(status_code=404, detail="Seller not found")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM sellers WHERE id = HEXTORAW(:seller_id)",
                seller_id=normalized_seller_id,
            )
            (seller_count,) = cur.fetchone()
            if seller_count == 0:
                raise HTTPException(status_code=404, detail="Seller not found")

            cur.execute(
                """
                SELECT SUM(seller_payable)
                FROM sales
                WHERE seller_id = HEXTORAW(:seller_id)
                """,
                seller_id=normalized_seller_id,
            )
            (payable_sum,) = cur.fetchone()

            cur.execute(
                """
                SELECT SUM(amount)
                FROM settlements
                WHERE seller_id = HEXTORAW(:seller_id)
                  AND status = 'completed'
                """,
                seller_id=normalized_seller_id,
            )
            (settled_sum,) = cur.fetchone()

            payable_total = payable_sum or 0.0
            settled_total = settled_sum or 0.0
            unsettled_total = round(payable_total - settled_total, 2)

            if round(payload.amount, 2) > unsettled_total:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Amount exceeds seller's unsettled balance "
                        f"({unsettled_total:.2f})"
                    ),
                )

            id_out = cur.var(str)
            cur.execute(
                """
                INSERT INTO settlements (seller_id, amount)
                VALUES (HEXTORAW(:seller_id), :amount)
                RETURNING RAWTOHEX(id) INTO :id_out
                """,
                seller_id=normalized_seller_id,
                amount=payload.amount,
                id_out=id_out,
            )
            conn.commit()
            settlement_id = id_out.getvalue()[0]

            cur.execute(
                """
                SELECT status, created_at, completed_at
                FROM settlements
                WHERE id = HEXTORAW(:settlement_id)
                """,
                settlement_id=settlement_id,
            )
            status, created_at, completed_at = cur.fetchone()

    return SettlementResponse(
        id=settlement_id,
        seller_id=normalized_seller_id,
        amount=payload.amount,
        status=status,
        created_at=str(created_at),
        completed_at=str(completed_at) if completed_at else None,
    )


@app.get("/admin/settlements", response_model=list[SettlementResponse])
def list_settlements(
    _admin_email: str = Depends(get_current_admin),
) -> list[SettlementResponse]:
    """
    Task 34. Admin-only, platform-wide settlement listing — every
    settlement recorded via POST /admin/settlements, across all
    sellers, newest first. No per-seller filter yet (a seller's own
    settlement history view, if wanted, would be a separate future
    task, mirroring how GET /sellers/earnings is seller-only and
    GET /admin/products is the admin-wide counterpart to
    GET /products/mine).
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT RAWTOHEX(id), RAWTOHEX(seller_id), amount, status,
                       created_at, completed_at
                FROM settlements
                ORDER BY created_at DESC
                """
            )
            rows = cur.fetchall()

    return [
        SettlementResponse(
            id=row[0],
            seller_id=row[1],
            amount=row[2],
            status=row[3],
            created_at=str(row[4]),
            completed_at=str(row[5]) if row[5] else None,
        )
        for row in rows
    ]


@app.post("/admin/settlements/{settlement_id}/complete", response_model=SettlementResponse)
def complete_settlement(
    settlement_id: str,
    _admin_email: str = Depends(get_current_admin),
) -> SettlementResponse:
    """
    Task 35. Admin-only — marks a settlement `'completed'` and stamps
    `completed_at`, the transition Task 34 deliberately left out. The
    admin calls this only after actually paying the seller manually,
    outside this system, to the payout account from Task 33 — this
    endpoint itself moves no money, it just records that the payout
    already happened.

    Idempotent for a settlement that's already `'completed'`: returns
    the stored result unchanged rather than re-running the update or
    erroring, mirroring POST /receipts/{receipt_id}/verify's shape for
    the same "already in the target state" case.
    """
    normalized_id = settlement_id.strip().upper()
    if len(normalized_id) != 32 or not all(c in "0123456789ABCDEF" for c in normalized_id):
        # Not a well-formed RAW(16) hex id — mirrors the same guard used
        # elsewhere so a malformed id 404s cleanly instead of reaching
        # HEXTORAW and raising an Oracle error.
        raise HTTPException(status_code=404, detail="Settlement not found")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT RAWTOHEX(seller_id), amount, status, created_at, completed_at
                FROM settlements
                WHERE id = HEXTORAW(:settlement_id)
                """,
                settlement_id=normalized_id,
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Settlement not found")

    seller_id, amount, status, created_at, completed_at = row

    if status == "completed":
        return SettlementResponse(
            id=normalized_id,
            seller_id=seller_id,
            amount=amount,
            status=status,
            created_at=str(created_at),
            completed_at=str(completed_at) if completed_at else None,
        )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE settlements
                SET status = 'completed', completed_at = SYSTIMESTAMP
                WHERE id = HEXTORAW(:settlement_id)
                """,
                settlement_id=normalized_id,
            )
            conn.commit()

            cur.execute(
                """
                SELECT RAWTOHEX(seller_id), amount, status, created_at, completed_at
                FROM settlements
                WHERE id = HEXTORAW(:settlement_id)
                """,
                settlement_id=normalized_id,
            )
            seller_id, amount, status, created_at, completed_at = cur.fetchone()

    return SettlementResponse(
        id=normalized_id,
        seller_id=seller_id,
        amount=amount,
        status=status,
        created_at=str(created_at),
        completed_at=str(completed_at) if completed_at else None,
    )


class AdminReportsResponse(BaseModel):
    total_sales: int
    gross_amount_total: float
    commission_total: float
    seller_payable_total: float
    settled_total: float
    unsettled_total: float


@app.get("/admin/reports", response_model=AdminReportsResponse)
def get_admin_reports(
    _admin_email: str = Depends(get_current_admin),
) -> AdminReportsResponse:
    """
    Task 37. Admin-only, platform-wide financial reporting — the first
    endpoint that aggregates `sales`/`settlements` across every seller
    rather than one. Same six fields and the same two queries as
    GET /sellers/earnings (Task 32/36), just without a `seller_id`
    filter: `settled_total` sums every `'completed'` settlement
    platform-wide, and `unsettled_total` is `seller_payable_total -
    settled_total`, not clamped to zero for the same reason it isn't in
    GET /sellers/earnings (see that endpoint's docstring) — nothing yet
    stops an admin from recording more in completed settlements than a
    seller actually earned, and a negative total here is the
    platform-wide version of that same early-warning signal.

    `SUM(...)` over zero rows returns Oracle NULL, not 0 — coalesced to
    0.0 here so an empty platform (no sales yet) gets a clean all-zero
    response, same convention as GET /sellers/earnings.

    Read-only, no new tables/columns. A per-seller breakdown (grouping
    this same query by `seller_id`) is a deliberately separate, later
    task — see this file's module docstring.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*),
                       SUM(gross_amount),
                       SUM(commission_amount),
                       SUM(seller_payable)
                FROM sales
                """
            )
            sales_row = cur.fetchone()

            cur.execute(
                """
                SELECT SUM(amount)
                FROM settlements
                WHERE status = 'completed'
                """
            )
            (settled_sum,) = cur.fetchone()

    total_sales, gross_total, commission_total, payable_total = sales_row
    payable_total = payable_total or 0.0
    settled_total = settled_sum or 0.0
    unsettled_total = round(payable_total - settled_total, 2)

    return AdminReportsResponse(
        total_sales=total_sales or 0,
        gross_amount_total=gross_total or 0.0,
        commission_total=commission_total or 0.0,
        seller_payable_total=payable_total,
        settled_total=settled_total,
        unsettled_total=unsettled_total,
    )


class AdminSellerReportItem(BaseModel):
    seller_id: str
    total_sales: int
    gross_amount_total: float
    commission_total: float
    seller_payable_total: float
    settled_total: float
    unsettled_total: float


@app.get("/admin/reports/by-seller", response_model=list[AdminSellerReportItem])
def get_admin_reports_by_seller(
    _admin_email: str = Depends(get_current_admin),
) -> list[AdminSellerReportItem]:
    """
    Task 38. Admin-only — the per-seller breakdown GET /admin/reports
    (Task 37) deliberately left out. Same fields, same two-query shape,
    but `GROUP BY seller_id` instead of one platform-wide sum, so
    summing every row this endpoint returns reproduces exactly what
    GET /admin/reports returns as a single row.

    Only sellers with at least one row in `sales` appear: the first
    query groups `sales` by `seller_id`, so a seller who has never made
    a sale has no group to appear in. (This mirrors GET /admin/reports
    itself returning all-zero for an empty platform — there's simply no
    seller row to report for one with nothing sold yet.)

    The second query aggregates `settlements` (`'completed'` only) by
    `seller_id` the same way GET /sellers/earnings' `settled_total` does
    for one seller; results are merged in Python by seller_id since
    Oracle has no seller with sales but zero completed settlements to
    LEFT JOIN against cleanly without extra NULL-handling in SQL — a
    seller present in the sales grouping but absent from the settlements
    grouping simply gets `settled_total=0.0`, same convention as
    `SUM(...)` over zero matching rows elsewhere in this file.

    `unsettled_total` is `seller_payable_total - settled_total` per
    seller, not clamped to zero — same reasoning, and same pre-existing
    gap, as GET /sellers/earnings (Task 36) and GET /admin/reports
    (Task 37): nothing yet stops an admin from over-settling a specific
    seller, and this is where that becomes visible per seller rather
    than only in the platform-wide total.

    Ordered by `unsettled_total` descending — sellers NATRA owes the
    most to (or has most over-settled, at the negative end) surface
    first, which is the ordering most useful to an admin scanning this
    list; alphabetical/hex `seller_id` order would carry no meaning.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT RAWTOHEX(seller_id),
                       COUNT(*),
                       SUM(gross_amount),
                       SUM(commission_amount),
                       SUM(seller_payable)
                FROM sales
                GROUP BY seller_id
                """
            )
            sales_rows = cur.fetchall()

            cur.execute(
                """
                SELECT RAWTOHEX(seller_id), SUM(amount)
                FROM settlements
                WHERE status = 'completed'
                GROUP BY seller_id
                """
            )
            settled_rows = cur.fetchall()

    settled_by_seller = {row[0]: row[1] or 0.0 for row in settled_rows}

    items = []
    for seller_id, total_sales, gross_total, commission_total, payable_total in sales_rows:
        payable_total = payable_total or 0.0
        settled_total = settled_by_seller.get(seller_id, 0.0)
        unsettled_total = round(payable_total - settled_total, 2)
        items.append(
            AdminSellerReportItem(
                seller_id=seller_id,
                total_sales=total_sales or 0,
                gross_amount_total=gross_total or 0.0,
                commission_total=commission_total or 0.0,
                seller_payable_total=payable_total,
                settled_total=settled_total,
                unsettled_total=unsettled_total,
            )
        )

    items.sort(key=lambda item: item.unsettled_total, reverse=True)
    return items
