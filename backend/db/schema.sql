-- NATRA — database schema.
--
-- This file is a human-readable reference. The backend applies this same
-- DDL programmatically via `backend/app/init_db.py` (idempotent: skips
-- creation of any table that already exists).

-- Task 5.
-- Task 33 (Phase 3): four nullable payment-account columns, mirroring
-- admin_settings' own CBE/Telebirr fields in shape, but semantically the
-- opposite — this is where NATRA sends a seller's money for a settlement,
-- never where a buyer pays (buyers only ever see NATRA's own
-- admin_settings account, per ARCHITECTURE.md's payment architecture).
-- All four start NULL ("not configured yet"); no settlement logic reads
-- them yet (a later Phase 3 task).
-- Task 68 (Phase 6): `email_verified` tracks whether a seller has
-- confirmed their address via the OTP flow in `app/otp.py`. Starts 'N'
-- on every registration (`app/main.py`'s `register_seller()`, which
-- also triggers the first OTP email); flips to 'Y' via
-- `POST /sellers/verify-email`.
--
-- Task 71: `POST /sellers/login` now gates on this value (403 for 'N',
-- checked after the password check — see `login_seller()`'s docstring
-- for why that order matters). Task 68 had deliberately left this
-- ungated to avoid breaking the register-then-auto-login frontend
-- chain (Task 55); Task 71 removed that auto-login step
-- (`SellerRegister.tsx`) so the gate could land here without locking a
-- seller out of the very screen that lets them verify.
CREATE TABLE sellers (
    id                       RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    email                    VARCHAR2(255) NOT NULL,
    password_hash            VARCHAR2(255) NOT NULL,
    email_verified           VARCHAR2(1) DEFAULT 'N' NOT NULL,
    cbe_account_name         VARCHAR2(255),
    cbe_account_number       VARCHAR2(64),
    telebirr_account_name    VARCHAR2(255),
    telebirr_account_number  VARCHAR2(64),
    created_at               TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT uq_sellers_email UNIQUE (email),
    CONSTRAINT ck_sellers_email_verified CHECK (email_verified IN ('Y', 'N'))
);

-- Task 8. Phase 1 fields only (name, price, description, thumbnail ref,
-- public Google Drive delivery link, seller_id). `thumbnail_ref` is
-- nullable and unused for now — no upload mechanism/Object Storage exists
-- yet (a later task); the column exists so it doesn't require a schema
-- change when that task lands.
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
);

-- Task 12. Single-row table (id is always 1) holding NATRA's own CBE/
-- Telebirr payment account info, shown to buyers after "Buy Now" — this
-- is NATRA's account, never a seller's (see ARCHITECTURE.md "payment
-- architecture"). All fields start NULL/unconfigured; init_db.py seeds
-- the one row. No admin write endpoint yet (Task 16 adds it) — for now
-- these are only ever set directly in the database.
-- Task 29 (Phase 3). `commission_rate` is NATRA's commission percentage
-- applied to a verified sale (see CLAUDE_MASTER_PROMPT.md section 4's
-- worked example: 500 ETB sale, 10% commission = 50 ETB to NATRA, 450 ETB
-- seller payable). Lives on the same singleton row as the CBE/Telebirr
-- settings since it's another piece of admin-configured, NATRA-wide
-- state. Defaults to 10.00 (10%) so a fresh install has a sane rate from
-- the start rather than an unset one; NOT NULL because, unlike the
-- payment fields, "no rate configured" isn't a valid state once Phase 3
-- logic starts computing commissions. Added via idempotent
-- `ALTER TABLE ... ADD` in `init_db.py` for databases that already ran
-- this CREATE TABLE before the column existed; the version below is the
-- final shape for a fresh install. No endpoint reads or writes this yet
-- — that starts with the admin settlement/commission-management task.
CREATE TABLE admin_settings (
    id                       NUMBER(1) DEFAULT 1 PRIMARY KEY,
    cbe_account_name         VARCHAR2(255),
    cbe_account_number       VARCHAR2(64),
    telebirr_account_name    VARCHAR2(255),
    telebirr_account_number  VARCHAR2(64),
    commission_rate          NUMBER(5,2) DEFAULT 10.00 NOT NULL,
    updated_at               TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT ck_admin_settings_singleton CHECK (id = 1),
    CONSTRAINT ck_admin_settings_commission_rate
        CHECK (commission_rate >= 0 AND commission_rate <= 100)
);

-- Task 13. Buyer-submitted payment receipt URL, stored only — NOT
-- verified yet (verification is explicitly Phase 2, see
-- CLAUDE_MASTER_PROMPT.md sections 5 and 9). No order/sale row exists at
-- this point since nothing is verified in Phase 1; a product can receive
-- more than one receipt submission (e.g. a buyer retries), so there is no
-- uniqueness constraint here yet — duplicate-payment protection is also a
-- Phase 2 concern, keyed off the transaction/reference number extracted
-- from the receipt during verification, never off this table.
--
-- Task 19 adds the four verification columns below (status,
-- transaction_ref, verified_amount, provider) — all nullable, since a
-- receipt starts unverified. On an existing database that already ran
-- the Task 13 CREATE TABLE, `init_db.py` adds these via idempotent
-- ALTER TABLE statements rather than recreating the table; the version
-- below is simply the final shape, for a fresh install. No verification
-- *logic* writes to these columns yet — that starts at Task 20 (CBE) and
-- Task 22 (Telebirr).
CREATE TABLE receipts (
    id               RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    product_id       RAW(16) NOT NULL,
    receipt_url      VARCHAR2(2048) NOT NULL,
    submitted_at     TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    status           VARCHAR2(20),
    transaction_ref  VARCHAR2(128),
    verified_amount  NUMBER(12,2),
    provider         VARCHAR2(20),
    CONSTRAINT fk_receipts_product FOREIGN KEY (product_id) REFERENCES products(id),
    CONSTRAINT ck_receipts_status
        CHECK (status IS NULL OR status IN ('pending', 'verified', 'rejected')),
    CONSTRAINT ck_receipts_verified_amount_positive
        CHECK (verified_amount IS NULL OR verified_amount > 0),
    CONSTRAINT ck_receipts_provider
        CHECK (provider IS NULL OR provider IN ('cbe', 'telebirr'))
);

-- Task 25. Duplicate payment protection at the database level, backing
-- `backend/app/duplicate_check.py`'s application-level check. Oracle has
-- no native partial/filtered unique index, so this uses the standard
-- Oracle idiom: a unique index on two expressions that evaluate to NULL
-- for every row except 'verified' ones. Oracle unique indexes ignore
-- rows where every indexed column is NULL, so 'pending'/'rejected' rows
-- never participate in the uniqueness check — only two 'verified' rows
-- sharing the same (transaction_ref, provider) pair would collide.
CREATE UNIQUE INDEX uq_receipts_verified_txn ON receipts (
    CASE WHEN status = 'verified' THEN transaction_ref END,
    CASE WHEN status = 'verified' THEN provider END
);

-- Task 30 (Phase 3). One row per verified receipt, recording NATRA's
-- commission and the seller's payable balance for that sale.
-- `commission_rate` is snapshotted from `admin_settings.commission_rate`
-- (Task 29) at the moment of verification (not looked up live later) so
-- a future rate change never rewrites the numbers on a past sale.
-- `receipt_id` is UNIQUE — at most one sale per receipt, matching the
-- fact that `verify_receipt()` only ever transitions a receipt to
-- 'verified' once (it's idempotent after that). Written in the same
-- transaction as that UPDATE (see `main.py`'s `verify_receipt()` /
-- `_record_sale()`) so a verified receipt and its sale row can never
-- diverge.
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
);

-- Task 34 (Phase 3). One row per settlement NATRA records for a seller —
-- NATRA manually pays the seller outside the system (their own CBE/
-- Telebirr account, Task 33), then an admin records that payout here.
-- `status` starts 'pending' on every insert; nothing transitions it to
-- 'completed' yet — that's explicitly a later task (admin settlement
-- management), which will add the endpoint that flips this status and
-- sets `completed_at`. Deliberately no FK/derivation tying `amount` to
-- `sales.seller_payable` yet and no validation that it doesn't exceed
-- the seller's outstanding balance — that reconciliation is out of
-- scope for this task; see DATABASE_SCHEMA.md for the reasoning.
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
);

-- Task 68 (Phase 6). Backs `app/otp.py`'s signup-verification and
-- password-reset OTP flow. One row per outstanding code for a given
-- (email, purpose) pair — `uq_otp_codes_email_purpose` enforces at
-- most one at a time, matching `issue_otp()`'s own
-- delete-then-insert behavior (the constraint is a race-condition
-- safety net, not the primary mechanism). `code_hash` stores a
-- PBKDF2 hash (via `security.hash_password()`), never the plain-text
-- code — same reasoning as `sellers.password_hash`. `attempts` counts
-- failed verify attempts against this specific code; `verify_otp()`
-- refuses to even compare once it reaches 5, forcing a fresh
-- `issue_otp()` call instead of unlimited guessing against one code.
-- Not tied to `sellers` via a foreign key: a signup-verification code
-- is issued in the same request that creates the seller row, but a
-- password-reset code's email is looked up against `sellers` only at
-- request-time in `app/main.py`, not enforced by this table itself.
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
);

-- Task 45. Oracle does not automatically index foreign-key columns (only
-- primary/unique-key columns get one for free). These three back a live
-- `WHERE seller_id = ...` read in main.py: a seller's own "view my
-- products" list, and GET /sellers/earnings (seller-facing) plus the
-- admin per-seller report, both of which read `sales`/`settlements` by
-- seller_id. Without these, each of those was a full-table scan.
-- `receipts.product_id` has the same unindexed-FK shape but is
-- deliberately NOT indexed here: nothing in main.py actually queries
-- `receipts` by `product_id` (every receipts lookup goes through its own
-- primary key, `id`) — indexes were added for real query patterns found
-- by reviewing main.py, not for every FK on principle.
CREATE INDEX idx_products_seller_id ON products (seller_id);
CREATE INDEX idx_sales_seller_id ON sales (seller_id);
CREATE INDEX idx_settlements_seller_id ON settlements (seller_id);

-- Task 45. `duplicate_check.py`'s `is_duplicate_transaction()` filters
-- `WHERE transaction_ref = :ref AND provider = :provider AND
-- status = 'verified'` on plain columns — a different shape from Task
-- 25's `uq_receipts_verified_txn` above, which is a function-based
-- unique index over two `CASE WHEN status = 'verified' THEN ... END`
-- expressions. Oracle only matches a function-based index against a
-- query using that exact expression, so that index does not serve this
-- plain-column lookup, which was a full-table scan on `receipts`. This
-- plain composite index lets Oracle range-scan on the leading two
-- columns instead, without touching Task 25's uniqueness guarantee.
CREATE INDEX idx_receipts_txn_provider ON receipts (transaction_ref, provider);
