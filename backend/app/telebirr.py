"""
NATRA backend — Telebirr receipt page fetching and data extraction.

Phase 2, Task 22: given a Telebirr receipt URL
(https://transactioninfo.ethiotelecom.et/...), load it with Playwright
and return its raw rendered page content (HTML + visible text). Mirrors
`cbe.py`'s Task 20 exactly, reusing `_load_page()` as-is (it was already
written host-agnostic for this reason) — the only new code there was
the Telebirr host/URL validation.

Phase 2, Task 23: `extract_telebirr_data()` parses that visible text
into structured fields (transaction/receipt number, settled amount,
total amount paid, payer/receiver names, date, reason). **Best-effort,
not yet confirmed against a real Telebirr receipt page** — this sandbox
cannot reach `transactioninfo.ethiotelecom.et` (see CURRENT_STATUS.md),
so the patterns below are based on the bilingual (Amharic/English) field
labels consistently reported across independently published Telebirr
receipts — "Receipt No.", "Payment date", "Settled Amount", "Total
Amount Paid", "Credited Party name", "Payment Reason" — a public,
structural fact about the page layout, not from a page this codebase
has actually fetched itself. Telebirr's label set is genuinely different
from CBE's, so these patterns are new, not copied from `cbe.py` — only
the overall function shape (best-effort, never raises, `found` flag,
`likely_not_found` heuristic) mirrors `extract_cbe_data()`. No amount/
status *validation* against a product's price happens here — that's
Task 24. No duplicate-payment check — that's Task 25.

Same standing gap as Task 20: this sandbox's network policy cannot reach
`transactioninfo.ethiotelecom.et` (it isn't on the allowed egress list),
so the fetch mechanism itself is verified the same way Task 20's was —
against an allowed stand-in domain — with the real-host gap flagged
below rather than hidden.
"""

import re
from urllib.parse import urlparse

from app.cbe import DEFAULT_TIMEOUT_MS, _load_page

# Per CLAUDE_MASTER_PROMPT.md section 5: Telebirr receipt URLs look like
# https://transactioninfo.ethiotelecom.et/receipt/...
TELEBIRR_RECEIPT_HOST = "transactioninfo.ethiotelecom.et"


class InvalidReceiptUrlError(ValueError):
    """Raised when a URL is not a Telebirr receipt URL."""


def _validate_telebirr_url(url: str) -> None:
    """
    Reject anything that isn't an https URL on exactly
    `transactioninfo.ethiotelecom.et`. Same reasoning as
    `cbe._validate_cbe_url()`: using `urlparse(...).hostname` (not a
    substring/`endswith` check) means a lookalike host such as
    `transactioninfo.ethiotelecom.et.evil.com` is correctly rejected,
    not accidentally accepted.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != TELEBIRR_RECEIPT_HOST:
        raise InvalidReceiptUrlError(
            f"Not a Telebirr receipt URL (expected https://{TELEBIRR_RECEIPT_HOST}/...): {url!r}"
        )


def fetch_telebirr_receipt(url: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> dict:
    """
    Load a Telebirr receipt URL and return its raw rendered content.

    Returns a dict, never raises:
      Success: {"fetched": True, "html": "...", "text": "..."}
      Failure: {"fetched": False, "error": "..."}
    Failure covers both a URL that isn't a Telebirr receipt URL and any
    navigation/browser failure (timeout, DNS, non-200, etc.) — same
    shape as `cbe.fetch_cbe_receipt()` so callers can treat both
    providers uniformly.
    """
    try:
        _validate_telebirr_url(url)
    except InvalidReceiptUrlError as exc:
        return {"fetched": False, "error": str(exc)}

    return _load_page(url, timeout_ms=timeout_ms)


# --- Task 23: data extraction --------------------------------------------
#
# Hardened against a real Telebirr receipt (task 67 follow-up:
# https://transactioninfo.ethiotelecom.et/receipt/DI27DWJKTT). This
# uncovered three real bugs that meant the *original* patterns would
# never have matched a genuine receipt at all:
#   1. The reference-number label is "Invoice No." on the real page,
#      not "Receipt No." — every receipt would have come back with
#      `transaction_ref: None` and therefore `found: False`.
#   2. The real label is "Total Paid Amount", not "Total Amount Paid"
#      (word order reversed from what was assumed) — `total_paid`
#      always came back `None`.
#   3. Real amounts render as bare integers ("175 Birr", "177 Birr"),
#      never with two decimal places — the old `_AMOUNT_PATTERN`
#      required `\.\d{2}` and so never matched *any* amount on a real
#      page, CBE or Telebirr.
# A fourth, non-parsing bug fixed alongside this: `get_paid_amount()`
# in validation.py preferred `total_paid` over `settled_amount`, but
# `total_paid` includes Telebirr's own service fee (177 birr vs. the
# 175 birr actually settled to the receiver) — a buyer paying exactly
# the listed price would have failed validation. Swapped to prefer
# `settled_amount`, mirroring the reasoning `cbe.py` already documents
# for preferring `transferred_amount` over `total_debited`.
#
# The real "Invoice details" row (Invoice No. / Payment date / Settled
# Amount) renders as an actual HTML `<table>`, and it isn't confirmed
# whether Playwright's `inner_text()` keeps a table's header and data
# cells adjacent on one line or puts them on separate lines — both are
# plausible DOM-to-text linearizations for a `<table>`. So each of
# those three fields gets an adjacency-first pattern (works if the
# label and value stay on one line) with a windowed fallback pattern
# that tolerates the label and value being separated by a line break or
# other table cells, the same "search forward within N characters"
# approach `cbe.py` already uses for `_TOTAL_DEBITED_RE`.

# Accepts "175", "175.00", or "1,234.56" — real Telebirr amounts observed
# on the sample receipt have no decimal places at all. The leading
# `(?<![A-Za-z0-9])` guards the *windowed* fallback searches below: without
# it, a windowed search starting mid-token (e.g. the "27" inside the
# invoice number "DI27DWJKTT") would match a stray embedded digit run
# instead of skipping past the whole token to the real amount later in
# the table row — confirmed with a reconstructed table-linearized sample
# during this hardening pass.
_AMOUNT_PATTERN = r"(?<![A-Za-z0-9])([\d][\d,]*(?:\.\d{1,2})?)\s*(?:Birr|ETB|birr)?"
# Used only by the *windowed* fallback searches below, where the gap
# between label and value can be wide enough to also contain a date
# ("02-09-2026 18:21:14" is four separate digit runs — "02", "09",
# "2026", "18", "21", "14" — any of which the loose pattern above would
# happily match as if it were the amount). Requiring the currency word
# is a strong, empirically-confirmed anchor (every real amount on both
# sample receipts is followed by "Birr") that a date's digit runs never
# have, so it reliably skips past a date sitting between the label and
# the real amount.
_AMOUNT_PATTERN_STRICT = r"(?<![A-Za-z0-9])([\d][\d,]*(?:\.\d{1,2})?)\s*(?:Birr|ETB|birr)"

_RECEIPT_NO_RE = re.compile(
    # "Invoice No." is the confirmed real label; "Receipt No." kept as
    # an alternative in case a different Telebirr receipt template uses
    # that wording instead. Observed real values (e.g. "DI27DWJKTT")
    # run shorter than CBE's references and mix letters/digits with no
    # fixed length documented publicly, so this uses a bounded range
    # rather than an exact length.
    r"(?i:Invoice\s*No\.?|Receipt\s*No\.?)\s*[:\-]?\s*([A-Z0-9]{6,16})(?=\s|$|[A-Z][a-z])"
)
# Windowed fallback: allows the label and value to be separated by
# other text/line breaks (e.g. sibling table header cells), up to a
# bounded distance, so a `<table>` linearization that doesn't keep them
# adjacent still resolves correctly.
_RECEIPT_NO_WINDOW_RE = re.compile(
    r"(?:Invoice\s*No\.?|Receipt\s*No\.?).{0,150}?([A-Z0-9]{8,14})(?=\s|$)",
    re.IGNORECASE | re.DOTALL,
)
_SETTLED_AMOUNT_RE = re.compile(
    r"(?i:Settled\s*Amount)\s*[:\-]?\s*" + _AMOUNT_PATTERN
)
_SETTLED_AMOUNT_WINDOW_RE = re.compile(
    r"Settled\s*Amount.{0,80}?" + _AMOUNT_PATTERN_STRICT, re.IGNORECASE | re.DOTALL
)
# Matches both word orders ("Total Paid Amount" — confirmed real label
# — and "Total Amount Paid" — the original assumption, kept as a
# fallback in case another template uses it).
_TOTAL_PAID_RE = re.compile(
    r"(?i:Total\s*Paid\s*Amount|Total\s*Amount\s*Paid)\s*[:\-]?\s*" + _AMOUNT_PATTERN
)
_TOTAL_PAID_WINDOW_RE = re.compile(
    r"(?:Total\s*Paid\s*Amount|Total\s*Amount\s*Paid).{0,80}?" + _AMOUNT_PATTERN_STRICT,
    re.IGNORECASE | re.DOTALL,
)
_PAYER_RE = re.compile(
    r"(?i:Payer(?:\s*Name)?)\s*[:\-]?\s*([A-Z][A-Za-z .]{1,80}?)\s*(?:Receipt|Payment|Credited|\r?\n|$)"
)
_RECEIVER_RE = re.compile(
    r"(?i:Credited\s*Party\s*name)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9 .]{1,80}?)"
    r"\s*(?:Credited|Bank|Receipt|Payment|\r?\n|$)"
)
# Real date format confirmed: "02-09-2026 18:21:14" (DD-MM-YYYY, 24h
# time, no AM/PM) — already covered by the existing hyphen-tolerant
# pattern, kept as-is. Windowed fallback added for the same table-
# linearization reason as the fields above.
_PAYMENT_DATE_RE = re.compile(
    r"(?i:Payment\s*date)\s*[:\-]?\s*([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{2,4}[^\r\n]*)"
)
_PAYMENT_DATE_WINDOW_RE = re.compile(
    r"Payment\s*date.{0,60}?([0-9]{1,2}[/\-][0-9]{1,2}[/\-][0-9]{2,4}(?:\s+[0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?)?)",
    re.IGNORECASE | re.DOTALL,
)
_REASON_RE = re.compile(
    r"(?i:Payment\s*Reason)\s*[:\-]?\s*([^\r\n]{1,120}?)"
    r"\s*(?:(?i:Payment\s*channel)|(?i:Payment\s*Mode)|$)"
)
# Confirmed against the real sample: "transaction status Completed"
# (bilingual label "የክፍያው ሁኔታ/transaction status").
_STATUS_RE = re.compile(r"(?i:transaction\s*status)\s*[:\-]?\s*([A-Za-z]+)")
_COMPLETED_STATUSES = {"completed", "success", "successful"}

# Substrings that, if present when none of the structured fields were
# found, suggest the page is a "not found"/error response rather than a
# genuine receipt — best-effort, unconfirmed against a real error page,
# mirroring the same heuristic used in cbe.py.
_NOT_FOUND_HINTS = ("not found", "invalid", "no record", "does not exist", "error")


def _parse_amount(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def extract_telebirr_data(text: str) -> dict:
    """
    Best-effort extraction of transaction fields from a Telebirr receipt
    page's visible text — i.e. the `"text"` value
    `fetch_telebirr_receipt()` returns on success.

    Never raises. Returns:
      {
        "found": bool,                      # ref + amount both located
        "transaction_ref": str | None,       # e.g. "DI27DWJKTT" (Invoice No.)
        "settled_amount": float | None,
        "total_paid": float | None,
        "payer_name": str | None,
        "receiver_name": str | None,         # "Credited Party name"
        "payment_date": str | None,
        "reason": str | None,
        "status": str | None,               # raw status word, e.g. "Completed"
        "status_ok": bool,                  # status is a known-completed value
        "likely_not_found": bool,           # page looks like an error/not-found response
      }

    `found` is True only when both a receipt/transaction number and an
    amount (`settled_amount`, falling back to `total_paid` if it wasn't
    present — see the module docstring for why `settled_amount` is now
    primary) were located. `status_ok` is a separate, additional gate:
    True only when a status word was found AND it's a recognized
    "completed" value — mirroring `cbe.py`'s `status_ok`, and closing
    the same gap: a reference+amount pair from a PENDING/FAILED/
    REVERSED transaction must not be treated as valid just because the
    page happened to have those two fields. The other fields are
    extracted best-effort and may be `None` even on a genuine receipt
    if the page's exact wording differs from what these patterns
    expect.
    """
    text = text or ""

    ref_match = _RECEIPT_NO_RE.search(text) or _RECEIPT_NO_WINDOW_RE.search(text)
    settled_match = _SETTLED_AMOUNT_RE.search(text) or _SETTLED_AMOUNT_WINDOW_RE.search(text)
    total_match = _TOTAL_PAID_RE.search(text) or _TOTAL_PAID_WINDOW_RE.search(text)
    payer_match = _PAYER_RE.search(text)
    receiver_match = _RECEIVER_RE.search(text)
    date_match = _PAYMENT_DATE_RE.search(text) or _PAYMENT_DATE_WINDOW_RE.search(text)
    reason_match = _REASON_RE.search(text)
    status_match = _STATUS_RE.search(text)

    transaction_ref = ref_match.group(1).upper() if ref_match else None
    total_paid = _parse_amount(total_match.group(1)) if total_match else None
    settled_amount = _parse_amount(settled_match.group(1)) if settled_match else None
    payer_name = payer_match.group(1).strip() if payer_match else None
    receiver_name = receiver_match.group(1).strip() if receiver_match else None
    payment_date = date_match.group(1).strip() if date_match else None
    reason = reason_match.group(1).strip() if reason_match else None
    status = status_match.group(1).strip() if status_match else None
    status_ok = status is not None and status.lower() in _COMPLETED_STATUSES

    # Primary amount is what was actually credited to the receiver
    # (settled_amount), not what the payer's wallet was debited for
    # (total_paid, which includes Telebirr's own service fee) — see
    # module docstring, bug #4.
    primary_amount = settled_amount if settled_amount is not None else total_paid
    found = transaction_ref is not None and primary_amount is not None
    likely_not_found = not found and any(hint in text.lower() for hint in _NOT_FOUND_HINTS)

    return {
        "found": found,
        "transaction_ref": transaction_ref,
        "settled_amount": settled_amount,
        "total_paid": total_paid,
        "payer_name": payer_name,
        "receiver_name": receiver_name,
        "payment_date": payment_date,
        "reason": reason,
        "status": status,
        "status_ok": status_ok,
        "likely_not_found": likely_not_found,
    }


def parse_telebirr_receipt(url: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> dict:
    """
    Convenience wrapper: fetch a Telebirr receipt URL and extract its
    data in one call. Returns the fetch failure shape (`{"fetched":
    False, "error": ...}`, with `"found": False` merged in for a
    consistent shape to check) if fetching failed, otherwise
    `extract_telebirr_data()`'s result merged with `{"fetched": True}`.

    Not used by any endpoint yet — Task 26's verification endpoint will
    be the first caller (mirrors `cbe.parse_cbe_receipt()`).
    """
    fetch_result = fetch_telebirr_receipt(url, timeout_ms=timeout_ms)
    if not fetch_result.get("fetched"):
        return {"fetched": False, "found": False, "error": fetch_result.get("error")}

    extracted = extract_telebirr_data(fetch_result.get("text", ""))
    return {"fetched": True, **extracted}
