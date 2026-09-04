"""
Task 76: automated tests for admin auth + catalog — the fourth item
in Phase 7's schedule (see PROJECT_ROADMAP.md). Extends Task 73's
`fake_oracle.py` support for the singleton `admin_settings` row with
its write side, and reuses the `_admin_token()`/`_auth()` helper
pattern already established in `test_products.py`/
`test_seller_earnings_and_payment_methods.py` for the
`get_current_admin` auth guard.

Covers, against the real endpoint code with only the DB layer faked
(see conftest.py / fake_oracle.py):

- POST /admin/login: issues a token for the correct ADMIN_EMAIL/
  ADMIN_PASSWORD_HASH pair (env-var-provisioned, not a DB row — see
  that endpoint's docstring); the same generic 401 for a wrong
  password, a wrong email, and ADMIN_EMAIL/ADMIN_PASSWORD_HASH not
  being configured at all (anti-enumeration, matches POST
  /sellers/login's behavior); Task 44's per-IP rate limit still
  applies, its own independent "admin_login" counter.
- GET /admin/products: admin-only (401 with no token, 403 with a
  seller token); lists every seller's products, newest-first,
  including seller_id and drive_link (which no buyer-facing products
  endpoint returns); empty list when no products exist.
- GET /admin/settings: admin-only; returns the singleton row including
  commission_rate (defaulting to the schema's 10.00 before any admin
  has changed it); degrades to an all-null/0 response rather than 500
  if the row is ever missing, mirroring GET /payment-info's fallback.
- PUT /admin/settings: admin-only; the four payment fields and
  commission_rate are each independent and optional ("omit = leave
  unchanged", matching PUT /sellers/payment-methods' convention); an
  empty string clears a payment field; commission_rate is bounded to
  [0, 100] by the request model and, unlike the payment fields, can
  never be cleared (the column is NOT NULL); returns the full updated
  row.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


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


def _create_product(
    client: TestClient,
    token: str,
    *,
    name: str = "Ethiopian Coffee Guide",
    price: float = 199.99,
    description: str = "A short ebook.",
    drive_link: str = "https://drive.google.com/file/d/abc123",
):
    return client.post(
        "/products",
        headers=_auth(token),
        json={
            "name": name,
            "price": price,
            "description": description,
            "drive_link": drive_link,
        },
    )


class TestAdminLogin:
    def test_login_succeeds_with_correct_credentials(
        self, client: TestClient, monkeypatch
    ):
        from app.security import hash_password

        monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
        monkeypatch.setenv("ADMIN_PASSWORD_HASH", hash_password("super-secret-1"))

        resp = client.post(
            "/admin/login",
            json={"email": "admin@example.com", "password": "super-secret-1"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert isinstance(body["access_token"], str) and body["access_token"]

    def test_login_is_case_insensitive_on_email(
        self, client: TestClient, monkeypatch
    ):
        from app.security import hash_password

        monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
        monkeypatch.setenv("ADMIN_PASSWORD_HASH", hash_password("super-secret-1"))

        resp = client.post(
            "/admin/login",
            json={"email": "ADMIN@EXAMPLE.COM", "password": "super-secret-1"},
        )

        assert resp.status_code == 200

    def test_login_rejects_wrong_password(self, client: TestClient, monkeypatch):
        from app.security import hash_password

        monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
        monkeypatch.setenv("ADMIN_PASSWORD_HASH", hash_password("super-secret-1"))

        resp = client.post(
            "/admin/login",
            json={"email": "admin@example.com", "password": "totally-wrong"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid email or password"

    def test_login_rejects_wrong_email(self, client: TestClient, monkeypatch):
        from app.security import hash_password

        monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
        monkeypatch.setenv("ADMIN_PASSWORD_HASH", hash_password("super-secret-1"))

        resp = client.post(
            "/admin/login",
            json={"email": "nobody@example.com", "password": "super-secret-1"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid email or password"

    def test_login_fails_with_same_generic_error_when_unconfigured(
        self, client: TestClient, monkeypatch
    ):
        """No ADMIN_EMAIL/ADMIN_PASSWORD_HASH set at all — must not 500,
        and must return the same generic message a wrong password
        would, so a caller can't distinguish "not provisioned yet" from
        "wrong password" (see the endpoint's own docstring)."""
        monkeypatch.delenv("ADMIN_EMAIL", raising=False)
        monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)

        resp = client.post(
            "/admin/login",
            json={"email": "admin@example.com", "password": "whatever12"},
        )

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid email or password"

    def test_login_rate_limit_still_applies(self, client: TestClient, monkeypatch):
        """Task 44's per-IP throttle — five failed attempts, the sixth
        is 429 regardless of what the failure reason would have been.
        Uses its own 'admin_login' counter, independent of
        'seller_login' (see the endpoint's docstring)."""
        from app.security import hash_password

        monkeypatch.setenv("ADMIN_EMAIL", "admin@example.com")
        monkeypatch.setenv("ADMIN_PASSWORD_HASH", hash_password("super-secret-1"))

        for _ in range(5):
            resp = client.post(
                "/admin/login",
                json={"email": "admin@example.com", "password": "wrong"},
            )
            assert resp.status_code == 401

        resp = client.post(
            "/admin/login",
            json={"email": "admin@example.com", "password": "wrong"},
        )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers


class TestAdminProducts:
    def test_lists_every_sellers_products_newest_first(
        self, client: TestClient, sent_emails
    ):
        seller_a_token = _register_verified_seller(
            client, sent_emails, email="a@example.com"
        )
        seller_b_token = _register_verified_seller(
            client, sent_emails, email="b@example.com"
        )
        _create_product(client, seller_a_token, name="A's product")
        _create_product(client, seller_b_token, name="B's product")

        resp = client.get("/admin/products", headers=_auth(_admin_token()))

        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert names == ["B's product", "A's product"]

    def test_includes_seller_id_and_drive_link(
        self, client: TestClient, sent_emails, store
    ):
        token = _register_verified_seller(client, sent_emails)
        _create_product(client, token)

        resp = client.get("/admin/products", headers=_auth(_admin_token()))

        item = resp.json()[0]
        assert set(item.keys()) == {
            "id",
            "seller_id",
            "name",
            "price",
            "description",
            "thumbnail_ref",
            "drive_link",
        }
        assert item["seller_id"] in {row.id_hex for row in store.sellers.values()}
        assert item["drive_link"] == "https://drive.google.com/file/d/abc123"

    def test_empty_when_no_products_exist(self, client: TestClient):
        resp = client.get("/admin/products", headers=_auth(_admin_token()))

        assert resp.status_code == 200
        assert resp.json() == []

    def test_requires_authentication(self, client: TestClient):
        resp = client.get("/admin/products")
        assert resp.status_code == 401

    def test_rejects_seller_token(self, client: TestClient, sent_emails):
        token = _register_verified_seller(client, sent_emails)

        resp = client.get("/admin/products", headers=_auth(token))

        assert resp.status_code == 403


class TestGetAdminSettings:
    def test_defaults_to_all_null_payment_info_and_10_percent_commission(
        self, client: TestClient
    ):
        resp = client.get("/admin/settings", headers=_auth(_admin_token()))

        assert resp.status_code == 200
        assert resp.json() == {
            "cbe_account_name": None,
            "cbe_account_number": None,
            "telebirr_account_name": None,
            "telebirr_account_number": None,
            "commission_rate": 10.0,
        }

    def test_degrades_when_row_is_missing(self, client: TestClient, store):
        store.admin_settings = None

        resp = client.get("/admin/settings", headers=_auth(_admin_token()))

        assert resp.status_code == 200
        body = resp.json()
        assert body["commission_rate"] == 0
        assert body["cbe_account_name"] is None

    def test_requires_authentication(self, client: TestClient):
        resp = client.get("/admin/settings")
        assert resp.status_code == 401

    def test_rejects_seller_token(self, client: TestClient, sent_emails):
        token = _register_verified_seller(client, sent_emails)

        resp = client.get("/admin/settings", headers=_auth(token))

        assert resp.status_code == 403


class TestUpdateAdminSettings:
    def test_updates_only_provided_fields(self, client: TestClient):
        admin = _auth(_admin_token())

        first = client.put(
            "/admin/settings",
            headers=admin,
            json={"cbe_account_name": "NATRA Ltd", "cbe_account_number": "1000200030"},
        )
        assert first.status_code == 200
        assert first.json()["cbe_account_name"] == "NATRA Ltd"
        assert first.json()["cbe_account_number"] == "1000200030"
        assert first.json()["telebirr_account_name"] is None

        second = client.put(
            "/admin/settings",
            headers=admin,
            json={"telebirr_account_name": "NATRA Ltd"},
        )
        assert second.status_code == 200
        body = second.json()
        # Fields from the first call are left unchanged by the second.
        assert body["cbe_account_name"] == "NATRA Ltd"
        assert body["cbe_account_number"] == "1000200030"
        assert body["telebirr_account_name"] == "NATRA Ltd"

    def test_empty_string_clears_a_field(self, client: TestClient):
        admin = _auth(_admin_token())
        client.put(
            "/admin/settings", headers=admin, json={"cbe_account_name": "NATRA Ltd"}
        )

        resp = client.put(
            "/admin/settings", headers=admin, json={"cbe_account_name": ""}
        )

        assert resp.status_code == 200
        assert resp.json()["cbe_account_name"] == ""

    def test_updates_commission_rate(self, client: TestClient):
        resp = client.put(
            "/admin/settings",
            headers=_auth(_admin_token()),
            json={"commission_rate": 15},
        )

        assert resp.status_code == 200
        assert resp.json()["commission_rate"] == 15

    def test_commission_rate_omitted_leaves_it_unchanged(self, client: TestClient):
        admin = _auth(_admin_token())
        client.put("/admin/settings", headers=admin, json={"commission_rate": 15})

        resp = client.put(
            "/admin/settings", headers=admin, json={"cbe_account_name": "NATRA Ltd"}
        )

        assert resp.status_code == 200
        assert resp.json()["commission_rate"] == 15

    def test_rejects_commission_rate_above_100(self, client: TestClient):
        resp = client.put(
            "/admin/settings",
            headers=_auth(_admin_token()),
            json={"commission_rate": 101},
        )
        assert resp.status_code == 422

    def test_rejects_negative_commission_rate(self, client: TestClient):
        resp = client.put(
            "/admin/settings",
            headers=_auth(_admin_token()),
            json={"commission_rate": -1},
        )
        assert resp.status_code == 422

    def test_no_fields_provided_returns_current_settings_unchanged(
        self, client: TestClient
    ):
        admin = _auth(_admin_token())
        client.put("/admin/settings", headers=admin, json={"commission_rate": 15})

        resp = client.put("/admin/settings", headers=admin, json={})

        assert resp.status_code == 200
        assert resp.json()["commission_rate"] == 15

    def test_requires_authentication(self, client: TestClient):
        resp = client.put("/admin/settings", json={"commission_rate": 15})
        assert resp.status_code == 401

    def test_rejects_seller_token(self, client: TestClient, sent_emails):
        token = _register_verified_seller(client, sent_emails)

        resp = client.put(
            "/admin/settings", headers=_auth(token), json={"commission_rate": 15}
        )

        assert resp.status_code == 403
