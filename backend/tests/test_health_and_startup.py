"""
Task 78: automated tests for the cross-cutting backend surface —
`/health*` endpoints, the Task 43 generic-500 handler, Task 39's
startup config validation, and Task 40's CORS origin parsing. Sixth
and final item in Phase 7's backend schedule (see
PROJECT_ROADMAP.md); after this, Phase 7 moves on to the frontend
test-infra tasks (79-84) and then E2E (85-88).

None of this fits the `fake_oracle.py`-backed `client` fixture as
neatly as Tasks 73-77's DB-heavy CRUD endpoints did:

- `GET /health/db` and `GET /health/playwright` each call one small,
  already-isolated function (`db.check_connection()` /
  `browser.check_browser()`) that `main.py` imports by name — the
  same monkeypatch-the-imported-name pattern Task 75's
  `test_receipts.py` already uses for
  `parse_cbe_receipt`/`parse_telebirr_receipt`, applied here to those
  two functions instead. No `fake_oracle.py` changes needed, and a
  real Oracle connection / real headless-browser launch is never
  made. Both `check_connection()` and `check_browser()` already
  *never raise* on their own (see their own docstrings) — they
  degrade to a 200 response with `"connected"`/`"browser_ready":
  False` — so the "DB down" / "browser broken" cases below assert a
  200 with that false flag, not an error status.
- The Task 43 generic-500 handler is exercised by making
  `check_connection()` raise something *other* than the two
  exception types it already catches internally (`OracleConfigError`,
  `oracledb.Error`) — a plain `RuntimeError` reaches `main.py`
  completely uncaught, the same as any other genuinely unexpected
  exception would, and `handle_unexpected_error` is what's left to
  catch it.
- Task 39's startup validation and Task 40's CORS origin parsing both
  run once — on FastAPI's "startup" event
  (`_validate_startup_config()`) or at module-import time
  (`_cors_allowed_origins`) — not per-request, unlike everything else
  in this suite, which reuses one already-started `client`.
  Startup-validation tests reuse the already-imported `app.main`
  module and its already-built `app` object directly:
  `_validate_startup_config()` re-reads `os.environ` fresh every time
  it runs, so a plain `monkeypatch.delenv(...)` before entering a
  *new* `TestClient(main.app)` context is enough — no reload needed.
  CORS tests instead need `importlib.reload(app.main)`, since
  `_cors_allowed_origins` / the `app.add_middleware(CORSMiddleware,
  ...)` call only run once, at import time — the `fresh_main` fixture
  below reloads the module again on teardown (after `monkeypatch` has
  already reverted this test's env vars, thanks to `conftest.py`'s
  autouse `_env` fixture setting the baseline ORACLE_*/JWT_SECRET_KEY
  values back), so every later test file's `client` fixture — which
  reuses `app.main.app` without reloading it — sees the same
  module-level state it always has, not whatever the last CORS test
  left behind.
"""

from __future__ import annotations

import importlib
import logging

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def fresh_main():
    """
    Yields the `app.main` module for a test that needs to reload it
    (to pick up env vars read only at import time, e.g.
    `CORS_ALLOWED_ORIGINS`). Always reloads again on teardown — even
    if the test itself never got around to it or raised — so
    module-level state (`_cors_allowed_origins`, the `CORSMiddleware`
    it's baked into) is back to matching `conftest.py`'s baseline env
    before the next test file's `client` fixture reuses the same
    `app.main.app` object.
    """
    from app import main as main_module

    try:
        yield main_module
    finally:
        importlib.reload(main_module)


# --- GET /health -----------------------------------------------------


def test_health_ok(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "natra-backend"}


# --- GET /health/db ----------------------------------------------------


def test_health_db_connected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main

    monkeypatch.setattr(main, "check_connection", lambda: {"connected": True})
    resp = client.get("/health/db")
    assert resp.status_code == 200
    assert resp.json() == {"service": "natra-backend", "connected": True}


def test_health_db_not_connected_degrades_to_200(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`check_connection()` never raises on its own (it catches
    `OracleConfigError`/`oracledb.Error` internally) — a broken DB
    surfaces as a 200 with `connected: False` and an `error` string,
    not an HTTP error status."""
    from app import main

    monkeypatch.setattr(
        main,
        "check_connection",
        lambda: {"connected": False, "error": "Oracle error: ORA-12154"},
    )
    resp = client.get("/health/db")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "natra-backend"
    assert body["connected"] is False
    assert body["error"] == "Oracle error: ORA-12154"


# --- GET /health/playwright ---------------------------------------------


def test_health_playwright_ready(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main

    monkeypatch.setattr(main, "check_browser", lambda: {"browser_ready": True})
    resp = client.get("/health/playwright")
    assert resp.status_code == 200
    assert resp.json() == {"service": "natra-backend", "browser_ready": True}


def test_health_playwright_not_ready_degrades_to_200(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same never-raises contract as `check_connection()` — see
    `browser.check_browser()`'s own docstring."""
    from app import main

    monkeypatch.setattr(
        main,
        "check_browser",
        lambda: {"browser_ready": False, "error": "Executable doesn't exist"},
    )
    resp = client.get("/health/playwright")
    assert resp.status_code == 200
    body = resp.json()
    assert body["browser_ready"] is False
    assert body["error"] == "Executable doesn't exist"


# --- Task 43: generic-500 handler ---------------------------------------


def test_unhandled_exception_returns_generic_500(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A genuinely unexpected exception — one `check_connection()`
    doesn't already catch itself — reaches `main.py` uncaught and
    lands on `handle_unexpected_error`: a 500 with the fixed, generic
    `{"detail": "Internal server error"}` body. The real exception
    message must never reach the client, but it must still be
    logged server-side (`logger.error(..., exc_info=exc)`) so nothing
    is lost for debugging.

    Built as its own `TestClient(main.app, raise_server_exceptions=False)`
    rather than reusing the shared `client` fixture: with the default
    `raise_server_exceptions=True`, `TestClient` re-raises the original
    exception into the test itself once the ASGI transport sees one
    occurred, even though `handle_unexpected_error` already sent a real
    500 response — that would defeat the point of this test, which is
    to check what the *client* actually receives.
    """
    from app import main

    def _boom() -> dict:
        raise RuntimeError("super secret internal detail — must never leak")

    monkeypatch.setattr(main, "check_connection", _boom)

    with caplog.at_level(logging.ERROR, logger="natra"):
        with TestClient(main.app, raise_server_exceptions=False) as test_client:
            resp = test_client.get("/health/db")

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}
    assert "super secret internal detail" not in resp.text

    assert any(
        record.name == "natra" and record.exc_info is not None for record in caplog.records
    ), "the real exception should still be logged server-side"


def test_http_exceptions_are_unaffected_by_the_generic_handler(client: TestClient) -> None:
    """FastAPI's own, more specific handler for `HTTPException` still
    runs first — an ordinary 404 (e.g. an admin-only endpoint hit with
    no token, which raises `HTTPException(401)`) keeps its real
    `{"detail": "..."}` message, not the generic 500 body."""
    resp = client.get("/admin/settlements")
    assert resp.status_code == 401
    assert resp.json() != {"detail": "Internal server error"}


# --- Task 39: startup config validation ---------------------------------


def test_startup_raises_on_missing_critical_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main

    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(main.StartupConfigError, match="JWT_SECRET_KEY"):
        with TestClient(main.app):
            pass


def test_startup_raises_and_lists_every_missing_critical_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import main

    monkeypatch.delenv("ORACLE_USER", raising=False)
    monkeypatch.delenv("ORACLE_DSN", raising=False)

    with pytest.raises(main.StartupConfigError) as excinfo:
        with TestClient(main.app):
            pass

    message = str(excinfo.value)
    assert "ORACLE_USER" in message
    assert "ORACLE_DSN" in message
    # ORACLE_PASSWORD/JWT_SECRET_KEY are still set by the autouse `_env`
    # fixture — only the two vars actually deleted above should be
    # reported missing.
    assert "ORACLE_PASSWORD" not in message
    assert "JWT_SECRET_KEY" not in message


def test_startup_succeeds_with_every_critical_var_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Baseline: `conftest.py`'s autouse `_env` fixture already sets
    every critical var, so startup succeeds without raising —
    confirmed directly here rather than only implicitly, via every
    other test file's `client` fixture already depending on it."""
    from app import main

    with TestClient(main.app):
        pass


def test_startup_warns_but_does_not_raise_on_missing_recommended_env_vars(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """`ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH` are deliberately NOT fatal
    (see `_validate_startup_config()`'s own docstring) — a missing one
    only logs a warning; the app still starts and serves buyers/
    sellers normally."""
    from app import main

    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)

    with caplog.at_level(logging.WARNING, logger="natra"):
        with TestClient(main.app) as test_client:
            resp = test_client.get("/health")

    assert resp.status_code == 200
    assert any(
        "ADMIN_EMAIL" in record.message or "ADMIN_PASSWORD_HASH" in record.message
        for record in caplog.records
    )


# --- Task 40: CORS origin parsing ----------------------------------------


class TestParseCorsOrigins:
    """Direct unit tests of `_parse_cors_origins()` — the pure parsing
    function, independent of the app/middleware it feeds. Covers every
    input shape Task 40's own docstring calls out."""

    def test_none_means_zero_origins(self) -> None:
        from app.main import _parse_cors_origins

        assert _parse_cors_origins(None) == []

    def test_empty_string_means_zero_origins(self) -> None:
        from app.main import _parse_cors_origins

        assert _parse_cors_origins("") == []

    def test_whitespace_only_means_zero_origins(self) -> None:
        from app.main import _parse_cors_origins

        assert _parse_cors_origins("   ") == []

    def test_single_origin(self) -> None:
        from app.main import _parse_cors_origins

        assert _parse_cors_origins("http://localhost:5173") == ["http://localhost:5173"]

    def test_multiple_origins_comma_separated(self) -> None:
        from app.main import _parse_cors_origins

        assert _parse_cors_origins(
            "http://localhost:5173,https://natra.example.com"
        ) == ["http://localhost:5173", "https://natra.example.com"]

    def test_whitespace_around_origins_is_trimmed(self) -> None:
        from app.main import _parse_cors_origins

        assert _parse_cors_origins(
            " http://localhost:5173 , https://natra.example.com "
        ) == ["http://localhost:5173", "https://natra.example.com"]

    def test_trailing_comma_does_not_produce_a_blank_wildcard_entry(self) -> None:
        from app.main import _parse_cors_origins

        assert _parse_cors_origins("http://localhost:5173,") == ["http://localhost:5173"]

    def test_double_comma_does_not_produce_a_blank_wildcard_entry(self) -> None:
        from app.main import _parse_cors_origins

        assert _parse_cors_origins("http://localhost:5173,,https://natra.example.com") == [
            "http://localhost:5173",
            "https://natra.example.com",
        ]


def test_cors_unconfigured_allows_no_cross_origin_requests(
    monkeypatch: pytest.MonkeyPatch, fresh_main
) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    reloaded = importlib.reload(fresh_main)

    with TestClient(reloaded.app) as test_client:
        resp = test_client.get("/health", headers={"Origin": "https://natra.example.com"})

    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers


def test_cors_allows_a_configured_origin(monkeypatch: pytest.MonkeyPatch, fresh_main) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://natra.example.com")
    reloaded = importlib.reload(fresh_main)

    with TestClient(reloaded.app) as test_client:
        resp = test_client.get("/health", headers={"Origin": "https://natra.example.com"})

    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "https://natra.example.com"


def test_cors_rejects_a_non_configured_origin(
    monkeypatch: pytest.MonkeyPatch, fresh_main
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://natra.example.com")
    reloaded = importlib.reload(fresh_main)

    with TestClient(reloaded.app) as test_client:
        resp = test_client.get("/health", headers={"Origin": "https://evil.example.com"})

    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers


def test_cors_credentials_are_never_allowed(monkeypatch: pytest.MonkeyPatch, fresh_main) -> None:
    """`allow_credentials=False` throughout (see Task 40's docstring —
    the frontend authenticates via a Bearer token, never cookies)."""
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://natra.example.com")
    reloaded = importlib.reload(fresh_main)

    with TestClient(reloaded.app) as test_client:
        resp = test_client.get("/health", headers={"Origin": "https://natra.example.com"})

    assert "access-control-allow-credentials" not in resp.headers


def test_cors_preflight_allows_only_the_configured_methods(
    monkeypatch: pytest.MonkeyPatch, fresh_main
) -> None:
    """`allow_methods=["GET", "POST", "PUT"]` — a preflight for a
    method this API never uses (e.g. `DELETE`) is not granted."""
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://natra.example.com")
    reloaded = importlib.reload(fresh_main)

    with TestClient(reloaded.app) as test_client:
        allowed = test_client.options(
            "/health",
            headers={
                "Origin": "https://natra.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
        rejected = test_client.options(
            "/health",
            headers={
                "Origin": "https://natra.example.com",
                "Access-Control-Request-Method": "DELETE",
            },
        )

    assert "POST" in allowed.headers.get("access-control-allow-methods", "")
    assert rejected.status_code == 400
