"""
NATRA backend — duplicate payment protection.

Phase 2, Task 25: given a transaction/reference number extracted from a
receipt (Tasks 21/23) and the provider it came from, decide whether
that transaction has already been used for a *successful* verification
elsewhere in the system — i.e. reject a second buyer (or a retry)
trying to use the same real-world payment to unlock a second delivery.

Per `CLAUDE_MASTER_PROMPT.md` section 5: **the payer name must never be
used as a uniqueness key.** Only `transaction_ref` (the provider's own
identifier) is used here.

Two layers, both added by this task:
  1. `is_duplicate_transaction()` — an application-level check, run
     *before* a future verification attempts to mark a receipt
     `verified` (Task 26 will be the first caller). This is the primary
     mechanism: it lets the caller return a clear, specific rejection
     (`reason: "duplicate_transaction"`) instead of a raw database
     error.
  2. A unique index on `receipts`, added via this task's `init_db.py`
     migration (mirroring Task 19's idempotent `ALTER TABLE` pattern),
     enforcing the same rule at the database level. This exists purely
     as a safety net against a race between two concurrent verification
     attempts for the same transaction — the kind of window an
     application-level SELECT-then-UPDATE check alone can't fully close
     — not as the primary mechanism (see `db/schema.sql` /
     `init_db.py` for the index definition and the Oracle-specific
     reasoning behind how it's scoped to only `status = 'verified'`
     rows).

`provider` is included alongside `transaction_ref` in both layers, even
though CBE and Telebirr reference numbers are already visibly different
formats (Task 21's 12-character `FT...`-style vs. Task 23's shorter
`Receipt No.` values) — being explicit about the provider removes any
reliance on that format difference always holding, rather than being an
assumption baked silently into a bare `transaction_ref`-only check.
"""

from .db import get_connection

REASON_DUPLICATE_TRANSACTION = "duplicate_transaction"


def is_duplicate_transaction(transaction_ref: str, provider: str) -> bool:
    """
    True if a `receipts` row already exists with this exact
    `transaction_ref` + `provider` pair and `status = 'verified'` — i.e.
    this transaction has already been used for a successful
    verification. Returns False for `None`/empty `transaction_ref` or
    `provider` without querying, since Task 24's `validate_payment()`
    already guarantees a `found: True` result always has a real
    transaction reference — a caller reaching this function with an
    empty one indicates a bug upstream, not "no duplicate found", so
    this is a defensive guard rather than the expected path.
    """
    if not transaction_ref or not provider:
        return False

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM receipts
                WHERE transaction_ref = :transaction_ref
                  AND provider = :provider
                  AND status = 'verified'
                """,
                transaction_ref=transaction_ref,
                provider=provider,
            )
            (count,) = cur.fetchone()

    return count > 0
