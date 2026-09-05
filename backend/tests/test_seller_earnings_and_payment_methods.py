"""
Task 74: automated tests for seller earnings and seller payment
methods — the second item in Phase 7's schedule (see
PROJECT_ROADMAP.md). Extends Task 72/73's pytest + `fake_oracle.py`
pattern.

Covers, against the real endpoint code with only the DB layer faked
(see conftest.py / fake_oracle.py):

- GET /sellers/earnings: all-zero response with no sales, correct
  aggregation (total_sales/gross/commission/payable) over seeded
  `sales` rows, seller isolation (never another seller's sales), and
  the settled/unsettled split against seeded `settlements` rows
  ('pending' settlements excluded from settled_total, matching
  get_seller_earnings()'s docstring). Same auth guard as every other
  seller-only endpoint (401 with no token, 403 with an admin token).
- GET/PUT /sellers/payment-methods: all-null default, seller
  isolation, PUT's "omit or null = leave unchanged, empty string =
  clear" convention (see update_seller_payment_methods()'s
  docstring), field-length validation, same auth guard.

No in-scope endpoint writes `sales`/`settlements` (that's Task 75's
receipts flow and Task 77's admin settlements work), so those tests
seed `store.sales`/`store.settlements` directly — see
`fake_oracle.py`'s `SalesRow`/`SettlementRow` docstrings.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.fake_oracle import SalesRow, SettlementRow


def _admin_token() -> str:
    # Deferred import — see test_products.py's identical helper for why.
    from app.auth import create_admin_access_token

    return create_admin_access_token("admin@example.com")


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


def _seller_id(store, email: str) -> str:
    return store.sellers[email].id_hex


class TestSellerEarnings:
    def test_all_zero_with_no_sales(self, client: TestClient, sent_emails):
        token = _register_verified_seller(client, sent_emails)

        resp = client.get("/sellers/earnings", headers=_auth(token))

        assert resp.status_code == 200
        assert resp.json() == {
            "total_sales": 0,
            "gross_amount_total": 0.0,
            "commission_total": 0.0,
            "seller_payable_total": 0.0,
            "settled_total": 0.0,
            "unsettled_total": 0.0,
        }

    def test_aggregates_seeded_sales(self, client: TestClient, sent_emails, store):
        token = _register_verified_seller(client, sent_emails)
        seller_id = _seller_id(store, "seller@example.com")
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_id,
                gross_amount=100.0,
                commission_amount=10.0,
                seller_payable=90.0,
            )
        )
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_id,
                gross_amount=50.0,
                commission_amount=5.0,
                seller_payable=45.0,
            )
        )

        resp = client.get("/sellers/earnings", headers=_auth(token))

        body = resp.json()
        assert body["total_sales"] == 2
        assert body["gross_amount_total"] == 150.0
        assert body["commission_total"] == 15.0
        assert body["seller_payable_total"] == 135.0

    def test_never_counts_another_sellers_sales(
        self, client: TestClient, sent_emails, store
    ):
        seller_a_token = _register_verified_seller(
            client, sent_emails, email="a@example.com"
        )
        _register_verified_seller(client, sent_emails, email="b@example.com")
        seller_b_id = _seller_id(store, "b@example.com")
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_b_id,
                gross_amount=999.0,
                commission_amount=99.0,
                seller_payable=900.0,
            )
        )

        resp = client.get("/sellers/earnings", headers=_auth(seller_a_token))

        body = resp.json()
        assert body["total_sales"] == 0
        assert body["gross_amount_total"] == 0.0

    def test_settled_excludes_pending_settlements(
        self, client: TestClient, sent_emails, store
    ):
        token = _register_verified_seller(client, sent_emails)
        seller_id = _seller_id(store, "seller@example.com")
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_id,
                gross_amount=100.0,
                commission_amount=0.0,
                seller_payable=100.0,
            )
        )
        store.settlements.append(
            SettlementRow(seller_id_hex=seller_id, amount=40.0, status="completed")
        )
        store.settlements.append(
            SettlementRow(seller_id_hex=seller_id, amount=30.0, status="pending")
        )

        resp = client.get("/sellers/earnings", headers=_auth(token))

        body = resp.json()
        assert body["seller_payable_total"] == 100.0
        assert body["settled_total"] == 40.0
        assert body["unsettled_total"] == 60.0

    def test_requires_authentication(self, client: TestClient):
        resp = client.get("/sellers/earnings")
        assert resp.status_code == 401

    def test_rejects_admin_token(self, client: TestClient):
        resp = client.get("/sellers/earnings", headers=_auth(_admin_token()))
        assert resp.status_code == 403


class TestGetPaymentMethods:
    def test_defaults_to_all_null(self, client: TestClient, sent_emails):
        token = _register_verified_seller(client, sent_emails)

        resp = client.get("/sellers/payment-methods", headers=_auth(token))

        assert resp.status_code == 200
        assert resp.json() == {
            "cbe_account_name": None,
            "cbe_account_number": None,
            "telebirr_account_name": None,
            "telebirr_account_number": None,
        }

    def test_requires_authentication(self, client: TestClient):
        resp = client.get("/sellers/payment-methods")
        assert resp.status_code == 401

    def test_rejects_admin_token(self, client: TestClient):
        resp = client.get(
            "/sellers/payment-methods", headers=_auth(_admin_token())
        )
        assert resp.status_code == 403

    def test_never_leaks_another_sellers_payment_methods(
        self, client: TestClient, sent_emails
    ):
        seller_a_token = _register_verified_seller(
            client, sent_emails, email="a@example.com"
        )
        seller_b_token = _register_verified_seller(
            client, sent_emails, email="b@example.com"
        )
        client.put(
            "/sellers/payment-methods",
            headers=_auth(seller_a_token),
            json={"cbe_account_name": "Seller A"},
        )

        resp = client.get("/sellers/payment-methods", headers=_auth(seller_b_token))

        assert resp.json()["cbe_account_name"] is None


class TestUpdatePaymentMethods:
    def test_sets_all_fields_and_they_persist(
        self, client: TestClient, sent_emails
    ):
        token = _register_verified_seller(client, sent_emails)

        put_resp = client.put(
            "/sellers/payment-methods",
            headers=_auth(token),
            json={
                "cbe_account_name": "Almaz Tesfaye",
                "cbe_account_number": "1000123456789",
                "telebirr_account_name": "Almaz Tesfaye",
                "telebirr_account_number": "0911223344",
            },
        )
        assert put_resp.status_code == 200
        assert put_resp.json() == {
            "cbe_account_name": "Almaz Tesfaye",
            "cbe_account_number": "1000123456789",
            "telebirr_account_name": "Almaz Tesfaye",
            "telebirr_account_number": "0911223344",
        }

        get_resp = client.get("/sellers/payment-methods", headers=_auth(token))
        assert get_resp.json() == put_resp.json()

    def test_partial_update_leaves_other_fields_unchanged(
        self, client: TestClient, sent_emails
    ):
        token = _register_verified_seller(client, sent_emails)
        client.put(
            "/sellers/payment-methods",
            headers=_auth(token),
            json={"cbe_account_name": "Almaz Tesfaye", "cbe_account_number": "111"},
        )

        resp = client.put(
            "/sellers/payment-methods",
            headers=_auth(token),
            json={"telebirr_account_number": "0911223344"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["cbe_account_name"] == "Almaz Tesfaye"
        assert body["cbe_account_number"] == "111"
        assert body["telebirr_account_number"] == "0911223344"
        assert body["telebirr_account_name"] is None

    def test_empty_string_clears_a_field(self, client: TestClient, sent_emails):
        token = _register_verified_seller(client, sent_emails)
        client.put(
            "/sellers/payment-methods",
            headers=_auth(token),
            json={"cbe_account_name": "Almaz Tesfaye"},
        )

        resp = client.put(
            "/sellers/payment-methods",
            headers=_auth(token),
            json={"cbe_account_name": ""},
        )

        assert resp.status_code == 200
        assert resp.json()["cbe_account_name"] == ""

    def test_omitting_all_fields_leaves_everything_unchanged(
        self, client: TestClient, sent_emails
    ):
        token = _register_verified_seller(client, sent_emails)
        client.put(
            "/sellers/payment-methods",
            headers=_auth(token),
            json={"cbe_account_name": "Almaz Tesfaye"},
        )

        resp = client.put("/sellers/payment-methods", headers=_auth(token), json={})

        assert resp.status_code == 200
        assert resp.json()["cbe_account_name"] == "Almaz Tesfaye"

    def test_requires_authentication(self, client: TestClient):
        resp = client.put("/sellers/payment-methods", json={"cbe_account_name": "x"})
        assert resp.status_code == 401

    def test_rejects_admin_token(self, client: TestClient):
        resp = client.put(
            "/sellers/payment-methods",
            headers=_auth(_admin_token()),
            json={"cbe_account_name": "x"},
        )
        assert resp.status_code == 403

    def test_only_affects_own_seller(self, client: TestClient, sent_emails):
        seller_a_token = _register_verified_seller(
            client, sent_emails, email="a@example.com"
        )
        seller_b_token = _register_verified_seller(
            client, sent_emails, email="b@example.com"
        )

        client.put(
            "/sellers/payment-methods",
            headers=_auth(seller_a_token),
            json={"cbe_account_name": "Seller A"},
        )

        resp = client.get("/sellers/payment-methods", headers=_auth(seller_b_token))
        assert resp.json()["cbe_account_name"] is None

    def test_rejects_account_name_over_max_length(
        self, client: TestClient, sent_emails
    ):
        token = _register_verified_seller(client, sent_emails)

        resp = client.put(
            "/sellers/payment-methods",
            headers=_auth(token),
            json={"cbe_account_name": "x" * 256},
        )

        assert resp.status_code == 422

    def test_rejects_account_number_over_max_length(
        self, client: TestClient, sent_emails
    ):
        token = _register_verified_seller(client, sent_emails)

        resp = client.put(
            "/sellers/payment-methods",
            headers=_auth(token),
            json={"cbe_account_number": "1" * 65},
        )

        assert resp.status_code == 422
