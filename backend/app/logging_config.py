"""
NATRA backend — structured logging configuration.

Task 48. Before this task, `main.py`'s `logger = logging.getLogger("natra")`
(introduced by Task 39/43/44's warning/error calls) had no configuration of
its own: no handler, no formatter, no explicit level. Python's logging
module falls back to `logging.lastResort` in that case — a bare
`StreamHandler` on stderr at WARNING level, with the message text only, no
timestamp, no request context, and any `logger.info(...)` call silently
dropped. That's unusable for the production VM this backend is meant to
run on (Task 46/47): there'd be no way to correlate a slow or failing
request with a specific log line, and nothing below WARNING would ever
appear at all.

This module fixes that with the standard library only — `json` and
`logging`, nothing new added to `requirements.txt` (see
CLAUDE_MASTER_PROMPT.md's "avoid unnecessary libraries" rule).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

# Attributes every `logging.LogRecord` already has, so `_JsonFormatter`
# can tell a record's "standard" fields apart from whatever was passed via
# `logger.info(..., extra={...})` — only the latter get merged into the
# JSON output as extra top-level keys.
_STANDARD_RECORD_ATTRS = frozenset(
    logging.LogRecord(
        name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
    ).__dict__.keys()
) | {"message", "asctime"}


class _JsonFormatter(logging.Formatter):
    """
    Renders each log record as one JSON object per line (newline-delimited
    JSON) — easy for `journalctl`/any log shipper to parse without a custom
    grammar, unlike the default free-text format. Includes the exception
    traceback as a plain string field when present, rather than leaving it
    to `Formatter.formatException`'s multi-line text glued onto the message
    (which would break the one-JSON-object-per-line property this exists
    to guarantee).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS and key not in payload:
                payload[key] = value
        return json.dumps(payload, default=str)


def setup_logging() -> None:
    """
    Configures the root logger with a single JSON `StreamHandler` on
    stdout (not stderr — Uvicorn's own access/error logs already go to
    stderr by default; keeping application logs on stdout lets a systemd
    journal or log shipper tell the two apart by stream if it wants to,
    and matches `deploy/systemd/natra-backend.service`'s expectation that
    `journalctl -u natra-backend` shows everything either way, since
    systemd captures both).

    Configuring the ROOT logger, not just `logging.getLogger("natra")`,
    is deliberate: it also captures Uvicorn's own `uvicorn.error`/
    `uvicorn.access` loggers and anything oracledb/playwright/etc. log,
    so every log line the process produces gets the same JSON shape
    instead of just the ones this codebase emits directly.

    Level is controlled by the `LOG_LEVEL` env var (default `INFO`) —
    documented in `backend/.env.example`/`.env.production.example`, same
    pattern as every other configurable value in this codebase. An
    invalid value falls back to `INFO` with a warning, rather than
    raising and preventing startup — logging misconfiguration alone
    shouldn't be a `StartupConfigError`-grade failure (see Task 39's
    docstring for what actually is).

    Idempotent: safe to call more than once (e.g. if a test imports
    `app.main` multiple times) — clears any handlers this function
    itself previously added instead of stacking duplicate handlers,
    which would otherwise print every log line multiple times.
    """
    root_logger = logging.getLogger()

    level_name = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, None)
    invalid_level_name = None
    if not isinstance(level, int):
        invalid_level_name = level_name
        level = logging.INFO

    for existing in list(root_logger.handlers):
        if getattr(existing, "_natra_json_handler", False):
            root_logger.removeHandler(existing)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_JsonFormatter())
    handler._natra_json_handler = True  # marks this handler for the idempotency check above
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Logged only now, with the JSON handler already attached — logging
    # this any earlier (e.g. before addHandler above) would send it to
    # logging.lastResort's plain-text stderr handler instead, making the
    # very first line this module ever logs inconsistent with every line
    # after it.
    if invalid_level_name is not None:
        root_logger.warning(
            "Invalid LOG_LEVEL=%r, falling back to INFO", invalid_level_name
        )


class RequestLoggingMiddleware:
    """
    ASGI middleware (plain callable, not `BaseHTTPMiddleware` — avoids that
    class's known issue of breaking `request.client`/streaming responses in
    some Starlette versions) that logs one structured line per HTTP
    request: method, path, status code, and duration. This is the
    "structured logging" half of Task 48's roadmap entry that isn't
    already covered by Task 43's error handler (which only logs *uncaught*
    exceptions) — every request, successful or not, now produces exactly
    one correlatable log line.

    Deliberately logs `request.url.path` only, never the query string or
    body: `POST /sellers/login`/`POST /admin/login` receive passwords in
    the body (never the query string, per those endpoints' own request
    models), and a future receipt-verification retry could carry a
    receipt URL that a receipt provider might treat as sensitive. Nothing
    this middleware logs risks that.
    """

    def __init__(self, app) -> None:  # noqa: ANN001 - ASGI app, no fastapi type import needed here
        self.app = app
        self._logger = logging.getLogger("natra.request")

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.monotonic()
        status_code = 500  # overwritten below unless the app never sends a response at all

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        await self.app(scope, receive, send_wrapper)

        duration_ms = round((time.monotonic() - start) * 1000, 1)
        self._logger.info(
            "%s %s -> %s (%sms)",
            scope.get("method"),
            scope.get("path"),
            status_code,
            duration_ms,
            extra={
                "http_method": scope.get("method"),
                "http_path": scope.get("path"),
                "http_status": status_code,
                "duration_ms": duration_ms,
            },
        )
