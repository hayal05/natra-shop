"""
NATRA backend — CBE receipt page fetching and data extraction.

Phase 2, Task 20: given a CBE receipt URL
(https://mbreciept.cbe.com.et/...), load it with Playwright and return
its raw rendered page content (HTML + visible text).

Phase 2, Task 21: `extract_cbe_data()` parses that visible text into
structured fields (transaction reference, transferred amount, payer/
receiver names, date, reason). **Best-effort, not yet confirmed against
a real CBE receipt page** — this sandbox cannot reach
`mbreciept.cbe.com.et` (see CURRENT_STATUS.md), so the patterns below are
based on the field labels consistently reported across many
independently published CBE mobile-banking receipts (a public,
structural fact about the page layout — "Payer", "Receiver",
"Reference No. (VAT Invoice No)", "Transferred Amount", "Total amount
debited from customers account" — not from a page this codebase has
actually fetched itself). No amount/status *validation* against a
product's price happens here — that's Task 24. No duplicate-payment
check — that's Task 25.

Split into three pieces on purpose:
  - `_validate_cbe_url()` — pure, no network/browser needed, so it's
    fully testable without any external dependency.
  - `_load_page()` — the actual Playwright navigation, reused as-is by
    Task 22's Telebirr fetcher (same mechanism, different host).
  - `extract_cbe_data()` — pure text parsing, independently testable
    against any sample text without needing a browser at all.
`fetch_cbe_receipt()` composes the first two; `parse_cbe_receipt()`
composes fetching with extraction for convenience.
"""

import re
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

# Per CLAUDE_MASTER_PROMPT.md section 5: CBE receipt URLs look like
# https://mbreciept.cbe.com.et/...
CBE_RECEIPT_HOST = "mbreciept.cbe.com.et"

DEFAULT_TIMEOUT_MS = 15000


class InvalidReceiptUrlError(ValueError):
    """Raised when a URL is not a CBE receipt URL."""


def _validate_cbe_url(url: str) -> None:
    """
    Reject anything that isn't an https URL on exactly
    `mbreciept.cbe.com.et`. Using `urlparse(...).hostname` (not a
    substring/`endswith` check) means a lookalike host such as
    `mbreciept.cbe.com.et.evil.com` or `evil.com/mbreciept.cbe.com.et`
    is correctly rejected, not accidentally accepted.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != CBE_RECEIPT_HOST:
        raise InvalidReceiptUrlError(
            f"Not a CBE receipt URL (expected https://{CBE_RECEIPT_HOST}/...): {url!r}"
        )


def _load_page(url: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> dict:
    """
    Host-agnostic Playwright page load, reused by the Telebirr fetcher
    (Task 22). Returns raw HTML and visible text; never raises.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, timeout=timeout_ms, wait_until="networkidle")
                html = page.content()
                text = page.inner_text("body")
                page.close()
            finally:
                browser.close()
        return {"fetched": True, "html": html, "text": text}
    except Exception as exc:  # noqa: BLE001 - deliberately broad, never crash the caller
        return {"fetched": False, "error": str(exc)}


def fetch_cbe_receipt(url: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> dict:
    """
    Load a CBE receipt URL and return its raw rendered content.

    Returns a dict, never raises:
      Success: {"fetched": True, "html": "...", "text": "..."}
      Failure: {"fetched": False, "error": "..."}
    Failure covers both a URL that isn't a CBE receipt URL and any
    navigation/browser failure (timeout, DNS, non-200, etc.) — the
    caller doesn't need to distinguish those to decide "verification
    can't proceed."
    """
    try:
        _validate_cbe_url(url)
    except InvalidReceiptUrlError as exc:
        return {"fetched": False, "error": str(exc)}

    return _load_page(url, timeout_ms=timeout_ms)


# --- Task 21: data extraction --------------------------------------------
#
# Hardened against two real CBE receipts (task 67 follow-up): the header/
# customer-info fields, "Payer"/"Receiver"/"Account" rows, "Payment Type",
# "Payment Date & Time", "Reference No (VAT Invoice No)", and the page's
# top-of-receipt "Status: COMPLETED" banner were all confirmed directly
# against real `mbreciept.cbe.com.et` screenshots. Two real bugs this
# fixed: (1) `Payer:`/`Receiver:` have a colon the old patterns didn't
# skip over, so both fields silently always returned `None`; (2) the real
# date format is "Aug 27, 2026, 3:39 PM", not the numeric "DD/MM/YYYY"
# the old pattern assumed, so `payment_date` also always returned `None`.
# The "Transferred Amount"/"Total amount debited" fields themselves were
# below the fold in the screenshot we have — the amount pattern below is
# widened to accept both a bare integer and a decimal amount, with or
# without a trailing "Birr"/"ETB", but the exact field label there is
# still not independently confirmed against a live page.

# Accepts "175", "175.00", or "1,234.56" — real CBE amounts observed
# elsewhere on the page (e.g. none directly confirmed here) may or may
# not include cents, so this no longer requires exactly two decimal
# digits the way the original pattern did. The leading
# `(?<![A-Za-z0-9])` prevents a windowed search (e.g. `_TOTAL_DEBITED_RE`,
# which allows up to 80 chars of unrelated text before the amount) from
# matching a stray digit run embedded inside a nearby reference number
# or account number instead of the real amount.
_AMOUNT_PATTERN = r"(?<![A-Za-z0-9])([\d][\d,]*(?:\.\d{1,2})?)\s*(?:Birr|ETB|birr)?"
# Used only by the windowed `_TOTAL_DEBITED_RE` below, where up to 80
# characters of unrelated text (potentially including a date, which is
# itself several stray digit runs) can sit between the label and the
# real amount. Requiring the currency word anchors on the one thing a
# date never has — see the matching comment in telebirr.py, where this
# was confirmed to matter against a reconstructed real sample.
_AMOUNT_PATTERN_STRICT = r"(?<![A-Za-z0-9])([\d][\d,]*(?:\.\d{1,2})?)\s*(?:Birr|ETB|birr)"

_REFERENCE_RE = re.compile(
    # CBE reference numbers observed across many independently published
    # receipts, and confirmed again in the real sample this task used
    # ("FT26239NB22Z"), are consistently exactly 12 characters — matched
    # as an exact length, not an open-ended range, so that in text with
    # no whitespace between the reference and the next label, the match
    # can't run on into that label's own text.
    r"(?i:Reference\s*No\.?\s*(?:\(\s*VAT\s*Invoice\s*No\s*\)\s*)?)[:\-]?\s*([A-Z0-9]{12})"
)
# Fallback for a reference of some other length: only used when the page
# has an actual whitespace/line boundary after the value (so there's no
# run-together ambiguity to worry about in the first place).
_REFERENCE_FALLBACK_RE = re.compile(
    r"(?i:Reference\s*No\.?\s*(?:\(\s*VAT\s*Invoice\s*No\s*\)\s*)?)[:\-]?\s*([A-Z0-9]{6,20})(?=\s|$)"
)
_TRANSFERRED_AMOUNT_RE = re.compile(
    r"(?i:Transferred\s*Amount)\s*[:\-]?\s*" + _AMOUNT_PATTERN
)
_TOTAL_DEBITED_RE = re.compile(
    r"(?i:Total\s*amount\s*debited).{0,80}?" + _AMOUNT_PATTERN_STRICT, re.DOTALL
)
# `[:\-]?` now actually matters: the real page renders "Payer:" and
# "Receiver:" with a colon, which `\s*` alone (the old pattern) never
# matched, so these two fields always silently came back `None` before.
_PAYER_RE = re.compile(
    r"(?i:Payer)\s*[:\-]?\s*([A-Z][A-Za-z .]{1,80}?)\s*(?:Account|\r?\n|$)"
)
_RECEIVER_RE = re.compile(
    r"(?i:Receiver)\s*[:\-]?\s*([A-Z][A-Za-z .]{1,80}?)\s*(?:Account|\r?\n|$)"
)
# Two alternatives: the numeric "DD/MM/YYYY..." form kept as a fallback
# in case a different CBE receipt template uses it, and the real
# "Mon DD, YYYY, H:MM AM/PM" form confirmed against the actual sample
# ("Aug 27, 2026, 3:39 PM") — tried first since it's the confirmed one.
_PAYMENT_DATE_RE = re.compile(
    r"(?i:Payment\s*Date(?:\s*&\s*Time)?)\s*[:\-]?\s*"
    r"([A-Za-z]{3,9}\s+[0-9]{1,2},\s*[0-9]{4},?\s*[0-9]{1,2}:[0-9]{2}\s*[APap][Mm]"
    r"|[0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}[^\r\n]*)"
)
_REASON_RE = re.compile(
    r"(?i:Reason\s*/?\s*(?:Type\s*of\s*service)?)\s*[:\-]?\s*([^\r\n]{1,120}?)"
    r"\s*(?:(?i:Transferred\s*Amount)|$)"
)
# Confirmed against the real sample: the top of the receipt reads
# "Status: COMPLETED". Captures the single word after the label.
_STATUS_RE = re.compile(r"(?i:Status)\s*[:\-]?\s*([A-Za-z]+)")
# Values that count as a genuinely completed, money-actually-moved
# transaction. Anything else (PENDING, FAILED, REVERSED, CANCELLED, or
# no status found at all) must not be treated as a valid payment, even
# if a reference number and an amount were both present on the page —
# those can still appear on a pending or reversed transaction's receipt.
_COMPLETED_STATUSES = {"completed", "success", "successful"}

# Substrings that, if present when none of the structured fields were
# found, suggest the page is a "not found"/error response rather than a
# genuine receipt — best-effort, unconfirmed against a real error page.
_NOT_FOUND_HINTS = ("not found", "invalid", "no record", "does not exist", "error")


def _parse_amount(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def extract_cbe_data(text: str) -> dict:
    """
    Best-effort extraction of transaction fields from a CBE receipt
    page's visible text — i.e. the `"text"` value `fetch_cbe_receipt()`
    returns on success.

    Never raises. Returns:
      {
        "found": bool,                      # ref + amount both located
        "transaction_ref": str | None,       # e.g. "FT25057C5FS8"
        "transferred_amount": float | None,
        "total_debited": float | None,
        "payer_name": str | None,
        "receiver_name": str | None,
        "payment_date": str | None,
        "reason": str | None,
        "status": str | None,               # raw status word, e.g. "COMPLETED"
        "status_ok": bool,                  # status is a known-completed value
        "likely_not_found": bool,           # page looks like an error/not-found response
      }

    `found` is True only when both a transaction reference and a
    transferred amount were located — the two fields duplicate-payment
    protection (Task 25) and amount validation (Task 24) actually need.
    `status_ok` is a separate, additional gate: True only when a status
    word was found AND it's a recognized "completed" value. A page that
    has a reference and an amount but a PENDING/FAILED/REVERSED status
    (or no status field this parser recognizes at all) sets `status_ok`
    to False — `validate_payment()` (Task 24) requires both `found` and
    `status_ok` before accepting a payment, closing the gap where a
    real reference+amount pair from a *non*-completed transaction could
    otherwise pass. The other fields are extracted best-effort and may
    be `None` even on a genuine receipt if the page's exact wording
    differs from what these patterns expect.
    """
    text = text or ""

    ref_match = _REFERENCE_RE.search(text) or _REFERENCE_FALLBACK_RE.search(text)
    transferred_match = _TRANSFERRED_AMOUNT_RE.search(text)
    total_match = _TOTAL_DEBITED_RE.search(text)
    payer_match = _PAYER_RE.search(text)
    receiver_match = _RECEIVER_RE.search(text)
    date_match = _PAYMENT_DATE_RE.search(text)
    reason_match = _REASON_RE.search(text)
    status_match = _STATUS_RE.search(text)

    transaction_ref = ref_match.group(1).upper() if ref_match else None
    transferred_amount = _parse_amount(transferred_match.group(1)) if transferred_match else None
    total_debited = _parse_amount(total_match.group(1)) if total_match else None
    payer_name = payer_match.group(1).strip() if payer_match else None
    receiver_name = receiver_match.group(1).strip() if receiver_match else None
    payment_date = date_match.group(1).strip() if date_match else None
    reason = reason_match.group(1).strip() if reason_match else None
    status = status_match.group(1).strip() if status_match else None
    status_ok = status is not None and status.lower() in _COMPLETED_STATUSES

    found = transaction_ref is not None and transferred_amount is not None
    likely_not_found = not found and any(hint in text.lower() for hint in _NOT_FOUND_HINTS)

    return {
        "found": found,
        "transaction_ref": transaction_ref,
        "transferred_amount": transferred_amount,
        "total_debited": total_debited,
        "payer_name": payer_name,
        "receiver_name": receiver_name,
        "payment_date": payment_date,
        "reason": reason,
        "status": status,
        "status_ok": status_ok,
        "likely_not_found": likely_not_found,
    }


def parse_cbe_receipt(url: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> dict:
    """
    Convenience wrapper: fetch a CBE receipt URL and extract its data in
    one call. Returns the fetch failure shape (`{"fetched": False,
    "error": ...}`, with `"found": False` merged in for a consistent
    shape to check) if fetching failed, otherwise `extract_cbe_data()`'s
    result merged with `{"fetched": True}`.

    Not used by any endpoint yet — Task 26's verification endpoint will
    be the first caller.
    """
    fetch_result = fetch_cbe_receipt(url, timeout_ms=timeout_ms)
    if not fetch_result.get("fetched"):
        return {"fetched": False, "found": False, "error": fetch_result.get("error")}

    extracted = extract_cbe_data(fetch_result.get("text", ""))
    return {"fetched": True, **extracted}
