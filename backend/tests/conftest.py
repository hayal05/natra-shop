"""
Task 72: shared pytest fixtures for the backend test suite.

No real Oracle DB or Brevo account is available in this environment
(or, realistically, in most CI runners), so every test in this suite
runs against `app.main`'s real FastAPI app with two things swapped
for fakes:

1. `db.get_connection` (each of `app.main`'s, `app.otp`'s, and
   `app.duplicate_check`'s own imported reference to it — added by
   Task 75) — replaced with `fake_oracle.FakeConnection`, an in-memory
   double described in that file.
2. The two Brevo-sending functions `app.main` calls directly
   (`send_signup_otp_email` / `send_password_reset_otp_email`) —
   replaced with fakes that record `(email, code)` instead of making
   a real HTTP call, via the `sent_emails` fixture. Nothing about
   `otp.py`'s own hashing/expiry/attempt-counting logic is faked —
   only the outbound network call is.

Everything else (password hashing, OTP hashing, JWT issuance/
verification, rate limiting, the endpoint logic itself) is the real
code from `app/`.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from tests.fake_oracle import FakeOracleStore, make_fake_get_connection  # noqa: E402


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Minimum env vars for the app to consider itself configured.
    `_validate_startup_config()` only runs on FastAPI's "startup"
    event (see its own docstring — deliberately not on plain import),
    which `TestClient` used as a context manager below does trigger,
    so these need to be set for every test regardless of whether that
    particular test touches JWTs or Oracle-shaped config directly.
    """
    monkeypatch.setenv("ORACLE_USER", "test_user")
    monkeypatch.setenv("ORACLE_PASSWORD", "test_password")
    monkeypatch.setenv("ORACLE_DSN", "test_dsn")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-do-not-use-in-prod")
    monkeypatch.delenv("BREVO_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> None:
    """
    `rate_limit.py`'s attempt counters are deliberately process-global,
    in-memory state (see that module's own docstring). Left alone,
    attempts from one test would count against the next one — every
    test in this suite hits the same fake client IP (`request.client`
    under `TestClient` is a fixed loopback address), so without this
    the 4th or 5th test to call a rate-limited endpoint would
    unexpectedly get a 429.
    """
    from app import rate_limit

    rate_limit._attempts.clear()
    yield
    rate_limit._attempts.clear()


@pytest.fixture
def store() -> FakeOracleStore:
    """A fresh, empty fake `sellers`/`otp_codes` store for one test."""
    return FakeOracleStore()


@pytest.fixture
def sent_emails() -> dict[str, list[tuple[str, str]]]:
    """
    Captures `(email, code)` for every fake signup/password-reset
    email "sent" during a test, keyed by `"signup"` / `"reset"`, so a
    test can grab the real OTP code main.py issued (codes are hashed
    at rest — see otp.py — so there's no other way to recover the
    plaintext short of capturing it here, the same place a real
    inbox would).
    """
    return {"signup": [], "reset": []}


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
    store: FakeOracleStore,
    sent_emails: dict[str, list[tuple[str, str]]],
) -> TestClient:
    from app import duplicate_check, main, otp

    fake_get_connection = make_fake_get_connection(store)
    monkeypatch.setattr(main, "get_connection", fake_get_connection)
    monkeypatch.setattr(otp, "get_connection", fake_get_connection)
    # Task 75 — `duplicate_check.is_duplicate_transaction()` holds its
    # own `from .db import get_connection` reference (like `otp.py`
    # does), separate from `main`'s, so it needs its own patch too or
    # `POST /receipts/{id}/verify`'s duplicate-check step would reach
    # past the fake and hit a real (unconfigured) Oracle connection.
    monkeypatch.setattr(duplicate_check, "get_connection", fake_get_connection)

    def _fake_send_signup(email: str, code: str) -> None:
        sent_emails["signup"].append((email, code))

    def _fake_send_reset(email: str, code: str) -> None:
        sent_emails["reset"].append((email, code))

    monkeypatch.setattr(main, "send_signup_otp_email", _fake_send_signup)
    monkeypatch.setattr(main, "send_password_reset_otp_email", _fake_send_reset)

    with TestClient(main.app) as test_client:
        yield test_client
