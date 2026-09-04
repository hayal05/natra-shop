"""
Task 75: automated tests for the receipts flow — `POST
/products/{product_id}/receipt` (Task 13), `POST
/receipts/{receipt_id}/verify` (Task 26), and `GET
/receipts/{receipt_id}/delivery` (Task 27). Third item in Phase 7's
schedule (see PROJECT_ROADMAP.md), flagged there as the heaviest of
the backend tasks. Extends Tasks 72-74's pytest + `fake_oracle.py`
pattern with a `receipts` table (see that file's docstring for the
new query shapes) and, per this task's own scope note, does NOT stand
up fakes for Playwright/`browser.py`/`cbe.py`/`telebirr.py` — instead
it monkeypatches `app.main.parse_cbe_receipt` / `parse_telebirr_receipt`
directly (`_patch_cbe`/`_patch_telebirr` below), the same pattern
`conftest.py` already uses for the Brevo email functions. That keeps
this suite exercising the real endpoint code (provider detection,
`validate_payment()`, `is_duplicate_transaction()`, `_record_sale()`)
without ever touching a real browser or network call.

Covers, against the real endpoint code with only the DB layer and the
two provider-parsing functions faked:

- POST /products/{product_id}/receipt: creates a `pending`
  (status=NULL) receipt row, 404 for a malformed and for a
  well-formed-but-unknown product id, 422 for a `receipt_url` that
  isn't http(s), allows more than one submission for the same
  product.
- POST /receipts/{receipt_id}/verify: 404 for a malformed and for a
  well-formed-but-unknown receipt id; the full reject path for every
  distinct `reason` the pipeline can produce (`unsupported_provider`,
  `fetch_failed`, `not_found`, `not_completed`, `amount_mismatch`,
  `duplicate_transaction`); the success path for both CBE and
  Telebirr, including the `sales` row `_record_sale()` writes
  (gross/commission/payable, snapshotting the current
  `commission_rate`); idempotency for an already-`verified` receipt
  (returns the stored result without re-invoking either provider
  parser).
- GET /receipts/{receipt_id}/delivery: 404 for a malformed and for a
  well-formed-but-unknown receipt id, 403 (never `drive_link`) for a
  receipt that is pending or rejected, 200 with `drive_link` only once
  `status = 'verified'`.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient


def _register_verified_seller(
    client: TestClient,
    sent_emails: dict[str, list[tuple[str, str]]],
    email: str = "seller@example.com",
    password: str = "correct-horse-1",
) -> str:
    """Same real register -> verify -> login flow as test_products.py's
    helper — returns the bearer token."""
    client.post("/sellers/register", json={"email": email, "password": password})
    _, code = sent_emails["signup"][-1]
    client.post("/sellers/verify-email", json={"email": email, "otp": code})
    login_resp = client.post(
        "/sellers/login", json={"email": email, "password": password}
    )
    return login_resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_product(
    client: TestClient,
    token: str,
    *,
    price: float = 199.99,
    drive_link: str = "https://drive.google.com/file/d/abc123",
) -> str:
    """Registers no seller of its own — takes an already-authenticated
    token — and returns the new product's id."""
    resp = client.post(
        "/products",
        headers=_auth(token),
        json={
            "name": "Ethiopian Coffee Guide",
            "price": price,
            "description": "A short ebook.",
            "drive_link": drive_link,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _submit_receipt(
    client: TestClient, product_id: str, receipt_url: str = "https://mbreciept.cbe.com.et/receipt/abc"
):
    return client.post(
        f"/products/{product_id}/receipt", json={"receipt_url": receipt_url}
    )


CBE_URL = "https://mbreciept.cbe.com.et/receipt/abc"
TELEBIRR_URL = "https://transactioninfo.ethiotelecom.et/receipt/DI27DWJKTT"
UNKNOWN_HOST_URL = "https://example.com/receipt/abc"

# A well-formed-but-nonexistent RAW(16) hex id — 32 hex chars, never
# inserted by any test, so every lookup against it 404s.
NONEXISTENT_ID = "0" * 32
MALFORMED_ID = "not-a-valid-id"


def _cbe_result(**overrides: Any) -> dict[str, Any]:
    """A minimal-but-complete `extract_cbe_data()`-shaped dict — every
    key `validate_payment()`/response-building code might touch,
    defaulted to a fully valid, matching-price payment. Individual
    tests override just the field(s) they need to exercise a
    particular reject reason."""
    base = {
        "fetched": True,
        "found": True,
        "transaction_ref": "FT26239NB22Z",
        "transferred_amount": 199.99,
        "total_debited": 199.99,
        "payer_name": "Abebe Kebede",
        "receiver_name": "NATRA",
        "payment_date": "Aug 27, 2026, 3:39 PM",
        "reason": "Payment",
        "status": "COMPLETED",
        "status_ok": True,
        "likely_not_found": False,
    }
    base.update(overrides)
    return base


def _telebirr_result(**overrides: Any) -> dict[str, Any]:
    base = {
        "fetched": True,
        "found": True,
        "transaction_ref": "DI27DWJKTT",
        "settled_amount": 199.99,
        "total_paid": 201.73,
        "payer_name": "Abebe Kebede",
        "receiver_name": "NATRA",
        "payment_date": "02-09-2026 18:21:14",
        "reason": "Payment",
        "status": "Completed",
        "status_ok": True,
        "likely_not_found": False,
    }
    base.update(overrides)
    return base


def _patch_cbe(monkeypatch: pytest.MonkeyPatch, result: dict[str, Any]) -> list[str]:
    """Monkeypatches `app.main.parse_cbe_receipt` to return `result`
    regardless of the URL passed in, and returns the list of URLs it
    was actually called with (so a test can assert it was — or, for
    the idempotency test, was NOT — invoked)."""
    from app import main

    calls: list[str] = []

    def _fake(url: str, timeout_ms: int = 15000) -> dict[str, Any]:
        calls.append(url)
        return result

    monkeypatch.setattr(main, "parse_cbe_receipt", _fake)
    return calls


def _patch_telebirr(
    monkeypatch: pytest.MonkeyPatch, result: dict[str, Any]
) -> list[str]:
    from app import main

    calls: list[str] = []

    def _fake(url: str, timeout_ms: int = 15000) -> dict[str, Any]:
        calls.append(url)
        return result

    monkeypatch.setattr(main, "parse_telebirr_receipt", _fake)
    return calls


def _seller_and_product(
    client: TestClient, sent_emails, price: float = 199.99
) -> tuple[str, str]:
    """Returns (token, product_id)."""
    token = _register_verified_seller(client, sent_emails)
    product_id = _create_product(client, token, price=price)
    return token, product_id


class TestSubmitReceipt:
    def test_submit_receipt_succeeds(self, client: TestClient, sent_emails):
        _, product_id = _seller_and_product(client, sent_emails)

        resp = _submit_receipt(client, product_id, CBE_URL)

        assert resp.status_code == 201
        body = resp.json()
        assert body["product_id"] == product_id
        assert body["receipt_url"] == CBE_URL
        assert len(body["id"]) == 32

    def test_submit_receipt_allows_multiple_submissions(
        self, client: TestClient, sent_emails
    ):
        _, product_id = _seller_and_product(client, sent_emails)

        first = _submit_receipt(client, product_id, CBE_URL)
        second = _submit_receipt(client, product_id, TELEBIRR_URL)

        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["id"] != second.json()["id"]

    def test_submit_receipt_404_for_malformed_product_id(self, client: TestClient):
        resp = _submit_receipt(client, MALFORMED_ID, CBE_URL)

        assert resp.status_code == 404

    def test_submit_receipt_404_for_unknown_product_id(self, client: TestClient):
        resp = _submit_receipt(client, NONEXISTENT_ID, CBE_URL)

        assert resp.status_code == 404

    def test_submit_receipt_422_for_non_url(self, client: TestClient, sent_emails):
        _, product_id = _seller_and_product(client, sent_emails)

        resp = _submit_receipt(client, product_id, "not-a-url")

        assert resp.status_code == 422

    def test_submit_receipt_422_for_empty_url(self, client: TestClient, sent_emails):
        _, product_id = _seller_and_product(client, sent_emails)

        resp = client.post(f"/products/{product_id}/receipt", json={"receipt_url": ""})

        assert resp.status_code == 422

    def test_submit_receipt_requires_no_authentication(
        self, client: TestClient, sent_emails
    ):
        # Public endpoint — a buyer holds no account. Sanity check that
        # it succeeds with no Authorization header at all (every other
        # test in this class already does this implicitly).
        _, product_id = _seller_and_product(client, sent_emails)

        resp = client.post(
            f"/products/{product_id}/receipt",
            json={"receipt_url": CBE_URL},
        )

        assert resp.status_code == 201


class TestVerifyReceipt:
    def test_verify_404_for_malformed_receipt_id(self, client: TestClient):
        resp = client.post(f"/receipts/{MALFORMED_ID}/verify")

        assert resp.status_code == 404

    def test_verify_404_for_unknown_receipt_id(self, client: TestClient):
        resp = client.post(f"/receipts/{NONEXISTENT_ID}/verify")

        assert resp.status_code == 404

    def test_verify_succeeds_for_cbe(
        self, client: TestClient, sent_emails, monkeypatch, store
    ):
        _, product_id = _seller_and_product(client, sent_emails, price=199.99)
        receipt_id = _submit_receipt(client, product_id, CBE_URL).json()["id"]
        calls = _patch_cbe(monkeypatch, _cbe_result())

        resp = client.post(f"/receipts/{receipt_id}/verify")

        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "id": receipt_id,
            "product_id": product_id,
            "status": "verified",
            "reason": None,
            "transaction_ref": "FT26239NB22Z",
            "verified_amount": 199.99,
            "provider": "cbe",
        }
        assert calls == [CBE_URL]

        # _record_sale() side effect: one sales row, commission
        # snapshotted from admin_settings' default 10.00%.
        assert len(store.sales) == 1
        sale = store.sales[0]
        assert sale.receipt_id_hex == receipt_id
        assert sale.product_id_hex == product_id
        assert sale.gross_amount == 199.99
        assert sale.commission_rate == 10.00
        assert sale.commission_amount == 20.0  # round(199.99 * 0.10, 2)
        assert sale.seller_payable == 179.99

    def test_verify_succeeds_for_telebirr(
        self, client: TestClient, sent_emails, monkeypatch
    ):
        _, product_id = _seller_and_product(client, sent_emails, price=199.99)
        receipt_id = _submit_receipt(client, product_id, TELEBIRR_URL).json()["id"]
        calls = _patch_telebirr(monkeypatch, _telebirr_result())

        resp = client.post(f"/receipts/{receipt_id}/verify")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "verified"
        assert body["provider"] == "telebirr"
        assert body["transaction_ref"] == "DI27DWJKTT"
        # settled_amount (199.99), not total_paid (201.73) — see
        # get_paid_amount()'s docstring.
        assert body["verified_amount"] == 199.99
        assert calls == [TELEBIRR_URL]

    def test_verify_is_idempotent_for_already_verified_receipt(
        self, client: TestClient, sent_emails, monkeypatch
    ):
        _, product_id = _seller_and_product(client, sent_emails, price=199.99)
        receipt_id = _submit_receipt(client, product_id, CBE_URL).json()["id"]
        _patch_cbe(monkeypatch, _cbe_result())
        first = client.post(f"/receipts/{receipt_id}/verify")
        assert first.status_code == 200
        assert first.json()["status"] == "verified"

        # Re-patch so any second invocation of the parser would raise —
        # proves the idempotent path returns the stored result without
        # re-fetching or re-running the pipeline at all.
        from app import main

        def _explode(url: str, timeout_ms: int = 15000):
            raise AssertionError(
                "parse_cbe_receipt should not be called again for an "
                "already-verified receipt"
            )

        monkeypatch.setattr(main, "parse_cbe_receipt", _explode)

        second = client.post(f"/receipts/{receipt_id}/verify")

        assert second.status_code == 200
        assert second.json() == first.json()

    def test_verify_rejects_unsupported_provider(
        self, client: TestClient, sent_emails
    ):
        _, product_id = _seller_and_product(client, sent_emails)
        receipt_id = _submit_receipt(client, product_id, UNKNOWN_HOST_URL).json()["id"]

        resp = client.post(f"/receipts/{receipt_id}/verify")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "rejected"
        assert body["reason"] == "unsupported_provider"
        assert body["provider"] is None
        assert body["transaction_ref"] is None

    def test_verify_rejects_on_fetch_failure(
        self, client: TestClient, sent_emails, monkeypatch
    ):
        _, product_id = _seller_and_product(client, sent_emails)
        receipt_id = _submit_receipt(client, product_id, CBE_URL).json()["id"]
        _patch_cbe(monkeypatch, {"fetched": False, "found": False, "error": "timeout"})

        resp = client.post(f"/receipts/{receipt_id}/verify")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "rejected"
        assert body["reason"] == "fetch_failed"
        assert body["provider"] == "cbe"

    def test_verify_rejects_when_not_found(
        self, client: TestClient, sent_emails, monkeypatch
    ):
        _, product_id = _seller_and_product(client, sent_emails)
        receipt_id = _submit_receipt(client, product_id, CBE_URL).json()["id"]
        _patch_cbe(
            monkeypatch,
            _cbe_result(found=False, transaction_ref=None, transferred_amount=None),
        )

        resp = client.post(f"/receipts/{receipt_id}/verify")

        body = resp.json()
        assert body["status"] == "rejected"
        assert body["reason"] == "not_found"

    def test_verify_rejects_when_not_completed(
        self, client: TestClient, sent_emails, monkeypatch
    ):
        _, product_id = _seller_and_product(client, sent_emails)
        receipt_id = _submit_receipt(client, product_id, CBE_URL).json()["id"]
        _patch_cbe(monkeypatch, _cbe_result(status="PENDING", status_ok=False))

        resp = client.post(f"/receipts/{receipt_id}/verify")

        body = resp.json()
        assert body["status"] == "rejected"
        assert body["reason"] == "not_completed"

    def test_verify_rejects_on_amount_mismatch(
        self, client: TestClient, sent_emails, monkeypatch
    ):
        _, product_id = _seller_and_product(client, sent_emails, price=199.99)
        receipt_id = _submit_receipt(client, product_id, CBE_URL).json()["id"]
        _patch_cbe(monkeypatch, _cbe_result(transferred_amount=50.00))

        resp = client.post(f"/receipts/{receipt_id}/verify")

        body = resp.json()
        assert body["status"] == "rejected"
        assert body["reason"] == "amount_mismatch"
        # The reference is still recorded even on a rejected receipt —
        # see _reject_receipt()'s own docstring on why that's safe.
        assert body["transaction_ref"] == "FT26239NB22Z"

    def test_verify_rejects_duplicate_transaction(
        self, client: TestClient, sent_emails, monkeypatch
    ):
        # First product/receipt: verifies successfully and "claims"
        # transaction_ref FT26239NB22Z for CBE.
        token, product_a = _seller_and_product(client, sent_emails, price=199.99)
        receipt_a = _submit_receipt(client, product_a, CBE_URL).json()["id"]
        _patch_cbe(monkeypatch, _cbe_result())
        first = client.post(f"/receipts/{receipt_a}/verify")
        assert first.json()["status"] == "verified"

        # Second product, same seller, same price — a different buyer
        # (or a retry) tries to reuse the exact same real-world payment.
        product_b = _create_product(client, token, price=199.99)
        receipt_b = _submit_receipt(client, product_b, CBE_URL).json()["id"]
        # Same transaction_ref as before — is_duplicate_transaction()
        # must catch this even though it's a different receipt/product.
        _patch_cbe(monkeypatch, _cbe_result())

        resp = client.post(f"/receipts/{receipt_b}/verify")

        body = resp.json()
        assert body["status"] == "rejected"
        assert body["reason"] == "duplicate_transaction"
        assert body["transaction_ref"] == "FT26239NB22Z"


class TestReceiptDelivery:
    def test_delivery_404_for_malformed_receipt_id(self, client: TestClient):
        resp = client.get(f"/receipts/{MALFORMED_ID}/delivery")

        assert resp.status_code == 404

    def test_delivery_404_for_unknown_receipt_id(self, client: TestClient):
        resp = client.get(f"/receipts/{NONEXISTENT_ID}/delivery")

        assert resp.status_code == 404

    def test_delivery_403_for_pending_receipt(self, client: TestClient, sent_emails):
        _, product_id = _seller_and_product(client, sent_emails)
        receipt_id = _submit_receipt(client, product_id, CBE_URL).json()["id"]

        resp = client.get(f"/receipts/{receipt_id}/delivery")

        assert resp.status_code == 403
        assert "drive_link" not in resp.text

    def test_delivery_403_for_rejected_receipt(self, client: TestClient, sent_emails):
        _, product_id = _seller_and_product(client, sent_emails)
        receipt_id = _submit_receipt(client, product_id, UNKNOWN_HOST_URL).json()["id"]
        client.post(f"/receipts/{receipt_id}/verify")  # -> rejected

        resp = client.get(f"/receipts/{receipt_id}/delivery")

        assert resp.status_code == 403

    def test_delivery_succeeds_for_verified_receipt(
        self, client: TestClient, sent_emails, monkeypatch
    ):
        drive_link = "https://drive.google.com/file/d/verified-product"
        token = _register_verified_seller(client, sent_emails)
        # Created directly (not via the shared `_create_product` helper)
        # so this test can assert on a `drive_link` it controls.
        product_resp = client.post(
            "/products",
            headers=_auth(token),
            json={
                "name": "Specific Drive Link Product",
                "price": 199.99,
                "description": "",
                "drive_link": drive_link,
            },
        )
        product_id = product_resp.json()["id"]
        receipt_id = _submit_receipt(client, product_id, CBE_URL).json()["id"]
        _patch_cbe(monkeypatch, _cbe_result())
        client.post(f"/receipts/{receipt_id}/verify")

        resp = client.get(f"/receipts/{receipt_id}/delivery")

        assert resp.status_code == 200
        assert resp.json() == {
            "receipt_id": receipt_id,
            "product_id": product_id,
            "drive_link": drive_link,
        }
