"""
Task 72: automated tests for the seller email-verification flow
(Task 68) and the login gate on top of it (Task 71).

Covers, against the real endpoint code with only the DB/email layers
faked (see conftest.py):

- register -> unverified by default, duplicate email rejected
- login blocked (403) while unverified, even with the right password
- wrong password still 401 regardless of verified state (Task 71's
  ordering guarantee — verification status must never leak through
  the error returned for a bad password)
- verify-email flips the flag and unblocks login
- a wrong/already-used OTP doesn't verify
- resend-verification and password-reset/request give the same
  generic response whether or not the email exists (anti-enumeration)
- password reset changes the password without touching email_verified
- the login rate limit still applies on top of the new gate
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _register(client: TestClient, email: str = "seller@example.com", password: str = "correct-horse-1"):
    return client.post(
        "/sellers/register", json={"email": email, "password": password}
    )


class TestRegister:
    def test_register_creates_unverified_seller(self, client: TestClient, store):
        resp = _register(client)
        assert resp.status_code == 201
        assert store.sellers["seller@example.com"].email_verified == "N"

    def test_register_sends_a_signup_otp(self, client: TestClient, sent_emails):
        _register(client)
        assert len(sent_emails["signup"]) == 1
        sent_email, code = sent_emails["signup"][0]
        assert sent_email == "seller@example.com"
        assert len(code) == 6 and code.isdigit()

    def test_register_duplicate_email_is_rejected(self, client: TestClient):
        _register(client)
        resp = _register(client)
        assert resp.status_code == 409

    def test_register_normalizes_email_case(self, client: TestClient, store):
        _register(client, email="Seller@Example.com")
        assert "seller@example.com" in store.sellers


class TestLoginGate:
    """The core of Task 71: POST /sellers/login checking email_verified."""

    def test_login_blocked_before_verification(self, client: TestClient):
        _register(client, email="seller@example.com", password="correct-horse-1")

        resp = client.post(
            "/sellers/login",
            json={"email": "seller@example.com", "password": "correct-horse-1"},
        )

        assert resp.status_code == 403
        assert "verify" in resp.json()["detail"].lower()

    def test_login_succeeds_after_verification(self, client: TestClient, sent_emails):
        _register(client, email="seller@example.com", password="correct-horse-1")
        _, code = sent_emails["signup"][0]

        verify_resp = client.post(
            "/sellers/verify-email", json={"email": "seller@example.com", "otp": code}
        )
        assert verify_resp.status_code == 200
        assert verify_resp.json()["verified"] is True

        login_resp = client.post(
            "/sellers/login",
            json={"email": "seller@example.com", "password": "correct-horse-1"},
        )
        assert login_resp.status_code == 200
        body = login_resp.json()
        assert body["token_type"] == "bearer"
        assert isinstance(body["access_token"], str) and body["access_token"]

    def test_wrong_password_is_401_even_when_unverified(self, client: TestClient):
        _register(client, email="seller@example.com", password="correct-horse-1")

        resp = client.post(
            "/sellers/login",
            json={"email": "seller@example.com", "password": "totally-wrong"},
        )
        assert resp.status_code == 401

    def test_wrong_password_is_401_even_when_verified(self, client: TestClient, sent_emails):
        """
        Task 71's ordering guarantee: the password check runs BEFORE
        the email_verified check, so a wrong password against a
        verified account and a wrong password against an unverified
        one are indistinguishable (both 401) — verification status
        must never leak through this endpoint's error response.
        """
        _register(client, email="seller@example.com", password="correct-horse-1")
        _, code = sent_emails["signup"][0]
        client.post(
            "/sellers/verify-email", json={"email": "seller@example.com", "otp": code}
        )

        resp = client.post(
            "/sellers/login",
            json={"email": "seller@example.com", "password": "totally-wrong"},
        )
        assert resp.status_code == 401

    def test_login_unknown_email_is_401_not_403(self, client: TestClient):
        """A nonexistent account must never surface the 403 shape —
        that would let a caller distinguish "no such seller" from
        "seller exists but is unverified"."""
        resp = client.post(
            "/sellers/login",
            json={"email": "nobody@example.com", "password": "whatever12"},
        )
        assert resp.status_code == 401

    def test_login_rate_limit_still_applies(self, client: TestClient):
        """Task 44's per-IP throttle sits in front of the new gate,
        same as it always did — five failed attempts, the sixth is
        429 regardless of what the failure reason would have been."""
        _register(client, email="seller@example.com", password="correct-horse-1")

        for _ in range(5):
            resp = client.post(
                "/sellers/login",
                json={"email": "seller@example.com", "password": "wrong"},
            )
            assert resp.status_code == 401

        resp = client.post(
            "/sellers/login",
            json={"email": "seller@example.com", "password": "wrong"},
        )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers


class TestVerifyEmail:
    def test_wrong_otp_does_not_verify(self, client: TestClient, store):
        _register(client, email="seller@example.com")

        resp = client.post(
            "/sellers/verify-email",
            json={"email": "seller@example.com", "otp": "000000"},
        )

        assert resp.status_code == 400
        assert store.sellers["seller@example.com"].email_verified == "N"

    def test_otp_cannot_be_reused(self, client: TestClient, sent_emails):
        _register(client, email="seller@example.com")
        _, code = sent_emails["signup"][0]

        first = client.post(
            "/sellers/verify-email", json={"email": "seller@example.com", "otp": code}
        )
        assert first.status_code == 200

        second = client.post(
            "/sellers/verify-email", json={"email": "seller@example.com", "otp": code}
        )
        assert second.status_code == 400

    def test_resend_gives_same_generic_message_for_any_email(self, client: TestClient):
        """Anti-enumeration: registered-unverified, registered-verified,
        and never-registered all get byte-identical responses."""
        _register(client, email="registered@example.com")

        resp_registered = client.post(
            "/sellers/verify-email/resend", json={"email": "registered@example.com"}
        )
        resp_unknown = client.post(
            "/sellers/verify-email/resend", json={"email": "nobody@example.com"}
        )

        assert resp_registered.status_code == resp_unknown.status_code == 200
        assert resp_registered.json() == resp_unknown.json()

    def test_resend_issues_a_new_code_that_verifies(self, client: TestClient, sent_emails):
        _register(client, email="seller@example.com")
        sent_emails["signup"].clear()  # discard the register-time code

        client.post("/sellers/verify-email/resend", json={"email": "seller@example.com"})
        assert len(sent_emails["signup"]) == 1
        _, new_code = sent_emails["signup"][0]

        resp = client.post(
            "/sellers/verify-email", json={"email": "seller@example.com", "otp": new_code}
        )
        assert resp.status_code == 200


class TestPasswordReset:
    def test_request_gives_same_generic_message_for_any_email(self, client: TestClient):
        _register(client, email="registered@example.com")

        resp_registered = client.post(
            "/sellers/password-reset/request", json={"email": "registered@example.com"}
        )
        resp_unknown = client.post(
            "/sellers/password-reset/request", json={"email": "nobody@example.com"}
        )

        assert resp_registered.status_code == resp_unknown.status_code == 200
        assert resp_registered.json() == resp_unknown.json()

    def test_confirm_changes_password_and_new_password_logs_in(
        self, client: TestClient, sent_emails
    ):
        _register(client, email="seller@example.com", password="old-password-1")
        # Verify first, same as a real seller would before ever logging in.
        _, signup_code = sent_emails["signup"][0]
        client.post(
            "/sellers/verify-email",
            json={"email": "seller@example.com", "otp": signup_code},
        )

        client.post(
            "/sellers/password-reset/request", json={"email": "seller@example.com"}
        )
        _, reset_code = sent_emails["reset"][0]

        confirm_resp = client.post(
            "/sellers/password-reset/confirm",
            json={
                "email": "seller@example.com",
                "otp": reset_code,
                "new_password": "new-password-2",
            },
        )
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["reset"] is True

        old_login = client.post(
            "/sellers/login",
            json={"email": "seller@example.com", "password": "old-password-1"},
        )
        assert old_login.status_code == 401

        new_login = client.post(
            "/sellers/login",
            json={"email": "seller@example.com", "password": "new-password-2"},
        )
        assert new_login.status_code == 200

    def test_reset_does_not_change_email_verified(self, client: TestClient, store, sent_emails):
        """A password reset alone must not silently mark an
        unverified seller as verified — that would be a second way to
        bypass Task 71's gate."""
        _register(client, email="seller@example.com", password="old-password-1")

        client.post(
            "/sellers/password-reset/request", json={"email": "seller@example.com"}
        )
        _, reset_code = sent_emails["reset"][0]
        client.post(
            "/sellers/password-reset/confirm",
            json={
                "email": "seller@example.com",
                "otp": reset_code,
                "new_password": "new-password-2",
            },
        )

        assert store.sellers["seller@example.com"].email_verified == "N"

        resp = client.post(
            "/sellers/login",
            json={"email": "seller@example.com", "password": "new-password-2"},
        )
        assert resp.status_code == 403
