"""
Task 100: automated tests for `POST /products/{product_id}/thumbnail`
(Task 94) — the third of Phase 8's four test-writing tasks (98-101).
Task 101 (the three surfaced GET endpoints) is the remaining one, not
yet started.

Unlike Tasks 98-99, this endpoint is a real FastAPI route, so these
tests go through a real `TestClient` call (`conftest.py`'s `client`/
`store`/`sent_emails` fixtures) the same way `test_products.py` and
`test_receipts.py` already do for seller-authenticated product
endpoints — `_register_verified_seller()`/`_admin_token()`/`_auth()`/
`_create_product()` below are local copies of those same helpers,
matching the project's existing convention (see e.g. `test_receipts.py`'s
own copy) of each test file keeping its own small copy rather than
importing across test files.

What's under test here is endpoint wiring only — auth, ownership,
request/response shape, and the two error-status mappings — not
`upload_thumbnail()`'s own internals (content-type/extension/size
rules, object naming, the Object Storage call itself), which
Task 99's `test_thumbnail.py` already covers directly. So rather than
reusing `fake_oci.py`'s OCI-level fake here, these tests monkeypatch
`app.main`'s own imported `upload_thumbnail` reference directly — the
same "monkeypatch the thing `main.py` looks up at call time" approach
`conftest.py` already uses for `send_signup_otp_email`/
`send_password_reset_otp_email`, and `test_health_and_startup.py` uses
for `check_object_storage`/`check_browser`. `main.py`'s
`from .thumbnail import ... upload_thumbnail` makes `main.upload_thumbnail`
a valid patch target — no OCI_* env vars or fake OCI client needed.

Covers:
- 401 with no token, 403 with an admin token (same auth/role guard as
  every other seller product endpoint).
- 404 for a malformed product id and for a well-formed-but-unknown one
  (mirrors `test_products.py`'s `GET /products/{id}` guard).
- 403 when the authenticated seller doesn't own the product, and
  confirms `upload_thumbnail()` is never even called in that case.
- Happy path: 200, the response body's `thumbnail_ref` matches what
  `upload_thumbnail()` returned, the exact `(file_bytes, filename,
  content_type)` the client uploaded reached `upload_thumbnail()`
  unchanged, and the DB row was actually updated (checked via
  `GET /products/mine`, since Task 97 already surfaces the column
  there).
- `ThumbnailValidationError` -> 400 with the exception's message as
  `detail`, and the DB is NOT updated.
- `ThumbnailUploadError` -> 502 with the exception's message as
  `detail`, and the DB is NOT updated.
"""

from __future__ import annotations

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


def _admin_token() -> str:
    from app.auth import create_admin_access_token

    return create_admin_access_token("admin@example.com")


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


def _upload(
    client: TestClient,
    token: str,
    product_id: str,
    *,
    filename: str = "photo.jpg",
    content: bytes = b"fake-image-bytes",
    content_type: str = "image/jpeg",
):
    return client.post(
        f"/products/{product_id}/thumbnail",
        headers=_auth(token),
        files={"file": (filename, content, content_type)},
    )


def _patch_upload_thumbnail(
    monkeypatch: pytest.MonkeyPatch,
    *,
    return_value: str | None = None,
    raises: Exception | None = None,
) -> list[tuple[bytes, str, str]]:
    """
    Replaces `app.main`'s imported `upload_thumbnail` with a fake that
    either returns a fixed URL or raises a given exception, and
    records every call's `(file_bytes, filename, content_type)` args
    so a test can assert the endpoint passed through exactly what the
    client uploaded. Returns the list the fake appends to.
    """
    from app import main

    calls: list[tuple[bytes, str, str]] = []

    def _fake_upload_thumbnail(file_bytes: bytes, filename: str, content_type: str) -> str:
        calls.append((file_bytes, filename, content_type))
        if raises is not None:
            raise raises
        return return_value  # type: ignore[return-value]

    monkeypatch.setattr(main, "upload_thumbnail", _fake_upload_thumbnail)
    return calls


def _thumbnail_ref_on_dashboard(client: TestClient, token: str, product_id: str) -> str | None:
    """Reads `thumbnail_ref` back via `GET /products/mine` (Task 97) — the endpoint under test never returns the stored DB value directly, only what `upload_thumbnail()` itself returned, so a separate read is the only way to confirm the write actually happened."""
    resp = client.get("/products/mine", headers=_auth(token))
    assert resp.status_code == 200
    (product,) = [p for p in resp.json() if p["id"] == product_id]
    return product["thumbnail_ref"]


class TestUploadProductThumbnail:
    def test_happy_path_returns_the_url_and_writes_it_to_the_db(
        self, client: TestClient, sent_emails, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        token = _register_verified_seller(client, sent_emails)
        product_id = _create_product(client, token)
        calls = _patch_upload_thumbnail(
            monkeypatch, return_value="https://objectstorage.example.com/thumb.jpg"
        )

        resp = _upload(client, token, product_id)

        assert resp.status_code == 200
        assert resp.json() == {
            "thumbnail_ref": "https://objectstorage.example.com/thumb.jpg"
        }
        assert calls == [(b"fake-image-bytes", "photo.jpg", "image/jpeg")]
        assert (
            _thumbnail_ref_on_dashboard(client, token, product_id)
            == "https://objectstorage.example.com/thumb.jpg"
        )

    def test_passes_through_the_uploaded_filename_and_content_type(
        self, client: TestClient, sent_emails, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        token = _register_verified_seller(client, sent_emails)
        product_id = _create_product(client, token)
        calls = _patch_upload_thumbnail(monkeypatch, return_value="https://example.com/x.png")

        resp = _upload(
            client,
            token,
            product_id,
            filename="cover.png",
            content=b"png-bytes",
            content_type="image/png",
        )

        assert resp.status_code == 200
        assert calls == [(b"png-bytes", "cover.png", "image/png")]

    def test_requires_authentication(self, client: TestClient, sent_emails) -> None:
        token = _register_verified_seller(client, sent_emails)
        product_id = _create_product(client, token)

        resp = client.post(
            f"/products/{product_id}/thumbnail",
            files={"file": ("photo.jpg", b"bytes", "image/jpeg")},
        )

        assert resp.status_code == 401

    def test_rejects_admin_token(self, client: TestClient, sent_emails) -> None:
        """Task 41's role check — an admin token must not act as a seller, same as every other seller product endpoint."""
        token = _register_verified_seller(client, sent_emails)
        product_id = _create_product(client, token)

        resp = _upload(client, _admin_token(), product_id)

        assert resp.status_code == 403

    def test_404_for_malformed_product_id(
        self, client: TestClient, sent_emails
    ) -> None:
        token = _register_verified_seller(client, sent_emails)

        resp = _upload(client, token, "not-a-valid-hex-id")

        assert resp.status_code == 404

    def test_404_for_well_formed_but_unknown_product_id(
        self, client: TestClient, sent_emails
    ) -> None:
        token = _register_verified_seller(client, sent_emails)
        unknown_id = "AA" * 16  # well-formed RAW(16) hex, no such product

        resp = _upload(client, token, unknown_id)

        assert resp.status_code == 404

    def test_403_when_seller_does_not_own_the_product(
        self, client: TestClient, sent_emails, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        owner_token = _register_verified_seller(
            client, sent_emails, email="owner@example.com"
        )
        other_token = _register_verified_seller(
            client, sent_emails, email="other@example.com"
        )
        product_id = _create_product(client, owner_token)
        calls = _patch_upload_thumbnail(monkeypatch, return_value="https://example.com/x.jpg")

        resp = _upload(client, other_token, product_id)

        assert resp.status_code == 403
        # Ownership is checked before the file is ever read/uploaded —
        # `upload_thumbnail()` must not have been called at all.
        assert calls == []

    def test_validation_error_maps_to_400_and_does_not_write_to_db(
        self, client: TestClient, sent_emails, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.thumbnail import ThumbnailValidationError

        token = _register_verified_seller(client, sent_emails)
        product_id = _create_product(client, token)
        _patch_upload_thumbnail(
            monkeypatch, raises=ThumbnailValidationError("Thumbnail file is too large.")
        )

        resp = _upload(client, token, product_id)

        assert resp.status_code == 400
        assert resp.json()["detail"] == "Thumbnail file is too large."
        assert _thumbnail_ref_on_dashboard(client, token, product_id) is None

    def test_upload_error_maps_to_502_and_does_not_write_to_db(
        self, client: TestClient, sent_emails, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.thumbnail import ThumbnailUploadError

        token = _register_verified_seller(client, sent_emails)
        product_id = _create_product(client, token)
        _patch_upload_thumbnail(
            monkeypatch, raises=ThumbnailUploadError("OCI error: bucket not found")
        )

        resp = _upload(client, token, product_id)

        assert resp.status_code == 502
        assert resp.json()["detail"] == "OCI error: bucket not found"
        assert _thumbnail_ref_on_dashboard(client, token, product_id) is None
