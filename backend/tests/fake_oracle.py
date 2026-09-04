"""
Task 72: a small in-memory stand-in for `db.get_connection()`.

There's no real Oracle instance available in CI/sandbox environments,
and the actual queries in `app/main.py` and `app/otp.py` use
Oracle-specific syntax (`RAWTOHEX`, `HEXTORAW`, `SYS_GUID()`,
`RETURNING ... INTO`, named `:bind` parameters via `cur.var()`) that a
generic SQLite swap-in couldn't run unmodified. Rather than either
skipping DB-touching tests entirely or standing up a real Oracle
instance just for CI, this fakes only the *shapes* of the handful of
queries this codebase actually issues against the `sellers` and
`otp_codes` tables — enough to exercise the real endpoint code in
`main.py` end to end (real password hashing, real OTP hashing/expiry
logic in `otp.py`, real JWT issuance) without a real database.

Task 73 extends this with `products` and the singleton `admin_settings`
row, following the same pattern, for the Products endpoints suite
(`POST /products`, `GET /products/mine`, `GET /products`,
`GET /products/{id}`, `GET /payment-info`).

Task 74 extends it further with `sales`/`settlements` (read-only —
seeded directly by a test via `store.sales`/`store.settlements`, since
no in-scope endpoint writes them yet) and the four payment-method
columns on `sellers` (Task 33), for `GET /sellers/earnings` and
`GET`/`PUT /sellers/payment-methods`.

Task 75 extends it once more with a `receipts` table (the full
submit -> verify -> reject/verify -> delivery lifecycle) and two new
`products` query shapes (`SELECT COUNT(*) ... WHERE id = ...` for the
submit endpoint's existence check, and `SELECT price,
RAWTOHEX(seller_id) ...` for the verify endpoint's price lookup),
`admin_settings.commission_rate` (previously deliberately left
unimplemented by Task 74 — see that task's CURRENT_STATUS.md note —
now needed for real by `_record_sale()`), and a real `INSERT INTO
sales` (as opposed to Task 74's seed-only `SalesRow` usage). This
task does **not** fake Playwright/`browser.py`/`cbe.py`/`telebirr.py`
directly — `main.py` imports `parse_cbe_receipt`/
`parse_telebirr_receipt` by name (`from .cbe import ... parse_cbe_receipt`),
so the test suite monkeypatches `app.main.parse_cbe_receipt` /
`app.main.parse_telebirr_receipt` themselves (see
`test_receipts.py`'s `_patch_provider` fixture), the same
already-established pattern `conftest.py` uses for the Brevo email
functions. That keeps this file scoped to the database layer only.

Task 77 gives `SettlementRow` a real `id_hex`/`created_at`/
`completed_at` (all defaulted, so Task 74's existing seed-only
`SettlementRow(seller_id_hex=..., amount=..., status=...)` calls are
unaffected) and adds the query shapes `POST`/`GET /admin/settlements`,
`POST /admin/settlements/{id}/complete`, `GET /admin/reports`, and
`GET /admin/reports/by-seller` actually issue: a seller-existence
check against `sellers` by id, a single-column `SUM(seller_payable)`
against `sales` for one seller (`POST /admin/settlements`' over-payment
guard — distinct from Task 74's 4-column `SUM(...)` aggregate used by
`GET /sellers/earnings`), a real `INSERT INTO settlements`, a
platform-wide (no `seller_id` filter) version of both the `sales` and
`settlements` aggregates, and `GROUP BY seller_id` versions of each for
the per-seller report. `store.sales`/`store.settlements` remain plain
Python lists — Task 74's seed-direct tests and this task's real-insert
tests both work against the same underlying store.

This is deliberately narrow: it recognizes queries by a distinctive
substring, not a SQL parser, and only implements the exact statements
`grep -n "cur.execute"` finds in `app/main.py` / `app/otp.py` as of
Task 74. If a future task adds a new query against these tables, this
file needs a matching branch added — `_unhandled_sql()` raises loudly
(rather than silently no-op'ing) specifically so a forgotten branch
fails a test instead of passing one that never actually ran real
logic.
"""

from __future__ import annotations

import re
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

import oracledb


def _collapse(sql: str) -> str:
    """Normalize whitespace so substring checks don't care about indentation."""
    return re.sub(r"\s+", " ", sql).strip()


@dataclass
class FakeVar:
    """Stands in for `cursor.var(str)` — an OUT bind populated by execute()."""

    value: Any = None

    def getvalue(self) -> list[Any]:
        return [self.value]


@dataclass
class SellerRow:
    id_hex: str
    email: str
    password_hash: str
    email_verified: str = "N"
    # Task 33 — seller's own payout account, set via
    # PUT /sellers/payment-methods. All-NULL until the seller configures
    # them; never the account a buyer pays into (that's admin_settings).
    cbe_account_name: str | None = None
    cbe_account_number: str | None = None
    telebirr_account_name: str | None = None
    telebirr_account_number: str | None = None


@dataclass
class OtpRow:
    id_hex: str
    email: str
    purpose: str
    code_hash: str
    expires_at: Any
    attempts: int = 0


@dataclass
class ProductRow:
    id_hex: str
    seller_id_hex: str
    name: str
    price: float
    description: str
    drive_link: str
    thumbnail_ref: str | None = None


@dataclass
class SalesRow:
    """Task 74 — populated directly by a test's `store.sales.append(...)`
    rather than through any endpoint: no in-scope endpoint creates a
    `sales` row (that's `_record_sale()`, part of the receipts-flow
    Task 75), so tests set up known aggregation inputs this way, the
    same "arrange" step a real DB-backed test would do with a direct
    INSERT.

    Task 75 adds `receipt_id_hex`/`product_id_hex`/`commission_rate` —
    all `None` by default so Task 74's existing seed calls (which never
    pass them) are unaffected — populated for real now by
    `_insert_sale()`, the fake backing `_record_sale()`'s real
    `INSERT INTO sales`."""

    seller_id_hex: str
    gross_amount: float
    commission_amount: float
    seller_payable: float
    receipt_id_hex: str | None = None
    product_id_hex: str | None = None
    commission_rate: float | None = None


@dataclass
class ReceiptRow:
    """Task 75 — backs the `receipts` table across its full lifecycle:
    `POST /products/{product_id}/receipt` (Task 13, insert — `status`
    starts `None`/NULL, matching `schema.sql`'s `status` column having
    no `DEFAULT`), `POST /receipts/{receipt_id}/verify` (Task 26,
    updates to `'verified'` or `'rejected'`), and
    `GET /receipts/{receipt_id}/delivery` (Task 27, read-only)."""

    id_hex: str
    product_id_hex: str
    receipt_url: str
    status: str | None = None
    transaction_ref: str | None = None
    verified_amount: float | None = None
    provider: str | None = None


@dataclass
class SettlementRow:
    """Task 74 — same as `SalesRow`: originally no in-scope endpoint
    created one, so tests seeded `store.settlements` directly.

    Task 77 adds `id_hex`/`created_at`/`completed_at` — all defaulted,
    so Task 74's existing direct-seed calls (which never pass them)
    keep working — now that `POST /admin/settlements` performs a real
    `INSERT` and `GET /admin/settlements` / `POST .../complete` need a
    real id and timestamps to return. `created_at` defaults to "now" at
    construction time so insertion order (used for "newest first",
    same convention as `products`/`receipts`) lines up with real
    chronological order for both seeded and inserted rows."""

    seller_id_hex: str
    amount: float
    status: str = "pending"
    id_hex: str = field(default_factory=lambda: uuid.uuid4().hex.upper())
    created_at: Any = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Any = None


@dataclass
class AdminSettingsRow:
    """Mirrors the singleton `admin_settings` row (id=1). `init_db.py`
    seeds the four CBE/Telebirr fields all-NULL; `commission_rate` is
    `NUMBER(5,2) DEFAULT 10.00 NOT NULL` per `schema.sql`, so it
    defaults here to `10.00` too rather than `None` — Task 73's
    `GET /payment-info` never selects this column, but Task 75's
    `_get_commission_rate()` (called from `_record_sale()`) does."""

    cbe_account_name: str | None = None
    cbe_account_number: str | None = None
    telebirr_account_name: str | None = None
    telebirr_account_number: str | None = None
    commission_rate: float = 10.00


@dataclass
class FakeOracleStore:
    """Shared backing store for a single test — one instance per test."""

    sellers: dict[str, SellerRow] = field(default_factory=dict)  # keyed by email
    otp_codes: dict[str, OtpRow] = field(default_factory=dict)  # keyed by id_hex
    # Keyed by id_hex; insertion order doubles as `created_at` order since
    # every real query against this table orders by created_at DESC and
    # tests only ever insert in real chronological order.
    products: dict[str, ProductRow] = field(default_factory=dict)
    # Seeded all-NULL by default, matching init_db.py. A test can set this
    # to None to exercise GET /payment-info's "row missing" degrade path.
    admin_settings: AdminSettingsRow | None = field(default_factory=AdminSettingsRow)
    # Task 74 — see SalesRow/SettlementRow docstrings: no in-scope
    # endpoint populates these, tests seed them directly.
    sales: list[SalesRow] = field(default_factory=list)
    settlements: list[SettlementRow] = field(default_factory=list)
    # Task 75 — keyed by id_hex, same convention as `products`; fully
    # populated through the real endpoints (submit/verify/reject), not
    # seeded directly.
    receipts: dict[str, ReceiptRow] = field(default_factory=dict)


class FakeCursor:
    def __init__(self, store: FakeOracleStore):
        self._store = store
        self._result: list[tuple] | None = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None

    def var(self, _type: Any) -> FakeVar:
        return FakeVar()

    def execute(self, sql: str, **kwargs: Any) -> None:
        s = _collapse(sql)
        self._result = None

        if "INSERT INTO sellers" in s:
            self._insert_seller(**kwargs)
        elif "RAWTOHEX(id), password_hash, email_verified FROM sellers" in s:
            self._select_seller_for_login(**kwargs)
        elif "UPDATE sellers SET email_verified" in s:
            self._update_seller_verified(**kwargs)
        elif "SELECT email_verified FROM sellers" in s:
            self._select_seller_verified_flag(**kwargs)
        elif "SELECT 1 FROM sellers" in s:
            self._select_seller_exists(**kwargs)
        elif "UPDATE sellers SET password_hash" in s:
            self._update_seller_password(**kwargs)
        elif "UPDATE sellers SET" in s and (
            "cbe_account" in s or "telebirr_account" in s
        ):
            # Dynamic column list (PUT /sellers/payment-methods only sets
            # the columns actually provided) — the set of bound kwargs
            # varies, hence **fields rather than named params.
            self._update_seller_payment_methods(**kwargs)
        elif (
            "cbe_account_name, cbe_account_number, "
            "telebirr_account_name, telebirr_account_number "
            "FROM sellers" in s
        ):
            self._select_seller_payment_methods(**kwargs)
        elif "DELETE FROM otp_codes WHERE email" in s:
            self._delete_otp_by_email_purpose(**kwargs)
        elif "INSERT INTO otp_codes" in s:
            self._insert_otp(**kwargs)
        elif "RAWTOHEX(id), code_hash, expires_at, attempts" in s:
            self._select_otp(**kwargs)
        elif "UPDATE otp_codes SET attempts" in s:
            self._increment_otp_attempts(**kwargs)
        elif "DELETE FROM otp_codes WHERE id" in s:
            self._delete_otp_by_id(**kwargs)
        elif "INSERT INTO products" in s:
            self._insert_product(**kwargs)
        elif "FROM products WHERE seller_id = HEXTORAW(:seller_id)" in s:
            self._select_products_mine(**kwargs)
        elif "RAWTOHEX(id), name, price, thumbnail_ref FROM products" in s:
            self._select_products_grid()
        elif (
            "RAWTOHEX(id), name, price, description, thumbnail_ref FROM products"
            in s
        ):
            self._select_product_detail(**kwargs)
        elif "COUNT(*) FROM products WHERE id = HEXTORAW(:product_id)" in s:
            # Task 75 — submit_receipt()'s existence check before
            # inserting a receipt. Deliberately distinct from the
            # RAWTOHEX(id)-shaped product-detail select above.
            self._select_product_exists(**kwargs)
        elif "price, RAWTOHEX(seller_id) FROM products" in s:
            # Task 75 — verify_receipt()'s price/seller lookup.
            self._select_product_price_and_seller(**kwargs)
        elif "drive_link FROM products WHERE id = HEXTORAW(:product_id)" in s:
            # Task 75 — get_receipt_delivery()'s drive_link lookup.
            self._select_product_drive_link(**kwargs)
        elif (
            "RAWTOHEX(id), RAWTOHEX(seller_id), name, price, "
            "description, thumbnail_ref, drive_link FROM products" in s
        ):
            # Task 76 — `GET /admin/products`. Distinct from both
            # `_select_products_grid` (buyer-facing, no seller_id/
            # description/drive_link) and `_select_product_detail`
            # (buyer-facing, no seller_id/drive_link) — this is the only
            # products query that returns seller_id and drive_link.
            self._select_admin_products()
        elif (
            "cbe_account_name, cbe_account_number, "
            "telebirr_account_name, telebirr_account_number, "
            "commission_rate FROM admin_settings" in s
        ):
            # Task 76 — `_fetch_admin_settings_row()`, shared by
            # GET/PUT /admin/settings. Checked before the 4-column
            # GET /payment-info branch below since this 5-column query
            # would otherwise never reach it anyway (the two column
            # lists diverge before "FROM admin_settings"), but keeping
            # the more specific check first matches this file's existing
            # convention of most-specific-first for the `admin_settings`
            # table (see that branch's own comment).
            self._select_admin_settings_full()
        elif (
            "cbe_account_name, cbe_account_number, "
            "telebirr_account_name, telebirr_account_number "
            "FROM admin_settings" in s
        ):
            # Deliberately specific, not just "FROM admin_settings WHERE
            # id = 1" — `_get_commission_rate()` (Task 30) and
            # `_fetch_admin_settings_row()` (Task 31) both query the same
            # table with different column lists; a looser match here would
            # silently hand this 4-tuple to code expecting a different
            # shape once a later task's tests exercise those.
            self._select_payment_info()
        elif "SELECT commission_rate FROM admin_settings" in s:
            # Task 75 — `_get_commission_rate()`, called from
            # `_record_sale()`. Task 74 verified (outside pytest — see
            # its CURRENT_STATUS.md note) that this query correctly did
            # NOT match any Task 74 branch; now it gets a real one.
            self._select_commission_rate()
        elif "UPDATE admin_settings SET" in s:
            # Task 76 — `PUT /admin/settings`'s dynamic column list (only
            # the fields actually provided are set, same "omit = leave
            # unchanged" convention as `_update_seller_payment_methods`).
            self._update_admin_settings(**kwargs)
        elif "FROM sales GROUP BY seller_id" in s:
            # Task 77 — GET /admin/reports/by-seller's sales grouping.
            # Checked before the plain per-seller/platform aggregates
            # below since "GROUP BY seller_id" is the only thing that
            # distinguishes this query's text from the platform-wide
            # one once WHERE is absent from both.
            self._select_sales_grouped_by_seller()
        elif "SELECT SUM(seller_payable) FROM sales WHERE seller_id = HEXTORAW(:seller_id)" in s:
            # Task 77 — POST /admin/settlements' over-payment guard.
            # Deliberately checked before the 4-column per-seller
            # aggregate below: SELECT is immediately followed by
            # SUM(seller_payable) here, which never happens in the
            # COUNT(*)-first query, so the two can't cross-match.
            self._select_seller_payable_sum(**kwargs)
        elif "FROM sales WHERE seller_id = HEXTORAW(:seller_id)" in s:
            self._select_seller_sales_aggregate(**kwargs)
        elif "COUNT(*), SUM(gross_amount), SUM(commission_amount), SUM(seller_payable) FROM sales" in s:
            # Task 77 — GET /admin/reports' platform-wide sales
            # aggregate (same four columns as the per-seller version
            # above, just no WHERE clause — reached here only once the
            # WHERE/GROUP BY variants above have already failed to
            # match).
            self._select_platform_sales_aggregate()
        elif "FROM settlements WHERE seller_id = HEXTORAW(:seller_id)" in s:
            self._select_seller_completed_settlements_sum(**kwargs)
        elif "FROM settlements WHERE status = 'completed' GROUP BY seller_id" in s:
            # Task 77 — GET /admin/reports/by-seller's settlements
            # grouping ('completed' only, same as the platform-wide
            # version below). Checked before the platform-wide branch
            # below since that branch's substring ("SELECT SUM(amount)
            # FROM settlements WHERE status = 'completed'") would not
            # actually match this query's text (SELECT is immediately
            # followed by RAWTOHEX(seller_id) here, not SUM(amount)),
            # but keeping the GROUP BY variant checked first matches
            # this file's most-specific-first convention.
            self._select_settlements_grouped_by_seller()
        elif "SELECT SUM(amount) FROM settlements WHERE status = 'completed'" in s:
            # Task 77 — GET /admin/reports' platform-wide completed-
            # settlements sum. SELECT is immediately followed by
            # SUM(amount) here, unlike the GROUP BY version above
            # (which has RAWTOHEX(seller_id) first), so they can't
            # cross-match regardless of check order.
            self._select_platform_completed_settlements_sum()
        elif "INSERT INTO settlements" in s:
            self._insert_settlement(**kwargs)
        elif "SELECT status, created_at, completed_at FROM settlements" in s:
            # Task 77 — POST /admin/settlements' post-insert confirm
            # select. Distinct column list from every other settlements
            # select below (no id/seller_id/amount columns).
            self._select_settlement_status_and_timestamps(**kwargs)
        elif "RAWTOHEX(id), RAWTOHEX(seller_id), amount, status, created_at, completed_at FROM settlements" in s:
            # Task 77 — GET /admin/settlements' platform-wide listing.
            # Checked before the narrower single-settlement select below
            # since this one's column list is a superset (leads with
            # RAWTOHEX(id) as well as RAWTOHEX(seller_id)) — the two
            # can't cross-match either way since SELECT is immediately
            # followed by different text in each, but keeping the
            # longer column list checked first matches this file's
            # existing most-specific-first convention.
            self._select_all_settlements()
        elif "SELECT RAWTOHEX(seller_id), amount, status, created_at, completed_at FROM settlements" in s:
            # Task 77 — POST /admin/settlements/{id}/complete's fetch,
            # used both for the initial lookup and the post-UPDATE
            # re-fetch (identical query text both times).
            self._select_settlement_full(**kwargs)
        elif "UPDATE settlements SET status = 'completed'" in s:
            self._complete_settlement_row(**kwargs)
        elif "SELECT COUNT(*) FROM sellers WHERE id = HEXTORAW(:seller_id)" in s:
            # Task 77 — POST /admin/settlements' seller-existence check.
            # Distinct from every other `sellers` branch, which all key
            # off `email`, not `id`.
            self._select_seller_count_by_id(**kwargs)
        elif "INSERT INTO sales" in s:
            self._insert_sale(**kwargs)
        elif "INSERT INTO receipts" in s:
            self._insert_receipt(**kwargs)
        elif (
            "RAWTOHEX(product_id), receipt_url, status, "
            "transaction_ref, verified_amount, provider FROM receipts" in s
        ):
            self._select_receipt_for_verify(**kwargs)
        elif "RAWTOHEX(product_id), status FROM receipts" in s:
            self._select_receipt_for_delivery(**kwargs)
        elif "UPDATE receipts SET status = 'rejected'" in s:
            self._reject_receipt_row(**kwargs)
        elif "UPDATE receipts SET status = 'verified'" in s:
            self._verify_receipt_row(**kwargs)
        elif "FROM receipts WHERE transaction_ref = :transaction_ref" in s:
            self._count_verified_transaction(**kwargs)
        elif "SELECT 1 FROM dual" in s:
            self._result = [(1,)]
        else:
            self._unhandled_sql(s)

    def fetchone(self) -> tuple | None:
        if not self._result:
            return None
        return self._result[0]

    def fetchall(self) -> list[tuple]:
        return list(self._result or [])

    # --- sellers -------------------------------------------------------

    def _insert_seller(self, email: str, password_hash: str, id_out: FakeVar) -> None:
        if email in self._store.sellers:
            raise oracledb.IntegrityError(
                "ORA-00001: unique constraint (uq_sellers_email) violated"
            )
        id_hex = uuid.uuid4().hex.upper()
        self._store.sellers[email] = SellerRow(
            id_hex=id_hex, email=email, password_hash=password_hash
        )
        id_out.value = id_hex

    def _select_seller_for_login(self, email: str) -> None:
        row = self._store.sellers.get(email)
        if row is None:
            self._result = []
            return
        self._result = [(row.id_hex, row.password_hash, row.email_verified)]

    def _update_seller_verified(self, email: str) -> None:
        row = self._store.sellers.get(email)
        if row is not None:
            row.email_verified = "Y"

    def _select_seller_verified_flag(self, email: str) -> None:
        row = self._store.sellers.get(email)
        self._result = [] if row is None else [(row.email_verified,)]

    def _select_seller_exists(self, email: str) -> None:
        row = self._store.sellers.get(email)
        self._result = [] if row is None else [(1,)]

    def _update_seller_password(self, email: str, password_hash: str) -> None:
        row = self._store.sellers.get(email)
        if row is not None:
            row.password_hash = password_hash

    def _find_seller_by_id(self, seller_id: str) -> "SellerRow | None":
        """`sellers` is keyed by email in this store (see `_insert_seller`),
        but the payment-methods and earnings queries filter by id — a
        linear scan is fine at test scale."""
        for row in self._store.sellers.values():
            if row.id_hex == seller_id:
                return row
        return None

    def _select_seller_payment_methods(self, seller_id: str) -> None:
        row = self._find_seller_by_id(seller_id)
        self._result = (
            []
            if row is None
            else [
                (
                    row.cbe_account_name,
                    row.cbe_account_number,
                    row.telebirr_account_name,
                    row.telebirr_account_number,
                )
            ]
        )

    def _update_seller_payment_methods(self, seller_id: str, **fields: Any) -> None:
        row = self._find_seller_by_id(seller_id)
        if row is not None:
            for column, value in fields.items():
                setattr(row, column, value)

    def _select_seller_sales_aggregate(self, seller_id: str) -> None:
        rows = [r for r in self._store.sales if r.seller_id_hex == seller_id]
        if not rows:
            # COUNT(*) is 0 over zero rows; the SUM()s are NULL, not 0 —
            # matches Oracle (and every other SQL engine)'s behavior, which
            # is exactly why the real endpoint coalesces them afterward.
            self._result = [(0, None, None, None)]
            return
        self._result = [
            (
                len(rows),
                sum(r.gross_amount for r in rows),
                sum(r.commission_amount for r in rows),
                sum(r.seller_payable for r in rows),
            )
        ]

    def _select_seller_completed_settlements_sum(self, seller_id: str) -> None:
        rows = [
            r
            for r in self._store.settlements
            if r.seller_id_hex == seller_id and r.status == "completed"
        ]
        self._result = (
            [(None,)] if not rows else [(sum(r.amount for r in rows),)]
        )

    def _select_seller_payable_sum(self, seller_id: str) -> None:
        # Task 77 — POST /admin/settlements' over-payment guard.
        rows = [r for r in self._store.sales if r.seller_id_hex == seller_id]
        self._result = [(None,)] if not rows else [(sum(r.seller_payable for r in rows),)]

    def _select_platform_sales_aggregate(self) -> None:
        # Task 77 — GET /admin/reports, no seller filter.
        rows = self._store.sales
        if not rows:
            self._result = [(0, None, None, None)]
            return
        self._result = [
            (
                len(rows),
                sum(r.gross_amount for r in rows),
                sum(r.commission_amount for r in rows),
                sum(r.seller_payable for r in rows),
            )
        ]

    def _select_sales_grouped_by_seller(self) -> None:
        # Task 77 — GET /admin/reports/by-seller's sales grouping.
        groups: dict[str, list[SalesRow]] = {}
        for r in self._store.sales:
            groups.setdefault(r.seller_id_hex, []).append(r)
        self._result = [
            (
                seller_id,
                len(rows),
                sum(r.gross_amount for r in rows),
                sum(r.commission_amount for r in rows),
                sum(r.seller_payable for r in rows),
            )
            for seller_id, rows in groups.items()
        ]

    def _select_platform_completed_settlements_sum(self) -> None:
        # Task 77 — GET /admin/reports, no seller filter.
        rows = [r for r in self._store.settlements if r.status == "completed"]
        self._result = [(None,)] if not rows else [(sum(r.amount for r in rows),)]

    def _select_settlements_grouped_by_seller(self) -> None:
        # Task 77 — GET /admin/reports/by-seller's settlements
        # grouping, 'completed' only (same filter as
        # `_select_seller_completed_settlements_sum`/
        # `_select_platform_completed_settlements_sum`).
        groups: dict[str, list[SettlementRow]] = {}
        for r in self._store.settlements:
            if r.status == "completed":
                groups.setdefault(r.seller_id_hex, []).append(r)
        self._result = [
            (seller_id, sum(r.amount for r in rows)) for seller_id, rows in groups.items()
        ]

    def _find_settlement_by_id(self, settlement_id: str) -> "SettlementRow | None":
        for row in self._store.settlements:
            if row.id_hex == settlement_id:
                return row
        return None

    def _insert_settlement(self, seller_id: str, amount: float, id_out: FakeVar) -> None:
        # Task 77 — POST /admin/settlements. Every new settlement
        # starts 'pending' (SettlementRow's own default), matching
        # schema.sql's column default.
        id_hex = uuid.uuid4().hex.upper()
        self._store.settlements.append(
            SettlementRow(seller_id_hex=seller_id, amount=amount, id_hex=id_hex)
        )
        id_out.value = id_hex

    def _select_settlement_status_and_timestamps(self, settlement_id: str) -> None:
        row = self._find_settlement_by_id(settlement_id)
        self._result = [] if row is None else [(row.status, row.created_at, row.completed_at)]

    def _select_all_settlements(self) -> None:
        # Task 77 — GET /admin/settlements, newest first (matches the
        # real query's ORDER BY created_at DESC) — insertion order
        # doubles as chronological order, same convention as
        # `_select_admin_products`.
        rows = list(reversed(self._store.settlements))
        self._result = [
            (r.id_hex, r.seller_id_hex, r.amount, r.status, r.created_at, r.completed_at)
            for r in rows
        ]

    def _select_settlement_full(self, settlement_id: str) -> None:
        row = self._find_settlement_by_id(settlement_id)
        self._result = (
            []
            if row is None
            else [(row.seller_id_hex, row.amount, row.status, row.created_at, row.completed_at)]
        )

    def _complete_settlement_row(self, settlement_id: str) -> None:
        row = self._find_settlement_by_id(settlement_id)
        if row is not None:
            row.status = "completed"
            row.completed_at = datetime.now(timezone.utc)

    def _select_seller_count_by_id(self, seller_id: str) -> None:
        # Task 77 — POST /admin/settlements' seller-existence check.
        row = self._find_seller_by_id(seller_id)
        self._result = [(1 if row is not None else 0,)]

    # --- otp_codes -------------------------------------------------------

    def _otp_key(self, email: str, purpose: str) -> str | None:
        for id_hex, row in self._store.otp_codes.items():
            if row.email == email and row.purpose == purpose:
                return id_hex
        return None

    def _delete_otp_by_email_purpose(self, email: str, purpose: str) -> None:
        key = self._otp_key(email, purpose)
        if key is not None:
            del self._store.otp_codes[key]

    def _insert_otp(
        self, email: str, purpose: str, code_hash: str, expires_at: Any
    ) -> None:
        id_hex = uuid.uuid4().hex.upper()
        self._store.otp_codes[id_hex] = OtpRow(
            id_hex=id_hex,
            email=email,
            purpose=purpose,
            code_hash=code_hash,
            expires_at=expires_at,
        )

    def _select_otp(self, email: str, purpose: str) -> None:
        key = self._otp_key(email, purpose)
        if key is None:
            self._result = []
            return
        row = self._store.otp_codes[key]
        self._result = [(row.id_hex, row.code_hash, row.expires_at, row.attempts)]

    def _increment_otp_attempts(self, id: str) -> None:  # noqa: A002 - matches kwarg name
        row = self._store.otp_codes.get(id)
        if row is not None:
            row.attempts += 1

    def _delete_otp_by_id(self, id: str) -> None:  # noqa: A002 - matches kwarg name
        self._store.otp_codes.pop(id, None)

    # --- products --------------------------------------------------------

    def _insert_product(
        self,
        seller_id: str,
        name: str,
        price: float,
        description: str,
        drive_link: str,
        id_out: FakeVar,
    ) -> None:
        id_hex = uuid.uuid4().hex.upper()
        self._store.products[id_hex] = ProductRow(
            id_hex=id_hex,
            seller_id_hex=seller_id,
            name=name,
            price=price,
            description=description,
            drive_link=drive_link,
        )
        id_out.value = id_hex

    def _select_products_mine(self, seller_id: str) -> None:
        # Newest-first, matching the real query's ORDER BY created_at DESC.
        rows = [
            p
            for p in reversed(list(self._store.products.values()))
            if p.seller_id_hex == seller_id
        ]
        self._result = [
            (p.id_hex, p.name, p.price, p.description, p.drive_link) for p in rows
        ]

    def _select_products_grid(self) -> None:
        rows = list(reversed(list(self._store.products.values())))
        self._result = [(p.id_hex, p.name, p.price, p.thumbnail_ref) for p in rows]

    def _select_product_detail(self, product_id: str) -> None:
        row = self._store.products.get(product_id)
        self._result = (
            []
            if row is None
            else [(row.id_hex, row.name, row.price, row.description, row.thumbnail_ref)]
        )

    def _select_product_exists(self, product_id: str) -> None:
        # Task 75 — submit_receipt()'s pre-insert existence check.
        # COUNT(*) is always 0 or 1 for a single id lookup.
        count = 1 if product_id in self._store.products else 0
        self._result = [(count,)]

    def _select_product_price_and_seller(self, product_id: str) -> None:
        # Task 75 — verify_receipt()'s price/seller lookup. Empty result
        # (not a (None, None) row) for an unknown id, matching every
        # other `products` select's "no row" shape.
        row = self._store.products.get(product_id)
        self._result = [] if row is None else [(row.price, row.seller_id_hex)]

    def _select_product_drive_link(self, product_id: str) -> None:
        # Task 75 — get_receipt_delivery()'s drive_link lookup.
        row = self._store.products.get(product_id)
        self._result = [] if row is None else [(row.drive_link,)]

    def _select_admin_products(self) -> None:
        # Task 76 — `GET /admin/products`: every seller's products,
        # newest-first (matches the real query's ORDER BY created_at
        # DESC), including seller_id and drive_link — buyer-facing
        # product queries never include either.
        rows = list(reversed(list(self._store.products.values())))
        self._result = [
            (
                p.id_hex,
                p.seller_id_hex,
                p.name,
                p.price,
                p.description,
                p.thumbnail_ref,
                p.drive_link,
            )
            for p in rows
        ]

    # --- admin_settings ----------------------------------------------------

    def _select_payment_info(self) -> None:
        row = self._store.admin_settings
        self._result = (
            []
            if row is None
            else [
                (
                    row.cbe_account_name,
                    row.cbe_account_number,
                    row.telebirr_account_name,
                    row.telebirr_account_number,
                )
            ]
        )

    def _select_commission_rate(self) -> None:
        # Task 75 — `_get_commission_rate()`. `admin_settings.commission_rate`
        # is `NOT NULL` with a `DEFAULT 10.00`, and `admin_settings` is
        # always seeded (see AdminSettingsRow's own docstring and Task
        # 73's GET /payment-info "row missing" degrade path, which this
        # doesn't need since `_get_commission_rate()`'s docstring says
        # that fallback isn't needed here) — a `None` store.admin_settings
        # would be a genuine test-setup bug, not a real-world case, so
        # this doesn't special-case it the way `_select_payment_info()`
        # does.
        row = self._store.admin_settings
        self._result = [(row.commission_rate,)]

    def _select_admin_settings_full(self) -> None:
        # Task 76 — `_fetch_admin_settings_row()`, shared by GET and PUT
        # /admin/settings. Unlike `_select_payment_info()` (the public
        # GET /payment-info's 4-column query), this includes
        # `commission_rate` and degrades the same "empty result, not a
        # tuple of Nones" way when the singleton row is missing, so both
        # endpoints' own "row is None" fallback path gets exercised the
        # same way GET /payment-info's does.
        row = self._store.admin_settings
        self._result = (
            []
            if row is None
            else [
                (
                    row.cbe_account_name,
                    row.cbe_account_number,
                    row.telebirr_account_name,
                    row.telebirr_account_number,
                    row.commission_rate,
                )
            ]
        )

    def _update_admin_settings(self, **fields: Any) -> None:
        # Task 76 — `PUT /admin/settings`'s dynamic SET clause: only the
        # columns actually provided are bound, same pattern as
        # `_update_seller_payment_methods`. `admin_settings` is always
        # seeded (see `AdminSettingsRow`'s own docstring) so, unlike
        # `_select_admin_settings_full()`'s read side, there's no "row
        # missing" case to guard here — a `None` store.admin_settings at
        # this point would be a test-setup bug, not a real-world one.
        row = self._store.admin_settings
        if row is not None:
            for column, value in fields.items():
                setattr(row, column, value)

    # --- sales -------------------------------------------------------------

    def _insert_sale(
        self,
        receipt_id: str,
        product_id: str,
        seller_id: str,
        gross_amount: float,
        commission_rate: float,
        commission_amount: float,
        seller_payable: float,
    ) -> None:
        # Task 75 — `_record_sale()`'s real INSERT, as opposed to Task
        # 74's test-only `store.sales.append(...)` seeding.
        self._store.sales.append(
            SalesRow(
                seller_id_hex=seller_id,
                gross_amount=gross_amount,
                commission_amount=commission_amount,
                seller_payable=seller_payable,
                receipt_id_hex=receipt_id,
                product_id_hex=product_id,
                commission_rate=commission_rate,
            )
        )

    # --- receipts ------------------------------------------------------------

    def _insert_receipt(self, product_id: str, receipt_url: str, id_out: FakeVar) -> None:
        # Task 75 — submit_receipt(). `status` starts `None`/NULL,
        # matching `schema.sql`'s `status` column having no `DEFAULT`
        # (see ReceiptRow's own docstring) — a fresh receipt is neither
        # verified nor rejected until POST .../verify runs.
        id_hex = uuid.uuid4().hex.upper()
        self._store.receipts[id_hex] = ReceiptRow(
            id_hex=id_hex, product_id_hex=product_id, receipt_url=receipt_url
        )
        id_out.value = id_hex

    def _select_receipt_for_verify(self, receipt_id: str) -> None:
        row = self._store.receipts.get(receipt_id)
        self._result = (
            []
            if row is None
            else [
                (
                    row.product_id_hex,
                    row.receipt_url,
                    row.status,
                    row.transaction_ref,
                    row.verified_amount,
                    row.provider,
                )
            ]
        )

    def _select_receipt_for_delivery(self, receipt_id: str) -> None:
        row = self._store.receipts.get(receipt_id)
        self._result = [] if row is None else [(row.product_id_hex, row.status)]

    def _reject_receipt_row(
        self,
        receipt_id: str,
        transaction_ref: str | None,
        provider: str | None,
    ) -> None:
        row = self._store.receipts.get(receipt_id)
        if row is not None:
            row.status = "rejected"
            row.transaction_ref = transaction_ref
            row.provider = provider

    def _verify_receipt_row(
        self,
        receipt_id: str,
        transaction_ref: str | None,
        verified_amount: float | None,
        provider: str | None,
    ) -> None:
        row = self._store.receipts.get(receipt_id)
        if row is not None:
            row.status = "verified"
            row.transaction_ref = transaction_ref
            row.verified_amount = verified_amount
            row.provider = provider

    def _count_verified_transaction(self, transaction_ref: str, provider: str) -> None:
        # Task 75 — `is_duplicate_transaction()`.
        count = sum(
            1
            for row in self._store.receipts.values()
            if row.transaction_ref == transaction_ref
            and row.provider == provider
            and row.status == "verified"
        )
        self._result = [(count,)]

    def _unhandled_sql(self, s: str) -> None:
        raise NotImplementedError(
            f"FakeCursor doesn't recognize this query — add a branch to "
            f"fake_oracle.py's FakeCursor.execute() for it: {s!r}"
        )


class FakeConnection:
    def __init__(self, store: FakeOracleStore):
        self._store = store

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._store)

    def commit(self) -> None:
        # Everything above is already applied in-place; nothing to flush.
        pass

    def close(self) -> None:
        pass


def make_fake_get_connection(store: FakeOracleStore):
    """
    Returns a drop-in replacement for `db.get_connection`, backed by
    `store`. Two callers (app.main and app.otp both do
    `from .db import get_connection`, so each holds its own reference)
    should be pointed at the *same* `store` for a given test so a
    signup OTP written by `otp.issue_otp()` is visible to
    `otp.verify_otp()` later in the same test.
    """

    @contextmanager
    def _get_connection() -> Iterator[FakeConnection]:
        yield FakeConnection(store)

    return _get_connection
