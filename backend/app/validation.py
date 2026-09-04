"""
NATRA backend — payment amount/status validation against a product's
price.

Phase 2, Task 24: given the structured data `extract_cbe_data()` /
`extract_telebirr_data()` produced (Tasks 21/23) and the price of the
product the buyer is paying for, decide whether the receipt actually
covers that purchase.

Kept separate from `cbe.py`/`telebirr.py` on purpose: this step is pure
comparison logic, needs no Playwright and no provider-specific text
parsing, so it has no reason to depend on either module beyond the
shape of the dict they return.

## Scoped decisions made for this task (recorded here, not just in
## CURRENT_STATUS.md, since the reasoning matters for anyone extending
## this later)

1. **Status validation.** *(Revised during the Task 67 hardening pass,
   which checked both extractors against real CBE/Telebirr receipts for
   the first time.)* Both `extract_cbe_data()` and `extract_telebirr_data()`
   now capture an explicit status field ("Status: COMPLETED" on CBE,
   "transaction status: Completed" on Telebirr — both confirmed against
   real receipt screenshots) and expose it as `status_ok`: True only
   when a status word was found and it's a recognized "completed"
   value. This closes a real gap the original scope-note above
   (superseded) explicitly flagged as unaddressed: a PENDING, FAILED, or
   REVERSED transaction can still have a genuine reference number and
   amount on its receipt page, and before this fix that combination
   alone (`found: True`) was accepted as a valid payment. `valid` now
   requires `found` AND `status_ok` both being True.
2. **Exact match vs. tolerance on amount.** This validates the paid
   amount against the product's price as an **exact match after
   rounding both to 2 decimal places** (matching `products.price`'s
   `NUMBER(12,2)` column) — not a tolerance band. A buyer either paid
   the listed price or they didn't; silently accepting an underpayment
   within some tolerance isn't something to introduce without the
   project owner explicitly asking for it. Rounding to 2 decimals only
   guards against float-representation noise (e.g. `299.99999999999994`
   from upstream parsing), not a real tolerance for mismatched amounts.
3. **Which Telebirr amount field counts as "paid".** *(Also revised
   during the Task 67 hardening pass.)* `get_paid_amount()` now prefers
   `settled_amount` over `total_paid` for Telebirr. `total_paid`
   includes Telebirr's own service fee on top of the amount actually
   credited to the receiver (confirmed on a real receipt: 175 birr
   settled vs. 177 birr total paid, a 1.74 birr service fee + 0.26 birr
   fee VAT) — validating against `total_paid` would have required
   buyers to also cover Telebirr's fee to pass, which is wrong, and
   inconsistent with the reasoning `get_paid_amount()` already used for
   CBE (`transferred_amount`, not `total_debited`, for the identical
   reason). `total_paid` is kept only as a fallback for a page where
   `settled_amount` wasn't extracted at all.
"""

PROVIDER_CBE = "cbe"
PROVIDER_TELEBIRR = "telebirr"
_KNOWN_PROVIDERS = (PROVIDER_CBE, PROVIDER_TELEBIRR)

# Reasons `validate_payment()` can report — a fixed, small vocabulary so
# a caller (Task 26's verification endpoint) can react to each distinct
# case (e.g. a different buyer-facing message) without string-matching
# free text.
REASON_NOT_FOUND = "not_found"
REASON_NOT_COMPLETED = "not_completed"
REASON_AMOUNT_MISSING = "amount_missing"
REASON_AMOUNT_MISMATCH = "amount_mismatch"
REASON_UNKNOWN_PROVIDER = "unknown_provider"


def get_paid_amount(provider: str, extracted: dict) -> float | None:
    """
    Pick the single "amount the buyer actually paid" figure out of an
    extractor's result dict, per provider:
      - CBE: `transferred_amount` — what the payer sent — not
        `total_debited`, which can include a transfer fee on top of
        the transferred amount and would overstate what NATRA received
        credit for.
      - Telebirr: `total_paid`, falling back to `settled_amount` when
        `total_paid` wasn't present — same fallback order
        `extract_telebirr_data()` already uses internally to compute
        its own `found` flag, kept consistent here.
    Returns `None` for an unrecognized provider or a missing field —
    never raises.
    """
    if provider == PROVIDER_CBE:
        return extracted.get("transferred_amount")
    if provider == PROVIDER_TELEBIRR:
        settled = extracted.get("settled_amount")
        return settled if settled is not None else extracted.get("total_paid")
    return None


def validate_payment(provider: str, extracted: dict, expected_price: float) -> dict:
    """
    Validate an extractor's result against a product's price.

    Never raises. Returns:
      {
        "valid": bool,
        "reason": str | None,   # one of the REASON_* constants when invalid, else None
        "paid_amount": float | None,
        "expected_price": float,
        "provider": str,
      }

    `valid` is True only when the provider is recognized, the receipt
    was `found`, its extracted status indicates a completed transaction
    (`status_ok`, decision 1), and the paid amount exactly matches
    `expected_price` after rounding both to 2 decimal places (decision
    2). No duplicate-payment check happens here — that's Task 25.
    """
    if provider not in _KNOWN_PROVIDERS:
        return {
            "valid": False,
            "reason": REASON_UNKNOWN_PROVIDER,
            "paid_amount": None,
            "expected_price": expected_price,
            "provider": provider,
        }

    if not extracted.get("found"):
        return {
            "valid": False,
            "reason": REASON_NOT_FOUND,
            "paid_amount": None,
            "expected_price": expected_price,
            "provider": provider,
        }

    if not extracted.get("status_ok"):
        # Covers both an explicit non-completed status (PENDING, FAILED,
        # REVERSED, ...) and a page where no recognized status field was
        # found at all — either way, this function can't confirm the
        # transaction actually completed, so it can't be accepted as a
        # valid payment even though a reference and amount were found.
        return {
            "valid": False,
            "reason": REASON_NOT_COMPLETED,
            "paid_amount": None,
            "expected_price": expected_price,
            "provider": provider,
        }

    paid_amount = get_paid_amount(provider, extracted)
    if paid_amount is None:
        # Shouldn't happen in practice — both extractors only set
        # `found: True` once an amount was located — but handled
        # explicitly rather than assumed, since `found` and
        # `get_paid_amount()`'s fallback logic living in two different
        # places is exactly the kind of thing that could drift out of
        # sync in a future edit.
        return {
            "valid": False,
            "reason": REASON_AMOUNT_MISSING,
            "paid_amount": None,
            "expected_price": expected_price,
            "provider": provider,
        }

    if round(paid_amount, 2) != round(expected_price, 2):
        return {
            "valid": False,
            "reason": REASON_AMOUNT_MISMATCH,
            "paid_amount": paid_amount,
            "expected_price": expected_price,
            "provider": provider,
        }

    return {
        "valid": True,
        "reason": None,
        "paid_amount": paid_amount,
        "expected_price": expected_price,
        "provider": provider,
    }
