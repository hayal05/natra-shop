"""
Task 77: automated tests for admin settlements + reports — the fifth
item in Phase 7's schedule (see PROJECT_ROADMAP.md). Extends
`fake_oracle.py`'s `SettlementRow` (Task 74) with a real `id_hex`/
`created_at`/`completed_at`, and adds the `sales`/`settlements` query
shapes `POST`/`GET /admin/settlements`,
`POST /admin/settlements/{id}/complete`, `GET /admin/reports`, and
`GET /admin/reports/by-seller` actually issue. Reuses the
`_admin_token()`/`_auth()`/`_register_verified_seller()` helper
pattern established in `test_products.py` and continued by
`test_seller_earnings_and_payment_methods.py` / `test_receipts.py` /
`test_admin_auth_and_catalog.py`.

Covers, against the real endpoint code with only the DB layer faked
(see conftest.py / fake_oracle.py):

- POST /admin/settlements: creates a 'pending' settlement for a real
  seller; rejects an amount over the seller's unsettled balance (422,
  the Task 42 guard) without inserting a row; 404 for a well-formed but
  nonexistent seller id and for a malformed one; admin-only guard
  (401/403); request validation (amount must be > 0).
- GET /admin/settlements: platform-wide, newest-first, across every
  seller (not just one); empty list with none recorded; admin-only
  guard.
- POST /admin/settlements/{id}/complete: transitions 'pending' ->
  'completed' and stamps completed_at; idempotent when already
  'completed' (returns the stored result unchanged); 404 for a
  nonexistent/malformed id; admin-only guard.
- GET /admin/reports: platform-wide totals across every seller's
  `sales`/`settlements` (not just one), all-zero with no sales yet;
  same six-field shape as GET /sellers/earnings; admin-only guard.
- GET /admin/reports/by-seller: grouped per seller, only sellers with
  at least one sale appear, sums back to GET /admin/reports' totals,
  sorted by unsettled_total descending; admin-only guard.

`sales` rows are seeded directly via `store.sales.append(...)` (same
as Task 74/75 — no in-scope endpoint here writes `sales`); `settlements`
rows are exercised through the real `POST /admin/settlements` /
`POST .../complete` endpoints wherever the test cares about their own
behavior, and seeded directly only where a test just needs a
'completed' settlement already sitting there as a precondition.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.fake_oracle import SalesRow, SettlementRow


def _admin_token() -> str:
    from app.auth import create_admin_access_token

    return create_admin_access_token("admin@example.com")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_verified_seller(
    client: TestClient,
    sent_emails: dict[str, list[tuple[str, str]]],
    email: str = "seller@example.com",
    password: str = "correct-horse-1",
) -> str:
    client.post("/sellers/register", json={"email": email, "password": password})
    _, code = sent_emails["signup"][-1]
    client.post("/sellers/verify-email", json={"email": email, "otp": code})
    login_resp = client.post(
        "/sellers/login", json={"email": email, "password": password}
    )
    return login_resp.json()["access_token"]


def _seller_id(store, email: str) -> str:
    return store.sellers[email].id_hex


class TestCreateSettlement:
    def test_creates_pending_settlement_within_balance(
        self, client: TestClient, sent_emails, store
    ):
        _register_verified_seller(client, sent_emails)
        seller_id = _seller_id(store, "seller@example.com")
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_id,
                gross_amount=500.0,
                commission_amount=50.0,
                seller_payable=450.0,
            )
        )

        resp = client.post(
            "/admin/settlements",
            headers=_auth(_admin_token()),
            json={"seller_id": seller_id, "amount": 200.0},
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["seller_id"] == seller_id
        assert body["amount"] == 200.0
        assert body["status"] == "pending"
        assert body["completed_at"] is None
        assert body["created_at"]
        assert isinstance(body["id"], str) and len(body["id"]) == 32

    def test_rejects_amount_over_unsettled_balance(
        self, client: TestClient, sent_emails, store
    ):
        _register_verified_seller(client, sent_emails)
        seller_id = _seller_id(store, "seller@example.com")
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_id,
                gross_amount=500.0,
                commission_amount=50.0,
                seller_payable=450.0,
            )
        )

        resp = client.post(
            "/admin/settlements",
            headers=_auth(_admin_token()),
            json={"seller_id": seller_id, "amount": 450.01},
        )

        assert resp.status_code == 422
        assert store.settlements == []

    def test_already_completed_settlements_reduce_available_balance(
        self, client: TestClient, sent_emails, store
    ):
        _register_verified_seller(client, sent_emails)
        seller_id = _seller_id(store, "seller@example.com")
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_id,
                gross_amount=500.0,
                commission_amount=50.0,
                seller_payable=450.0,
            )
        )
        store.settlements.append(
            SettlementRow(seller_id_hex=seller_id, amount=400.0, status="completed")
        )

        # Only 50.0 unsettled remains; 100.0 should be rejected.
        resp = client.post(
            "/admin/settlements",
            headers=_auth(_admin_token()),
            json={"seller_id": seller_id, "amount": 100.0},
        )
        assert resp.status_code == 422

        resp = client.post(
            "/admin/settlements",
            headers=_auth(_admin_token()),
            json={"seller_id": seller_id, "amount": 50.0},
        )
        assert resp.status_code == 201

    def test_pending_settlements_do_not_reduce_available_balance(
        self, client: TestClient, sent_emails, store
    ):
        # A 'pending' settlement isn't "settled" yet (see
        # create_settlement's own docstring) — it shouldn't count
        # against a second settlement's balance check.
        _register_verified_seller(client, sent_emails)
        seller_id = _seller_id(store, "seller@example.com")
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_id,
                gross_amount=500.0,
                commission_amount=50.0,
                seller_payable=450.0,
            )
        )
        store.settlements.append(
            SettlementRow(seller_id_hex=seller_id, amount=400.0, status="pending")
        )

        resp = client.post(
            "/admin/settlements",
            headers=_auth(_admin_token()),
            json={"seller_id": seller_id, "amount": 450.0},
        )
        assert resp.status_code == 201

    def test_404_for_nonexistent_seller(self, client: TestClient):
        resp = client.post(
            "/admin/settlements",
            headers=_auth(_admin_token()),
            json={"seller_id": "0" * 32, "amount": 10.0},
        )
        assert resp.status_code == 404

    def test_404_for_malformed_seller_id(self, client: TestClient):
        # 32 chars (passes the request model's min_length) but not
        # valid hex, so it reaches create_settlement()'s own hex check
        # rather than being rejected by pydantic first (422).
        resp = client.post(
            "/admin/settlements",
            headers=_auth(_admin_token()),
            json={"seller_id": "G" * 32, "amount": 10.0},
        )
        assert resp.status_code == 404

    def test_amount_must_be_positive(self, client: TestClient, sent_emails, store):
        _register_verified_seller(client, sent_emails)
        seller_id = _seller_id(store, "seller@example.com")

        resp = client.post(
            "/admin/settlements",
            headers=_auth(_admin_token()),
            json={"seller_id": seller_id, "amount": 0},
        )
        assert resp.status_code == 422

    def test_requires_admin_auth(self, client: TestClient, sent_emails, store):
        seller_token = _register_verified_seller(client, sent_emails)
        seller_id = _seller_id(store, "seller@example.com")

        no_auth = client.post(
            "/admin/settlements", json={"seller_id": seller_id, "amount": 10.0}
        )
        assert no_auth.status_code == 401

        seller_auth = client.post(
            "/admin/settlements",
            headers=_auth(seller_token),
            json={"seller_id": seller_id, "amount": 10.0},
        )
        assert seller_auth.status_code == 403


class TestListSettlements:
    def test_empty_with_none_recorded(self, client: TestClient):
        resp = client.get("/admin/settlements", headers=_auth(_admin_token()))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_across_every_seller_newest_first(
        self, client: TestClient, sent_emails, store
    ):
        _register_verified_seller(client, sent_emails, email="a@example.com")
        _register_verified_seller(client, sent_emails, email="b@example.com")
        seller_a = _seller_id(store, "a@example.com")
        seller_b = _seller_id(store, "b@example.com")
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_a,
                gross_amount=100.0,
                commission_amount=10.0,
                seller_payable=90.0,
            )
        )
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_b,
                gross_amount=200.0,
                commission_amount=20.0,
                seller_payable=180.0,
            )
        )

        first = client.post(
            "/admin/settlements",
            headers=_auth(_admin_token()),
            json={"seller_id": seller_a, "amount": 50.0},
        ).json()
        second = client.post(
            "/admin/settlements",
            headers=_auth(_admin_token()),
            json={"seller_id": seller_b, "amount": 100.0},
        ).json()

        resp = client.get("/admin/settlements", headers=_auth(_admin_token()))
        assert resp.status_code == 200
        body = resp.json()
        assert [item["id"] for item in body] == [second["id"], first["id"]]
        assert {item["seller_id"] for item in body} == {seller_a, seller_b}

    def test_requires_admin_auth(self, client: TestClient, sent_emails):
        seller_token = _register_verified_seller(client, sent_emails)

        assert client.get("/admin/settlements").status_code == 401
        assert (
            client.get("/admin/settlements", headers=_auth(seller_token)).status_code
            == 403
        )


class TestCompleteSettlement:
    def test_transitions_pending_to_completed(
        self, client: TestClient, sent_emails, store
    ):
        _register_verified_seller(client, sent_emails)
        seller_id = _seller_id(store, "seller@example.com")
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_id,
                gross_amount=500.0,
                commission_amount=50.0,
                seller_payable=450.0,
            )
        )
        created = client.post(
            "/admin/settlements",
            headers=_auth(_admin_token()),
            json={"seller_id": seller_id, "amount": 200.0},
        ).json()

        resp = client.post(
            f"/admin/settlements/{created['id']}/complete",
            headers=_auth(_admin_token()),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == created["id"]
        assert body["status"] == "completed"
        assert body["completed_at"] is not None

    def test_idempotent_when_already_completed(
        self, client: TestClient, sent_emails, store
    ):
        _register_verified_seller(client, sent_emails)
        seller_id = _seller_id(store, "seller@example.com")
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_id,
                gross_amount=500.0,
                commission_amount=50.0,
                seller_payable=450.0,
            )
        )
        created = client.post(
            "/admin/settlements",
            headers=_auth(_admin_token()),
            json={"seller_id": seller_id, "amount": 200.0},
        ).json()
        first_complete = client.post(
            f"/admin/settlements/{created['id']}/complete",
            headers=_auth(_admin_token()),
        ).json()

        second_complete = client.post(
            f"/admin/settlements/{created['id']}/complete",
            headers=_auth(_admin_token()),
        )

        assert second_complete.status_code == 200
        assert second_complete.json() == first_complete

    def test_404_for_nonexistent_settlement(self, client: TestClient):
        resp = client.post(
            f"/admin/settlements/{'A' * 32}/complete",
            headers=_auth(_admin_token()),
        )
        assert resp.status_code == 404

    def test_404_for_malformed_settlement_id(self, client: TestClient):
        resp = client.post(
            "/admin/settlements/not-a-hex-id/complete",
            headers=_auth(_admin_token()),
        )
        assert resp.status_code == 404

    def test_requires_admin_auth(self, client: TestClient, sent_emails, store):
        seller_token = _register_verified_seller(client, sent_emails)
        seller_id = _seller_id(store, "seller@example.com")
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_id,
                gross_amount=100.0,
                commission_amount=10.0,
                seller_payable=90.0,
            )
        )
        created = client.post(
            "/admin/settlements",
            headers=_auth(_admin_token()),
            json={"seller_id": seller_id, "amount": 50.0},
        ).json()

        no_auth = client.post(f"/admin/settlements/{created['id']}/complete")
        assert no_auth.status_code == 401

        seller_auth = client.post(
            f"/admin/settlements/{created['id']}/complete",
            headers=_auth(seller_token),
        )
        assert seller_auth.status_code == 403


class TestAdminReports:
    def test_all_zero_with_no_sales(self, client: TestClient):
        resp = client.get("/admin/reports", headers=_auth(_admin_token()))
        assert resp.status_code == 200
        assert resp.json() == {
            "total_sales": 0,
            "gross_amount_total": 0.0,
            "commission_total": 0.0,
            "seller_payable_total": 0.0,
            "settled_total": 0.0,
            "unsettled_total": 0.0,
        }

    def test_aggregates_across_every_seller(
        self, client: TestClient, sent_emails, store
    ):
        _register_verified_seller(client, sent_emails, email="a@example.com")
        _register_verified_seller(client, sent_emails, email="b@example.com")
        seller_a = _seller_id(store, "a@example.com")
        seller_b = _seller_id(store, "b@example.com")
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_a,
                gross_amount=100.0,
                commission_amount=10.0,
                seller_payable=90.0,
            )
        )
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_b,
                gross_amount=200.0,
                commission_amount=20.0,
                seller_payable=180.0,
            )
        )
        store.settlements.append(
            SettlementRow(seller_id_hex=seller_a, amount=50.0, status="completed")
        )
        store.settlements.append(
            SettlementRow(seller_id_hex=seller_b, amount=999.0, status="pending")
        )

        resp = client.get("/admin/reports", headers=_auth(_admin_token()))

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_sales"] == 2
        assert body["gross_amount_total"] == 300.0
        assert body["commission_total"] == 30.0
        assert body["seller_payable_total"] == 270.0
        # Only the 'completed' settlement counts toward settled_total —
        # the 'pending' one is excluded.
        assert body["settled_total"] == 50.0
        assert body["unsettled_total"] == 220.0

    def test_requires_admin_auth(self, client: TestClient, sent_emails):
        seller_token = _register_verified_seller(client, sent_emails)

        assert client.get("/admin/reports").status_code == 401
        assert (
            client.get("/admin/reports", headers=_auth(seller_token)).status_code
            == 403
        )


class TestAdminReportsBySeller:
    def test_empty_with_no_sales(self, client: TestClient):
        resp = client.get("/admin/reports/by-seller", headers=_auth(_admin_token()))
        assert resp.status_code == 200
        assert resp.json() == []

    def test_only_sellers_with_sales_appear(
        self, client: TestClient, sent_emails, store
    ):
        _register_verified_seller(client, sent_emails, email="a@example.com")
        _register_verified_seller(client, sent_emails, email="b@example.com")
        seller_a = _seller_id(store, "a@example.com")
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_a,
                gross_amount=100.0,
                commission_amount=10.0,
                seller_payable=90.0,
            )
        )

        resp = client.get("/admin/reports/by-seller", headers=_auth(_admin_token()))

        body = resp.json()
        assert len(body) == 1
        assert body[0]["seller_id"] == seller_a

    def test_sums_back_to_platform_totals_and_sorts_by_unsettled_desc(
        self, client: TestClient, sent_emails, store
    ):
        _register_verified_seller(client, sent_emails, email="a@example.com")
        _register_verified_seller(client, sent_emails, email="b@example.com")
        seller_a = _seller_id(store, "a@example.com")
        seller_b = _seller_id(store, "b@example.com")
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_a,
                gross_amount=100.0,
                commission_amount=10.0,
                seller_payable=90.0,
            )
        )
        store.sales.append(
            SalesRow(
                seller_id_hex=seller_b,
                gross_amount=200.0,
                commission_amount=20.0,
                seller_payable=180.0,
            )
        )
        # Seller A is almost fully settled; seller B has nothing
        # settled yet, so B should be owed more and sort first.
        store.settlements.append(
            SettlementRow(seller_id_hex=seller_a, amount=80.0, status="completed")
        )

        by_seller_resp = client.get(
            "/admin/reports/by-seller", headers=_auth(_admin_token())
        )
        platform_resp = client.get("/admin/reports", headers=_auth(_admin_token()))

        by_seller = by_seller_resp.json()
        platform = platform_resp.json()

        assert [item["seller_id"] for item in by_seller] == [seller_b, seller_a]
        assert sum(item["total_sales"] for item in by_seller) == platform["total_sales"]
        assert sum(item["gross_amount_total"] for item in by_seller) == platform[
            "gross_amount_total"
        ]
        assert sum(item["seller_payable_total"] for item in by_seller) == platform[
            "seller_payable_total"
        ]
        assert sum(item["settled_total"] for item in by_seller) == platform["settled_total"]

        seller_a_item = next(item for item in by_seller if item["seller_id"] == seller_a)
        seller_b_item = next(item for item in by_seller if item["seller_id"] == seller_b)
        assert seller_a_item["settled_total"] == 80.0
        assert seller_a_item["unsettled_total"] == 10.0
        assert seller_b_item["settled_total"] == 0.0
        assert seller_b_item["unsettled_total"] == 180.0

    def test_requires_admin_auth(self, client: TestClient, sent_emails):
        seller_token = _register_verified_seller(client, sent_emails)

        assert client.get("/admin/reports/by-seller").status_code == 401
        assert (
            client.get(
                "/admin/reports/by-seller", headers=_auth(seller_token)
            ).status_code
            == 403
        )
