"""
Task 73: automated tests for the Products endpoints — the first item
in Phase 7's schedule (see PROJECT_ROADMAP.md). Extends Task 72's
pytest + `fake_oracle.py` pattern with a `products` table and the
singleton `admin_settings` row (see that file's docstring).

Covers, against the real endpoint code with only the DB layer faked
(see conftest.py / fake_oracle.py):

- POST /products: creates a product owned by the authenticated seller,
  requires a seller token (401 with none, 403 with an admin token),
  validates `drive_link` is a URL, rejects a non-positive price and an
  empty name (Pydantic field validation), defaults `description` to
  ""  when omitted.
- GET /products/mine: seller isolation (never returns another
  seller's products), newest-first ordering, same auth/role guard as
  POST /products.
- GET /products: public, no auth, lists every seller's products,
  newest-first, and deliberately excludes seller_id/description/
  drive_link — the digital delivery link and description belong to
  GET /products/{id}, seller_id is never buyer-facing.
- GET /products/{id}: public, no auth, includes description but still
  never seller_id/drive_link; 404 for both a well-formed-but-unknown
  id and a malformed one (never reaches HEXTORAW with bad input).
- GET /payment-info: public, no auth, returns NATRA's own CBE/Telebirr
  account info (all-null until an admin configures it — Task 16), and
  degrades to all-null rather than 500 if the singleton row is ever
  missing.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _admin_token() -> str:
    # Deferred import, same reasoning as conftest.py's fixtures: `app.*`
    # is only importable once conftest.py has put `backend/` on sys.path,
    # which happens at conftest collection time, not necessarily before
    # this module's top-level code would otherwise run.
    from app.auth import create_admin_access_token

    return create_admin_access_token("admin@example.com")


def _register_verified_seller(
    client: TestClient,
    sent_emails: dict[str, list[tuple[str, str]]],
    email: str = "seller@example.com",
    password: str = "correct-horse-1",
) -> str:
    """Registers, verifies, and logs in a seller, the same real flow a
    seller goes through (Task 68/71) — this suite doesn't shortcut
    around it, since POST /products' auth guard is exactly what's
    under test for the 401/403 cases below. Returns the bearer token."""
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


class TestCreateProduct:
    def test_create_product_succeeds(self, client: TestClient, sent_emails, store):
        token = _register_verified_seller(client, sent_emails)

        resp = _create_product(client, token)

        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Ethiopian Coffee Guide"
        assert body["price"] == 199.99
        assert body["description"] == "A short ebook."
        assert body["drive_link"] == "https://drive.google.com/file/d/abc123"
        assert len(body["id"]) == 32
        assert body["seller_id"] in {row.id_hex for row in store.sellers.values()}

    def test_create_product_defaults_description_to_empty_string(
        self, client: TestClient, sent_emails
    ):
        token = _register_verified_seller(client, sent_emails)

        resp = client.post(
            "/products",
            headers=_auth(token),
            json={
                "name": "No description",
                "price": 10,
                "drive_link": "https://drive.google.com/file/d/xyz",
            },
        )

        assert resp.status_code == 201
        assert resp.json()["description"] == ""

    def test_create_product_requires_authentication(self, client: TestClient):
        resp = client.post(
            "/products",
            json={
                "name": "No token",
                "price": 10,
                "drive_link": "https://drive.google.com/file/d/xyz",
            },
        )
        assert resp.status_code == 401

    def test_create_product_rejects_admin_token(self, client: TestClient):
        """Task 41's role check — an admin token must not act as a seller."""
        admin_token = _admin_token()

        resp = _create_product(client, admin_token)

        assert resp.status_code == 403

    def test_create_product_rejects_non_positive_price(
        self, client: TestClient, sent_emails
    ):
        token = _register_verified_seller(client, sent_emails)

        resp = _create_product(client, token, price=0)

        assert resp.status_code == 422

    def test_create_product_rejects_empty_name(self, client: TestClient, sent_emails):
        token = _register_verified_seller(client, sent_emails)

        resp = _create_product(client, token, name="")

        assert resp.status_code == 422

    def test_create_product_rejects_non_url_drive_link(
        self, client: TestClient, sent_emails
    ):
        token = _register_verified_seller(client, sent_emails)

        resp = _create_product(client, token, drive_link="not-a-url")

        assert resp.status_code == 422
        assert "url" in resp.json()["detail"].lower()


class TestListMyProducts:
    def test_returns_only_own_products(self, client: TestClient, sent_emails):
        seller_a_token = _register_verified_seller(
            client, sent_emails, email="a@example.com"
        )
        seller_b_token = _register_verified_seller(
            client, sent_emails, email="b@example.com"
        )
        _create_product(client, seller_a_token, name="A's product")
        _create_product(client, seller_b_token, name="B's product")

        resp = client.get("/products/mine", headers=_auth(seller_a_token))

        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert names == ["A's product"]

    def test_newest_product_first(self, client: TestClient, sent_emails):
        token = _register_verified_seller(client, sent_emails)
        _create_product(client, token, name="First")
        _create_product(client, token, name="Second")

        resp = client.get("/products/mine", headers=_auth(token))

        names = [p["name"] for p in resp.json()]
        assert names == ["Second", "First"]

    def test_empty_when_seller_has_no_products(self, client: TestClient, sent_emails):
        token = _register_verified_seller(client, sent_emails)

        resp = client.get("/products/mine", headers=_auth(token))

        assert resp.status_code == 200
        assert resp.json() == []

    def test_requires_authentication(self, client: TestClient):
        resp = client.get("/products/mine")
        assert resp.status_code == 401

    def test_rejects_admin_token(self, client: TestClient):
        admin_token = _admin_token()
        resp = client.get("/products/mine", headers=_auth(admin_token))
        assert resp.status_code == 403


class TestPublicProductGrid:
    def test_lists_products_from_every_seller(self, client: TestClient, sent_emails):
        seller_a_token = _register_verified_seller(
            client, sent_emails, email="a@example.com"
        )
        seller_b_token = _register_verified_seller(
            client, sent_emails, email="b@example.com"
        )
        _create_product(client, seller_a_token, name="A's product")
        _create_product(client, seller_b_token, name="B's product")

        resp = client.get("/products")

        assert resp.status_code == 200
        names = {p["name"] for p in resp.json()}
        assert names == {"A's product", "B's product"}

    def test_omits_seller_id_description_and_drive_link(
        self, client: TestClient, sent_emails
    ):
        token = _register_verified_seller(client, sent_emails)
        _create_product(client, token)

        resp = client.get("/products")

        item = resp.json()[0]
        assert set(item.keys()) == {"id", "name", "price", "thumbnail_ref"}

    def test_newest_product_first(self, client: TestClient, sent_emails):
        token = _register_verified_seller(client, sent_emails)
        _create_product(client, token, name="First")
        _create_product(client, token, name="Second")

        resp = client.get("/products")

        names = [p["name"] for p in resp.json()]
        assert names == ["Second", "First"]

    def test_no_authentication_required(self, client: TestClient):
        resp = client.get("/products")
        assert resp.status_code == 200

    def test_empty_when_no_products_exist(self, client: TestClient):
        resp = client.get("/products")
        assert resp.status_code == 200
        assert resp.json() == []


class TestProductDetail:
    def test_returns_full_buyer_visible_fields(self, client: TestClient, sent_emails):
        token = _register_verified_seller(client, sent_emails)
        create_resp = _create_product(client, token)
        product_id = create_resp.json()["id"]

        resp = client.get(f"/products/{product_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"id", "name", "price", "description", "thumbnail_ref"}
        assert body["description"] == "A short ebook."

    def test_no_authentication_required(self, client: TestClient, sent_emails):
        token = _register_verified_seller(client, sent_emails)
        create_resp = _create_product(client, token)
        product_id = create_resp.json()["id"]

        resp = client.get(f"/products/{product_id}")

        assert resp.status_code == 200

    def test_unknown_but_well_formed_id_is_404(self, client: TestClient):
        resp = client.get("/products/" + "0" * 32)
        assert resp.status_code == 404

    def test_malformed_id_is_404_not_500(self, client: TestClient):
        """A malformed id must never reach HEXTORAW (which would raise an
        Oracle error) — the endpoint checks the shape first."""
        resp = client.get("/products/not-a-valid-id")
        assert resp.status_code == 404


class TestPaymentInfo:
    def test_defaults_to_all_null_when_unconfigured(self, client: TestClient):
        """Matches init_db.py's seeded row before any admin has called
        PUT /admin/settings (Task 16, not yet built as of this task)."""
        resp = client.get("/payment-info")

        assert resp.status_code == 200
        assert resp.json() == {
            "cbe_account_name": None,
            "cbe_account_number": None,
            "telebirr_account_name": None,
            "telebirr_account_number": None,
        }

    def test_no_authentication_required(self, client: TestClient):
        resp = client.get("/payment-info")
        assert resp.status_code == 200

    def test_degrades_to_all_null_when_row_is_missing(
        self, client: TestClient, store
    ):
        """Shouldn't happen in practice — init_db.py always seeds this
        row — but the endpoint is written to degrade rather than 500 if
        it's ever missing; exercise that branch directly."""
        store.admin_settings = None

        resp = client.get("/payment-info")

        assert resp.status_code == 200
        assert resp.json() == {
            "cbe_account_name": None,
            "cbe_account_number": None,
            "telebirr_account_name": None,
            "telebirr_account_number": None,
        }
