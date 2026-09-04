# NATRA — DATABASE SCHEMA

## Status

`sellers` was created in Task 5 and gained four payment-account columns
in Task 33 (Phase 3); `products` was added in Task 8;
`admin_settings` was added in Task 12 and gained `commission_rate` in
Task 29 (Phase 3); `receipts` was added in Task 13, gained its
payment-verification columns in Task 19, and gained a
duplicate-protection unique index in Task 25; `sales` was added in
Task 30 (Phase 3); `settlements` was added in Task 34 (Phase 3). Task
45 (Phase 4) added four plain indexes — `idx_products_seller_id`,
`idx_sales_seller_id`, `idx_settlements_seller_id`, and
`idx_receipts_txn_provider` — no new tables or columns.
All are applied via `backend/app/init_db.py`; the same DDL is kept as a
human-readable reference in `backend/db/schema.sql`.

This file will be updated with each additional table/model as it is
introduced. Do not implement future tables ahead of the task that requires
them.

## Current Tables

### `sellers`

| Column | Type | Constraints |
|---|---|---|
| `id` | `RAW(16)` | Primary key, default `SYS_GUID()` |
| `email` | `VARCHAR2(255)` | `NOT NULL`, unique (`uq_sellers_email`) |
| `password_hash` | `VARCHAR2(255)` | `NOT NULL` — never store plain-text passwords |
| `cbe_account_name` | `VARCHAR2(255)` | nullable — added Task 33; the seller's own CBE payout account, for receiving a future settlement |
| `cbe_account_number` | `VARCHAR2(64)` | nullable — added Task 33 |
| `telebirr_account_name` | `VARCHAR2(255)` | nullable — added Task 33 |
| `telebirr_account_number` | `VARCHAR2(64)` | nullable — added Task 33 |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | `NOT NULL`, default `SYSTIMESTAMP` |

The unique constraint on `email` doubles as an index and enforces one
account per email at the database level.

The four payment-account columns (Task 33) are the seller's own CBE/
Telebirr account — where NATRA will eventually *send* a settlement to
this seller — never the account a buyer pays into (that's always
NATRA's own `admin_settings` row, shown via the public
`GET /payment-info`). All four start `NULL` for every seller, existing
or new; `init_db.py` adds them via idempotent `ALTER TABLE ... ADD`, the
same convention as `receipts`' Task 19 columns and `admin_settings`'
Task 29 `commission_rate`. As of Task 33, `GET`/`PUT
/sellers/payment-methods` (both seller-only, via the existing
`get_current_seller_id`) read and update them, `seller_id` coming from
the verified JWT so a seller can only ever see or change their own
payout account. `PUT` follows the same "omit = leave unchanged"
convention as `PUT /admin/settings`: a field left out of the request
stays unchanged; sending an empty string `""` explicitly clears it. No
settlement logic reads these columns yet — that starts once
`settlements` (still just a planned table below) actually exists.

### `products`

| Column | Type | Constraints |
|---|---|---|
| `id` | `RAW(16)` | Primary key, default `SYS_GUID()` |
| `seller_id` | `RAW(16)` | `NOT NULL`, FK → `sellers(id)` (`fk_products_seller`) |
| `name` | `VARCHAR2(255)` | `NOT NULL` |
| `price` | `NUMBER(12,2)` | `NOT NULL`, `CHECK (price > 0)` (`ck_products_price_positive`) |
| `description` | `VARCHAR2(4000)` | nullable |
| `thumbnail_ref` | `VARCHAR2(2048)` | nullable — unused for now; no upload mechanism/Object Storage yet (later task) |
| `drive_link` | `VARCHAR2(2048)` | `NOT NULL` — seller's public Google Drive delivery link |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | `NOT NULL`, default `SYSTIMESTAMP` |

One seller can own many products (`seller_id` FK, no uniqueness constraint
on it). Rows are only ever inserted by the owning seller, identified from
their verified JWT (`POST /products`) — `seller_id` is never taken from the
request body.

As of Task 45, `idx_products_seller_id` (a plain index on `seller_id`)
backs the `WHERE seller_id = ...` filter `GET /sellers/products` uses
to list only the authenticated seller's own products. Oracle does not
create an index for a foreign-key column automatically (only for a
primary/unique key), so before this task that lookup was a full-table
scan; the public, buyer-facing product listing (`GET /products`) has no
`seller_id` filter and isn't affected either way.

### `admin_settings`

| Column | Type | Constraints |
|---|---|---|
| `id` | `NUMBER(1)` | Primary key, default `1`, `CHECK (id = 1)` — singleton row |
| `cbe_account_name` | `VARCHAR2(255)` | nullable — unset until an admin configures it |
| `cbe_account_number` | `VARCHAR2(64)` | nullable |
| `telebirr_account_name` | `VARCHAR2(255)` | nullable |
| `telebirr_account_number` | `VARCHAR2(64)` | nullable |
| `commission_rate` | `NUMBER(5,2)` | `NOT NULL`, default `10.00`, `CHECK (commission_rate >= 0 AND commission_rate <= 100)` (`ck_admin_settings_commission_rate`) — added Task 29 |
| `updated_at` | `TIMESTAMP WITH TIME ZONE` | `NOT NULL`, default `SYSTIMESTAMP` |

Exactly one row ever exists (`id` fixed to `1`), seeded by
`init_db.py` if missing. Holds NATRA's own CBE/Telebirr payment account —
never a seller's — shown to buyers after "Buy Now" (`GET /payment-info`).
`PUT /admin/settings` (Task 16, admin-only) writes the four account
fields; each is independently optional in that request, so any field
left out stays unchanged rather than being cleared. `commission_rate`
(Task 29) is NATRA's percentage cut of a verified sale — e.g. a 500 ETB
sale at the default 10.00 rate is 50 ETB to NATRA, 450 ETB seller
payable, per `CLAUDE_MASTER_PROMPT.md` section 4. Unlike the payment
fields it is `NOT NULL` (a rate must always exist once anything starts
computing commissions) and defaults to 10.00 so existing and new
installs both start with a sane value. As of Task 31, `GET`/`PUT
/admin/settings` (both admin-only) read and update it — `GET` returns
it alongside the four payment fields via `AdminSettingsResponse`; `PUT`
accepts an optional `commission_rate` (bounded `[0, 100]`) following the
same "omit = leave unchanged" convention as the payment fields, except
it can never be cleared to "unset" since the column is `NOT NULL`. The
public, buyer-facing `GET /payment-info` is untouched and still never
returns `commission_rate` — buyers have no reason to see it.

### `receipts`

| Column | Type | Constraints |
|---|---|---|
| `id` | `RAW(16)` | Primary key, default `SYS_GUID()` |
| `product_id` | `RAW(16)` | `NOT NULL`, FK → `products(id)` (`fk_receipts_product`) |
| `receipt_url` | `VARCHAR2(2048)` | `NOT NULL` — buyer-pasted payment receipt URL |
| `submitted_at` | `TIMESTAMP WITH TIME ZONE` | `NOT NULL`, default `SYSTIMESTAMP` |
| `status` | `VARCHAR2(20)` | Nullable; `CHECK` allows only `NULL`, `'pending'`, `'verified'`, `'rejected'` (`ck_receipts_status`) — added Task 19 |
| `transaction_ref` | `VARCHAR2(128)` | Nullable — the payment provider's own transaction/reference number, extracted during verification — added Task 19 |
| `verified_amount` | `NUMBER(12,2)` | Nullable; `CHECK (verified_amount IS NULL OR verified_amount > 0)` (`ck_receipts_verified_amount_positive`) — added Task 19 |
| `provider` | `VARCHAR2(20)` | Nullable; `CHECK` allows only `NULL`, `'cbe'`, `'telebirr'` (`ck_receipts_provider`) — added Task 19 |

`POST /products/{product_id}/receipt` (Task 13) still only inserts
`product_id` and `receipt_url` — the four verification columns above
exist as of Task 19 but nothing writes to them yet; that starts at
Task 20 (CBE fetching) and Task 22 (Telebirr fetching), with the amount/
status validation (Task 24) and duplicate-payment protection (Task 25)
having built the pieces that will fill them in once an endpoint (Task
26) actually calls them. A product may have more than one `receipts`
row — e.g. a buyer resubmits a corrected link, or two different rows
both end up `'pending'`/`'rejected'`. As of Task 25, a unique index
(`uq_receipts_verified_txn`) enforces that the same
(`transaction_ref`, `provider`) pair can never belong to two rows that
are both `status = 'verified'` — implemented as an Oracle
function-based unique index over two `CASE WHEN status = 'verified'
THEN ... END` expressions, since Oracle has no native partial/filtered
unique index and Oracle unique indexes ignore rows where every indexed
expression evaluates to `NULL` (which `'pending'`/`'rejected'` rows
always do here). This is deliberately a safety net, not the primary
mechanism: the primary check is `app/duplicate_check.py`'s
`is_duplicate_transaction()`, an application-level query run before a
future verification attempt marks anything `'verified'`, so a
duplicate can be rejected with a clear reason rather than surfacing as
a raw database error. Duplicate-payment protection keys off
`transaction_ref` (plus `provider`), the payment provider's own
number, never off the payer's name, per
`CLAUDE_MASTER_PROMPT.md` section 5.

`init_db.py` adds the four verification columns via idempotent
`ALTER TABLE ... ADD` statements and the unique index via an idempotent
`CREATE UNIQUE INDEX` (guarded by a check against `user_indexes`), so it
applies cleanly both to a brand-new database and to one that already ran
Task 13's original `CREATE TABLE receipts`.

As of Task 45, a second, plain (non-unique) index —
`idx_receipts_txn_provider` on `(transaction_ref, provider)` — backs
`duplicate_check.py`'s `is_duplicate_transaction()` lookup. That
function filters `WHERE transaction_ref = ... AND provider = ... AND
status = 'verified'` on the plain columns, a different expression shape
from `uq_receipts_verified_txn`'s `CASE WHEN status = 'verified' THEN
...END` function-based index above — Oracle only matches a
function-based index against a query using that exact expression, so
the existing unique index does not serve this lookup. The two indexes
serve different purposes and both remain: `uq_receipts_verified_txn`
enforces uniqueness at the database level; `idx_receipts_txn_provider`
only speeds up the lookup and enforces nothing.

### `sales`

| Column | Type | Constraints |
|---|---|---|
| `id` | `RAW(16)` | Primary key, default `SYS_GUID()` |
| `receipt_id` | `RAW(16)` | `NOT NULL`, FK → `receipts(id)` (`fk_sales_receipt`), UNIQUE (`uq_sales_receipt`) — the UNIQUE constraint doubles as an index |
| `product_id` | `RAW(16)` | `NOT NULL`, FK → `products(id)` (`fk_sales_product`) |
| `seller_id` | `RAW(16)` | `NOT NULL`, FK → `sellers(id)` (`fk_sales_seller`) |
| `gross_amount` | `NUMBER(12,2)` | `NOT NULL`, `CHECK (gross_amount > 0)` |
| `commission_rate` | `NUMBER(5,2)` | `NOT NULL`, `CHECK (commission_rate >= 0 AND commission_rate <= 100)` — snapshot of `admin_settings.commission_rate` at verification time, not a live reference |
| `commission_amount` | `NUMBER(12,2)` | `NOT NULL`, `CHECK (commission_amount >= 0)` |
| `seller_payable` | `NUMBER(12,2)` | `NOT NULL`, `CHECK (seller_payable >= 0)` |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | `NOT NULL`, default `SYSTIMESTAMP` |

Added Task 30 (Phase 3). One row per receipt that reaches
`status = 'verified'`, written by `main.py`'s `_record_sale()` in the
same connection/transaction as `verify_receipt()`'s `UPDATE receipts`,
so a verified receipt and its sale row can never diverge. The
`UNIQUE` constraint on `receipt_id` enforces at the database level that
a receipt can never back more than one sale, matching the fact that a
receipt only ever transitions to `'verified'` once (`verify_receipt()`
is idempotent after that point — a second call just returns the
already-stored result without re-running anything, including this
insert). `commission_rate`/`commission_amount`/`seller_payable` are
computed once, at verification time, from whatever
`admin_settings.commission_rate` is *then* — deliberately a snapshot,
not a live join, so a later change to the platform's commission rate
never rewrites what a past sale actually earned. `seller_id` is
denormalized from `products.seller_id` (rather than requiring a join
through `products` for every future earnings/settlement query) since a
product's seller never changes after creation. As of Task 32,
`GET /sellers/earnings` (seller-only) reads this table to return the
authenticated seller's own aggregate totals (sale count, gross,
commission, payable). As of Task 36 it also returns the settled/
unsettled split (see `settlements` below for how `settled_total` is
computed). As of Task 37, `GET /admin/reports` (admin-only) reads this
same table with the same six-field shape, but platform-wide — no
`WHERE seller_id = ...` filter, so it is every seller's sales summed
together, not one seller's. As of Task 38, `GET /admin/reports/by-seller`
(admin-only) reads it a third way — `GROUP BY seller_id` — returning one
row per seller instead of either a single seller's row or one
platform-wide row; summing every row it returns reproduces exactly what
`GET /admin/reports` reports as its single row.

As of Task 45, `idx_sales_seller_id` (a plain index on `seller_id`)
backs the `WHERE seller_id = ...` filter `GET /sellers/earnings` relies
on — before this index, Oracle had no FK-column index to use here
(Oracle does not create one automatically for a foreign key, unlike a
primary/unique key), so that lookup was a full-table scan. `GET
/admin/reports/by-seller`'s `GROUP BY seller_id` scans and groups the
whole table regardless (it has no `WHERE seller_id = ...` to seek on),
so this index isn't expected to change that query's plan — it exists
for the single-seller lookup.

### `settlements`

| Column | Type | Constraints |
|---|---|---|
| `id` | `RAW(16)` | Primary key, default `SYS_GUID()` |
| `seller_id` | `RAW(16)` | `NOT NULL`, FK → `sellers(id)` (`fk_settlements_seller`) |
| `amount` | `NUMBER(12,2)` | `NOT NULL`, `CHECK (amount > 0)` (`ck_settlements_amount_positive`) |
| `status` | `VARCHAR2(20)` | `NOT NULL`, default `'pending'`, `CHECK` allows only `'pending'`/`'completed'` (`ck_settlements_status`) |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | `NOT NULL`, default `SYSTIMESTAMP` |
| `completed_at` | `TIMESTAMP WITH TIME ZONE` | nullable — set when a settlement transitions to `'completed'`, by `POST /admin/settlements/{settlement_id}/complete` (Task 35) |

Added Task 34 (Phase 3). One row per settlement an admin records for a
seller: NATRA pays the seller manually, outside this system, to the
payout account the seller set via `PUT /sellers/payment-methods`
(Task 33), then `POST /admin/settlements` (admin-only) records that it
happened. Every settlement starts `status = 'pending'` — as of Task 35,
`POST /admin/settlements/{settlement_id}/complete` (admin-only) marks
it `'completed'` and stamps `completed_at`, idempotently (calling it
again on an already-`'completed'` row just returns the stored result).
`GET /admin/settlements` (admin-only) lists every settlement across all
sellers, newest first; there is no seller-scoped equivalent yet (a
seller can't see their own settlement history through any endpoint
yet — a possible future task).

For Tasks 34-38, no task validated `amount` against a seller's actual
outstanding `sales.seller_payable` balance — `POST /admin/settlements`
and `.../complete` both trusted whatever amount an admin recorded, with
no reconciliation logic. As of Task 36, `GET /sellers/earnings`'
`settled_total` (`SUM(amount)` over this seller's `'completed'`
settlements) and `unsettled_total` (`seller_payable_total -
settled_total`) made an over-settlement *visible* — a seller's
`unsettled_total` could go negative if an admin recorded more in
completed settlements than that seller's `sales` actually earned — but
nothing yet prevented it from happening in the first place. As of Task
37, `GET /admin/reports` summed this same `'completed'`-only
`SUM(amount)` platform-wide, so the same not-clamped-to-zero
`unsettled_total` behavior — and the same underlying gap — was visible
at the platform level too, not just per seller. As of Task 38, `GET
/admin/reports/by-seller` grouped the same `SUM(amount)` by `seller_id`
instead, so an over-settled seller was identifiable by `seller_id`
rather than only inferred from a platform-wide total that could hide
one over-settled seller behind other, under-settled ones.

As of Task 42, the gap is closed at the source: `POST
/admin/settlements` computes this same `seller_payable_total -
settled_total` (`'completed'`-only) balance for the target seller
before inserting, and rejects with `422` any `amount` that would drive
it negative. `.../complete` still performs no reconciliation of its
own — it doesn't need to, since a settlement's `amount` is now fixed
and validated at creation time, before it can ever become `'pending'`.
The remaining, narrower gap: this check only weighs already-`'completed'`
settlements, so two simultaneous `'pending'` settlements can still each
individually pass validation yet together overdraw the balance once
both are completed — deliberately out of scope for Task 42; see
`POST /admin/settlements`' docstring.

As of Task 45, `idx_settlements_seller_id` (a plain index on
`seller_id`) backs the `WHERE seller_id = ...` filter both `GET
/sellers/earnings`' `settled_total` and `POST /admin/settlements`'
Task 42 balance check rely on — same unindexed-FK gap, and same fix, as
`sales.seller_id` above. `GET /admin/settlements` (lists every
settlement, all sellers) and `GET /admin/reports`/`.../by-seller`
(platform-wide or grouped, no single-seller filter) aren't expected to
benefit from it — same reasoning as `sales` above.

## Planned Tables (for reference only — NOT yet implemented)

These are anticipated based on the final product vision. They are listed here
only to guide sensible naming/design later; none of them exist yet.

- (none currently planned for Phase 3 — Task 38 was the last item on
  Phase 3's task list; see PROJECT_ROADMAP.md)

## Constraints / Notes

- No `buyers` table — buyers never create accounts.
- No `admins` table — there is exactly one Master Admin identity,
  provisioned via the `ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH` environment
  variables (Task 14), not a database row. See `ARCHITECTURE.md` for the
  rationale. This may change to a real table if NATRA ever needs multiple
  admins with different permissions — not before.
- Any future payment/receipt identifier used for duplicate protection must be
  the transaction/reference/receipt ID, never the payer's name.
- Task 45 added four plain (non-unique) indexes after reviewing every
  query in `main.py`/`duplicate_check.py` for an unindexed column on a
  live filter path: `idx_products_seller_id`, `idx_sales_seller_id`,
  `idx_settlements_seller_id` (Oracle does not index FK columns
  automatically, and each backs a real `WHERE seller_id = ...` read),
  and `idx_receipts_txn_provider` (backs `is_duplicate_transaction()`'s
  plain-column lookup, which Task 25's function-based unique index
  doesn't serve). `receipts.product_id` has the same unindexed-FK shape
  but was deliberately left unindexed — nothing queries `receipts` by
  `product_id`; every lookup goes through `receipts.id`.
