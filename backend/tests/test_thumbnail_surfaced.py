"""
Task 101: automated tests for `thumbnail_ref` being surfaced across the
three GET endpoints (Tasks 95-97): `GET /products`, `GET /products/{id}`,
and `GET /products/mine`. Last of Phase 8's four test-writing tasks
(98-101).

`GET /products` and `GET /products/{id}` needed zero production code
changes for Tasks 95-96 (both already selected/returned the raw
`thumbnail_ref` column from the start), so what's under test here is
purely "does the response surface this field with the right value" —
both the non-null case (a product with a thumbnail set) and the null
case (one without). `test_products.py`'s existing key-set assertions
(`test_omits_seller_id_description_and_drive_link` /
`test_returns_full_buyer_visible_fields`) already confirm
`thumbnail_ref` is present as a *key*; this file is the first to check
its *value*.

`GET /products/mine` (Task 97) already has incidental coverage from
`test_thumbnail_upload.py`'s `_thumbnail_ref_on_dashboard()` helper
(which reads it back to confirm Task 100's upload endpoint wrote to
the DB) and from Task 98's `fake_oracle.py` bug-fix note (the 5-to-6-
column query change) — per `CURRENT_STATUS.md`'s Task 101 hand-off
note, it still gets its own explicit, direct tests below, the same
"each surfaced field gets its own test" standard every other field in
this suite gets.

Setup uses `store.products[product_id].thumbnail_ref = ...` directly
rather than going through the real `POST /products/{id}/thumbnail`
endpoint — the same "arrange via direct store mutation" pattern
`test_products.py`'s `TestPaymentInfo.test_degrades_to_all_null_when_row_is_missing`
already uses (`store.admin_settings = None`). This keeps these tests
scoped to the three GET endpoints' own surfacing logic, independent of
Task 100's upload-endpoint wiring, which `test_thumbnail_upload.py`
already covers on its own.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.fake_oracle import FakeOracleStore


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
    name: str = "Ethiopian Coffee Guide",
    price: float = 199.99,
    description: str = "A short ebook.",
    drive_link: str = "https://drive.google.com/file/d/abc123",
) -> str:
    resp = client.post(
        "/products",
        headers=_auth(token),
        json={
            "name": name,
            "price": price,
            "description": description,
            "drive_link": drive_link,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _set_thumbnail_ref(store: FakeOracleStore, product_id: str, thumbnail_ref: str) -> None:
    """Directly sets the stored `thumbnail_ref` for a product, bypassing
    the real upload endpoint — see module docstring."""
    store.products[product_id].thumbnail_ref = thumbnail_ref


class TestThumbnailRefOnPublicGrid:
    """GET /products (Task 95)."""

    def test_includes_thumbnail_ref_when_set(
        self, client: TestClient, sent_emails, store: FakeOracleStore
    ):
        token = _register_verified_seller(client, sent_emails)
        product_id = _create_product(client, token)
        _set_thumbnail_ref(store, product_id, "https://objectstorage.example.com/a.jpg")

        resp = client.get("/products")

        assert resp.status_code == 200
        (item,) = resp.json()
        assert item["thumbnail_ref"] == "https://objectstorage.example.com/a.jpg"

    def test_thumbnail_ref_is_null_when_not_set(self, client: TestClient, sent_emails):
        token = _register_verified_seller(client, sent_emails)
        _create_product(client, token)

        resp = client.get("/products")

        (item,) = resp.json()
        assert item["thumbnail_ref"] is None


class TestThumbnailRefOnProductDetail:
    """GET /products/{id} (Task 96)."""

    def test_includes_thumbnail_ref_when_set(
        self, client: TestClient, sent_emails, store: FakeOracleStore
    ):
        token = _register_verified_seller(client, sent_emails)
        product_id = _create_product(client, token)
        _set_thumbnail_ref(store, product_id, "https://objectstorage.example.com/b.png")

        resp = client.get(f"/products/{product_id}")

        assert resp.status_code == 200
        assert resp.json()["thumbnail_ref"] == "https://objectstorage.example.com/b.png"

    def test_thumbnail_ref_is_null_when_not_set(self, client: TestClient, sent_emails):
        token = _register_verified_seller(client, sent_emails)
        product_id = _create_product(client, token)

        resp = client.get(f"/products/{product_id}")

        assert resp.status_code == 200
        assert resp.json()["thumbnail_ref"] is None


class TestThumbnailRefOnSellerDashboard:
    """GET /products/mine (Task 97)."""

    def test_includes_thumbnail_ref_when_set(
        self, client: TestClient, sent_emails, store: FakeOracleStore
    ):
        token = _register_verified_seller(client, sent_emails)
        product_id = _create_product(client, token)
        _set_thumbnail_ref(store, product_id, "https://objectstorage.example.com/c.webp")

        resp = client.get("/products/mine", headers=_auth(token))

        assert resp.status_code == 200
        (item,) = resp.json()
        assert item["thumbnail_ref"] == "https://objectstorage.example.com/c.webp"

    def test_thumbnail_ref_is_null_when_not_set(self, client: TestClient, sent_emails):
        token = _register_verified_seller(client, sent_emails)
        _create_product(client, token)

        resp = client.get("/products/mine", headers=_auth(token))

        assert resp.status_code == 200
        (item,) = resp.json()
        assert item["thumbnail_ref"] is None

    def test_does_not_leak_another_sellers_thumbnail_ref(
        self, client: TestClient, sent_emails, store: FakeOracleStore
    ):
        """thumbnail_ref surfacing must respect the existing seller-
        isolation guard (test_products.py's TestListMyProducts) — a
        seller's dashboard should never even see another seller's
        product row, thumbnail_ref included."""
        owner_token = _register_verified_seller(
            client, sent_emails, email="owner@example.com"
        )
        other_token = _register_verified_seller(
            client, sent_emails, email="other@example.com"
        )
        owner_product_id = _create_product(
            client, owner_token, name="Owner's product"
        )
        _set_thumbnail_ref(
            store, owner_product_id, "https://objectstorage.example.com/d.jpg"
        )

        resp = client.get("/products/mine", headers=_auth(other_token))

        assert resp.status_code == 200
        assert resp.json() == []
