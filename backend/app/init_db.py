"""
NATRA backend — apply the database schema.

Phase 1, Task 5: creates `sellers`. Phase 1, Task 8: creates `products`.
Phase 1, Task 12: creates `admin_settings` (NATRA's own CBE/Telebirr
payment info, single row) and seeds its one row if missing.
Phase 1, Task 13: creates `receipts` (buyer-submitted payment receipt
URLs — storage only, not verified yet).
Phase 2, Task 19: adds verification columns (`status`, `transaction_ref`,
`verified_amount`, `provider`) to `receipts`, via an idempotent
ALTER TABLE migration so it also applies to databases that already ran
Task 13's CREATE TABLE before these columns existed. Still no
verification *logic* — Tasks 20+ write to these columns; nothing does
yet.
Phase 2, Task 25: adds a unique index on `receipts` scoped to only
`status = 'verified'` rows, enforcing at the database level that the
same (`transaction_ref`, `provider`) pair can never back two verified
receipts — the safety net behind `app/duplicate_check.py`'s
application-level check (see that module's docstring for why both
layers exist). Also idempotent, guarded by an index-existence check.
Phase 3, Task 29: adds `commission_rate` to `admin_settings`
(NUMBER(5,2), NOT NULL, defaults to 10.00), via the same idempotent
ALTER TABLE ADD pattern as Task 19 — applies whether `admin_settings`
already exists (existing row backfilled with the 10.00 default by
Oracle) or is being created fresh in this same run. No commission
*logic* reads or writes it yet — that's a later Phase 3 task.
Phase 3, Task 30: creates `sales` (one row per verified receipt,
recording gross amount, a snapshot of `commission_rate` at that moment,
NATRA's commission, and the seller's payable balance). Populated by
`main.py`'s `verify_receipt()`/`_record_sale()`, in the same
transaction as the `receipts` UPDATE that marks a receipt 'verified'.
Phase 3, Task 33: adds four nullable payment-account columns
(`cbe_account_name`, `cbe_account_number`, `telebirr_account_name`,
`telebirr_account_number`) to `sellers`, via the same idempotent
ALTER TABLE ADD pattern as Task 19/29 — this is where a seller receives
a *settlement* later, never where a buyer pays (buyers only ever see
NATRA's own `admin_settings` account). All four start NULL/unconfigured
for both existing and freshly created sellers; no settlement logic
reads them yet (a later Phase 3 task).
Phase 3, Task 34: creates `settlements` (one row per settlement an
admin records for a seller — NATRA pays the seller manually, outside
the system, to the payout account from Task 33, then an admin records
it here). `status` starts 'pending' on every insert; nothing
transitions it to 'completed' yet — that's a later task (admin
settlement management). No validation ties `amount` to a seller's
actual outstanding `sales.seller_payable` balance yet — see
DATABASE_SCHEMA.md.
Phase 4, Task 45: adds four plain (non-unique) indexes, closing an
"unindexed FK on a hot query path" gap found by reviewing `main.py`'s
actual queries rather than indexing every FK on principle:
`idx_products_seller_id`, `idx_sales_seller_id`,
`idx_settlements_seller_id` (each backs a live `WHERE seller_id = ...`
read), and `idx_receipts_txn_provider` (backs
`duplicate_check.py`'s plain-column lookup, which Task 25's
function-based unique index does not serve). Added via the same
idempotent `_create_index_if_missing` pattern as Task 25's index.

Phase 6, Task 68: adds `sellers.email_verified` (VARCHAR2(1), 'Y'/'N',
defaults 'N') via the same idempotent ALTER TABLE ADD pattern as
Task 19/29/33, and creates `otp_codes` (backing `app/otp.py`'s
signup-verification and password-reset one-time-code flow, emailed
via Brevo — see `app/brevo_email.py`). See `backend/db/schema.sql`'s
own comments on both for the full reasoning.
Do not add other tables here ahead of the task that needs them (see
backend/db/schema.sql for the same DDL as a human-readable reference, and
DATABASE_SCHEMA.md at the project root for the documented schema).

Usage:
    cd backend
    python -m app.init_db

Safe to re-run: skips creating any table that already exists, skips
adding any column that already exists, skips creating any index that
already exists, and skips seeding the admin_settings row if it's
already there.
"""

from .db import get_connection

CREATE_SELLERS_TABLE = """
CREATE TABLE sellers (
    id            RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    email         VARCHAR2(255) NOT NULL,
    password_hash VARCHAR2(255) NOT NULL,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT uq_sellers_email UNIQUE (email)
)
"""

CREATE_PRODUCTS_TABLE = """
CREATE TABLE products (
    id            RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    seller_id     RAW(16) NOT NULL,
    name          VARCHAR2(255) NOT NULL,
    price         NUMBER(12,2) NOT NULL,
    description   VARCHAR2(4000),
    thumbnail_ref VARCHAR2(2048),
    drive_link    VARCHAR2(2048) NOT NULL,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_products_seller FOREIGN KEY (seller_id) REFERENCES sellers(id),
    CONSTRAINT ck_products_price_positive CHECK (price > 0)
)
"""

CREATE_ADMIN_SETTINGS_TABLE = """
CREATE TABLE admin_settings (
    id                       NUMBER(1) DEFAULT 1 PRIMARY KEY,
    cbe_account_name         VARCHAR2(255),
    cbe_account_number       VARCHAR2(64),
    telebirr_account_name    VARCHAR2(255),
    telebirr_account_number  VARCHAR2(64),
    updated_at               TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT ck_admin_settings_singleton CHECK (id = 1)
)
"""

CREATE_RECEIPTS_TABLE = """
CREATE TABLE receipts (
    id            RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    product_id    RAW(16) NOT NULL,
    receipt_url   VARCHAR2(2048) NOT NULL,
    submitted_at  TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_receipts_product FOREIGN KEY (product_id) REFERENCES products(id)
)
"""

# Task 19. Verification columns added to `receipts` after the fact, via
# migration rather than editing CREATE_RECEIPTS_TABLE above — that keeps
# this working for databases that already ran Task 13's CREATE TABLE
# (ALTER TABLE ADD, guarded by a column-existence check) as well as for
# a brand-new database (columns just won't exist yet when this runs, so
# they get added the same way). All four are nullable: a receipt starts
# with none of them set ("not verified yet"), same as today.
RECEIPTS_VERIFICATION_COLUMNS = [
    (
        "status",
        "VARCHAR2(20)",
        "CONSTRAINT ck_receipts_status "
        "CHECK (status IS NULL OR status IN ('pending', 'verified', 'rejected'))",
    ),
    ("transaction_ref", "VARCHAR2(128)", None),
    (
        "verified_amount",
        "NUMBER(12,2)",
        "CONSTRAINT ck_receipts_verified_amount_positive "
        "CHECK (verified_amount IS NULL OR verified_amount > 0)",
    ),
    (
        "provider",
        "VARCHAR2(20)",
        "CONSTRAINT ck_receipts_provider "
        "CHECK (provider IS NULL OR provider IN ('cbe', 'telebirr'))",
    ),
]

# Task 25. A plain UNIQUE INDEX on (transaction_ref, provider) would
# reject NULLs from participating at all (fine) but would also apply to
# 'pending'/'rejected' rows, which is wrong — a buyer can legitimately
# submit a receipt that ends up 'rejected' and then correctly resubmit
# the *real* transaction later, or two different buyers could both
# submit (and have rejected) the same not-yet-real transaction_ref by
# mistake. Only a *verified* transaction_ref should ever be unique.
# Oracle has no native partial/filtered unique index, so this uses the
# standard Oracle idiom instead: a unique index on two expressions that
# evaluate to NULL for every row except 'verified' ones — Oracle unique
# indexes ignore rows where every indexed column is NULL, so
# 'pending'/'rejected'/never-submitted rows never participate, while any
# two 'verified' rows sharing the same (transaction_ref, provider) pair
# collide and raise ORA-00001.
CREATE_RECEIPTS_VERIFIED_TXN_INDEX = """
CREATE UNIQUE INDEX uq_receipts_verified_txn ON receipts (
    CASE WHEN status = 'verified' THEN transaction_ref END,
    CASE WHEN status = 'verified' THEN provider END
)
"""

# Task 29 (Phase 3). Added after the fact via migration, same convention
# as RECEIPTS_VERIFICATION_COLUMNS above. NOT NULL + a DEFAULT is safe
# here even as an ALTER TABLE ADD on a table that may already have a row:
# Oracle backfills the existing row with the literal default (10.00)
# rather than requiring a separate seed/update step.
ADMIN_SETTINGS_COMMISSION_COLUMNS = [
    (
        "commission_rate",
        "NUMBER(5,2) DEFAULT 10.00 NOT NULL",
        "CONSTRAINT ck_admin_settings_commission_rate "
        "CHECK (commission_rate >= 0 AND commission_rate <= 100)",
    ),
]

# Task 33 (Phase 3). Added after the fact via migration, same convention
# as ADMIN_SETTINGS_COMMISSION_COLUMNS above — same shape as
# admin_settings' four CBE/Telebirr fields, but this is a seller's own
# payout account (for receiving a future settlement), not NATRA's. All
# nullable: unconfigured is a valid, expected state until the seller
# sets them via PUT /sellers/payment-methods.
SELLERS_PAYMENT_COLUMNS = [
    ("cbe_account_name", "VARCHAR2(255)", None),
    ("cbe_account_number", "VARCHAR2(64)", None),
    ("telebirr_account_name", "VARCHAR2(255)", None),
    ("telebirr_account_number", "VARCHAR2(64)", None),
]

# Task 30 (Phase 3). One row per verified receipt — see
# backend/db/schema.sql's own comment on this table for the full
# reasoning (snapshot commission_rate, one-sale-per-receipt via the
# UNIQUE constraint, written atomically with the receipts UPDATE).
CREATE_SALES_TABLE = """
CREATE TABLE sales (
    id                 RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    receipt_id         RAW(16) NOT NULL,
    product_id         RAW(16) NOT NULL,
    seller_id          RAW(16) NOT NULL,
    gross_amount       NUMBER(12,2) NOT NULL,
    commission_rate    NUMBER(5,2) NOT NULL,
    commission_amount  NUMBER(12,2) NOT NULL,
    seller_payable     NUMBER(12,2) NOT NULL,
    created_at         TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT fk_sales_receipt FOREIGN KEY (receipt_id) REFERENCES receipts(id),
    CONSTRAINT fk_sales_product FOREIGN KEY (product_id) REFERENCES products(id),
    CONSTRAINT fk_sales_seller FOREIGN KEY (seller_id) REFERENCES sellers(id),
    CONSTRAINT uq_sales_receipt UNIQUE (receipt_id),
    CONSTRAINT ck_sales_gross_amount_positive CHECK (gross_amount > 0),
    CONSTRAINT ck_sales_commission_rate
        CHECK (commission_rate >= 0 AND commission_rate <= 100),
    CONSTRAINT ck_sales_commission_amount_nonnegative CHECK (commission_amount >= 0),
    CONSTRAINT ck_sales_seller_payable_nonnegative CHECK (seller_payable >= 0)
)
"""

# Task 34 (Phase 3). See backend/db/schema.sql's own comment on this
# table for the full reasoning (status starts 'pending', no
# 'completed' transition yet, no reconciliation against sales yet).
CREATE_SETTLEMENTS_TABLE = """
CREATE TABLE settlements (
    id            RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    seller_id     RAW(16) NOT NULL,
    amount        NUMBER(12,2) NOT NULL,
    status        VARCHAR2(20) DEFAULT 'pending' NOT NULL,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    completed_at  TIMESTAMP WITH TIME ZONE,
    CONSTRAINT fk_settlements_seller FOREIGN KEY (seller_id) REFERENCES sellers(id),
    CONSTRAINT ck_settlements_amount_positive CHECK (amount > 0),
    CONSTRAINT ck_settlements_status CHECK (status IN ('pending', 'completed'))
)
"""

# Task 45. Oracle does NOT automatically index foreign-key columns (only
# primary/unique-key columns get one for free). These three FK columns
# are each read via an equality `WHERE ... = :seller_id` filter in
# `main.py` on a live request path — `products.seller_id` (seller's own
# "view my products" list), `sales.seller_id` and `settlements.seller_id`
# (both read on every `GET /sellers/earnings` call, seller-only, and by
# the admin per-seller report) — so each was a full-table scan without
# an index. Deliberately NOT indexing `receipts.product_id`: it has the
# same "unindexed FK" shape, but nothing in `main.py` actually queries
# `receipts` by `product_id` (every receipts lookup is by its own
# primary key, `id`) — this task adds indexes for real query patterns
# found by reviewing `main.py`, not for every FK on principle.
CREATE_PRODUCTS_SELLER_ID_INDEX = """
CREATE INDEX idx_products_seller_id ON products (seller_id)
"""

CREATE_SALES_SELLER_ID_INDEX = """
CREATE INDEX idx_sales_seller_id ON sales (seller_id)
"""

CREATE_SETTLEMENTS_SELLER_ID_INDEX = """
CREATE INDEX idx_settlements_seller_id ON settlements (seller_id)
"""

# Task 45. `duplicate_check.py`'s `is_duplicate_transaction()` — called
# on every receipt-verification attempt — filters
# `WHERE transaction_ref = :ref AND provider = :provider AND
# status = 'verified'` on plain columns. That's a different shape from
# Task 25's `uq_receipts_verified_txn`, which is a function-based unique
# index over two `CASE WHEN status = 'verified' THEN ... END`
# expressions: Oracle only matches a function-based index against a
# query using that exact expression, not a plain-column predicate, so
# that existing index does not serve this lookup and it was a
# full-table scan on `receipts`. A plain composite index on
# `(transaction_ref, provider)` does serve it (Oracle can range-scan on
# the leading two columns, then filter the small remaining set by
# `status` from the index or table) without duplicating Task 25's
# uniqueness guarantee, which stays exactly as-is.
CREATE_RECEIPTS_TXN_PROVIDER_INDEX = """
CREATE INDEX idx_receipts_txn_provider ON receipts (transaction_ref, provider)
"""

# Task 68 (Phase 6). Added after the fact via migration, same
# convention as SELLERS_PAYMENT_COLUMNS above. Defaults 'N' so every
# existing seller row (created before this task) backfills as
# "not verified" rather than requiring a separate backfill step —
# correct, since none of them went through the new OTP flow.
SELLERS_EMAIL_VERIFIED_COLUMN = [
    (
        "email_verified",
        "VARCHAR2(1) DEFAULT 'N' NOT NULL",
        "CONSTRAINT ck_sellers_email_verified CHECK (email_verified IN ('Y', 'N'))",
    ),
]

# Task 68 (Phase 6). See backend/db/schema.sql's own comment on this
# table for the full reasoning (one row per outstanding OTP, hashed
# code, attempt counter, purpose-scoped, unique per (email, purpose)).
CREATE_OTP_CODES_TABLE = """
CREATE TABLE otp_codes (
    id          RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    email       VARCHAR2(255) NOT NULL,
    purpose     VARCHAR2(20) NOT NULL,
    code_hash   VARCHAR2(255) NOT NULL,
    expires_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    attempts    NUMBER(3) DEFAULT 0 NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT uq_otp_codes_email_purpose UNIQUE (email, purpose),
    CONSTRAINT ck_otp_codes_purpose CHECK (purpose IN ('signup', 'password_reset')),
    CONSTRAINT ck_otp_codes_attempts_nonneg CHECK (attempts >= 0)
)
"""



def _table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT COUNT(*) FROM user_tables WHERE table_name = :name",
        name=table_name.upper(),
    )
    (count,) = cursor.fetchone()
    return count > 0


def _create_table_if_missing(cursor, table_name: str, ddl: str) -> None:
    if _table_exists(cursor, table_name):
        print(f"{table_name} table already exists, skipping.")
        return
    cursor.execute(ddl)
    print(f"{table_name} table created.")


def _column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(
        "SELECT COUNT(*) FROM user_tab_columns "
        "WHERE table_name = :table_name AND column_name = :column_name",
        table_name=table_name.upper(),
        column_name=column_name.upper(),
    )
    (count,) = cursor.fetchone()
    return count > 0


def _add_columns_if_missing(cursor, table_name: str, columns: list) -> None:
    """
    Migration helper: for each (column_name, type_clause, constraint_clause)
    tuple, add that column to `table_name` via ALTER TABLE ... ADD if it
    isn't already there. `constraint_clause` may be None. Runs one column
    at a time (rather than a single multi-column ALTER) so a partially
    applied migration — e.g. a prior run that added some but not all
    columns before failing — still converges cleanly on a re-run.
    """
    for column_name, type_clause, constraint_clause in columns:
        if _column_exists(cursor, table_name, column_name):
            print(f"{table_name}.{column_name} already exists, skipping.")
            continue
        clause = f"{column_name} {type_clause}"
        if constraint_clause:
            clause += f" {constraint_clause}"
        cursor.execute(f"ALTER TABLE {table_name} ADD ({clause})")
        print(f"{table_name}.{column_name} added.")


def _index_exists(cursor, index_name: str) -> bool:
    cursor.execute(
        "SELECT COUNT(*) FROM user_indexes WHERE index_name = :name",
        name=index_name.upper(),
    )
    (count,) = cursor.fetchone()
    return count > 0


def _create_index_if_missing(cursor, index_name: str, ddl: str) -> None:
    if _index_exists(cursor, index_name):
        print(f"{index_name} index already exists, skipping.")
        return
    cursor.execute(ddl)
    print(f"{index_name} index created.")


def _seed_admin_settings_row(cursor) -> None:
    """
    Ensure the single admin_settings row (id=1) exists, so
    GET /payment-info always has something to read. All payment fields
    start NULL — the admin hasn't set them yet (Task 16 adds the write
    endpoint); NULL is the correct "not configured yet" state, not a
    placeholder value.
    """
    cursor.execute("SELECT COUNT(*) FROM admin_settings WHERE id = 1")
    (count,) = cursor.fetchone()
    if count > 0:
        print("admin_settings row already seeded, skipping.")
        return
    cursor.execute("INSERT INTO admin_settings (id) VALUES (1)")
    print("admin_settings row seeded (all payment fields NULL).")


def apply_schema() -> None:
    """Create any table (sellers, products, admin_settings, receipts, ...)
    that doesn't already exist, add any migration columns that don't
    already exist, and seed admin_settings' single row."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            _create_table_if_missing(cur, "sellers", CREATE_SELLERS_TABLE)
            _create_table_if_missing(cur, "products", CREATE_PRODUCTS_TABLE)
            _create_table_if_missing(cur, "admin_settings", CREATE_ADMIN_SETTINGS_TABLE)
            _create_table_if_missing(cur, "receipts", CREATE_RECEIPTS_TABLE)
            _add_columns_if_missing(cur, "receipts", RECEIPTS_VERIFICATION_COLUMNS)
            _create_index_if_missing(
                cur, "uq_receipts_verified_txn", CREATE_RECEIPTS_VERIFIED_TXN_INDEX
            )
            _add_columns_if_missing(
                cur, "admin_settings", ADMIN_SETTINGS_COMMISSION_COLUMNS
            )
            _seed_admin_settings_row(cur)
            _create_table_if_missing(cur, "sales", CREATE_SALES_TABLE)
            _add_columns_if_missing(cur, "sellers", SELLERS_PAYMENT_COLUMNS)
            _create_table_if_missing(cur, "settlements", CREATE_SETTLEMENTS_TABLE)
            _create_index_if_missing(
                cur, "idx_products_seller_id", CREATE_PRODUCTS_SELLER_ID_INDEX
            )
            _create_index_if_missing(
                cur, "idx_sales_seller_id", CREATE_SALES_SELLER_ID_INDEX
            )
            _create_index_if_missing(
                cur, "idx_settlements_seller_id", CREATE_SETTLEMENTS_SELLER_ID_INDEX
            )
            _create_index_if_missing(
                cur, "idx_receipts_txn_provider", CREATE_RECEIPTS_TXN_PROVIDER_INDEX
            )
            _add_columns_if_missing(cur, "sellers", SELLERS_EMAIL_VERIFIED_COLUMN)
            _create_table_if_missing(cur, "otp_codes", CREATE_OTP_CODES_TABLE)
            conn.commit()


if __name__ == "__main__":
    apply_schema()
