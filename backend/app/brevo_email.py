"""
NATRA backend — transactional email via Brevo (formerly Sendinblue).

Task 68 (Phase 6): the email transport behind OTP delivery (see
otp.py). Calls Brevo's REST API directly with `urllib.request` from
the standard library rather than adding the `sib-api-v3-sdk` /
`brevo-python` package as a dependency — this project already prefers
a stdlib approach over an extra dependency where one is
straightforward (see security.py's hashlib-based password hashing for
the same reasoning), and sending one JSON POST per OTP email doesn't
need a full SDK.

Configuration (see backend/.env.example):
  BREVO_API_KEY       required to send anything at all
  BREVO_SENDER_EMAIL  the "from" address — must be a sender verified
                       in the Brevo account, or Brevo rejects the send
  BREVO_SENDER_NAME   the "from" display name (defaults to "NATRA")

If either required variable is missing, `send_email()` raises
`BrevoConfigError` rather than silently no-op'ing — an OTP email that
silently never sends is worse than a loud error, since the seller has
no way to know their code is never coming and no page tells them
otherwise. Callers decide how to surface that (see otp.py and
main.py's signup/reset endpoints for how each one is handled).
"""

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger("natra")

_API_URL = "https://api.brevo.com/v3/smtp/email"
_DEFAULT_SENDER_NAME = "NATRA"
_TIMEOUT_SECONDS = 10


class BrevoConfigError(RuntimeError):
    """Raised when BREVO_API_KEY or BREVO_SENDER_EMAIL is not configured."""


class BrevoSendError(RuntimeError):
    """Raised when Brevo's API rejects the send, or the request otherwise fails."""


def send_email(to_email: str, subject: str, html_content: str) -> None:
    """
    Send one transactional email via Brevo's `POST /v3/smtp/email`.

    Raises `BrevoConfigError` if the required env vars aren't set, or
    `BrevoSendError` if Brevo's API returns a non-2xx response, the
    network request fails, or the response can't be read. Never
    swallows a failure itself — see this module's docstring.
    """
    api_key = os.environ.get("BREVO_API_KEY")
    sender_email = os.environ.get("BREVO_SENDER_EMAIL")
    if not api_key or not sender_email:
        raise BrevoConfigError(
            "Missing required environment variable: "
            "BREVO_API_KEY and/or BREVO_SENDER_EMAIL"
        )
    sender_name = os.environ.get("BREVO_SENDER_NAME") or _DEFAULT_SENDER_NAME

    payload = json.dumps(
        {
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": to_email}],
            "subject": subject,
            "htmlContent": html_content,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        _API_URL,
        data=payload,
        method="POST",
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": api_key,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            if response.status >= 300:
                body = response.read().decode("utf-8", errors="replace")
                logger.error("Brevo send failed (HTTP %s): %s", response.status, body)
                raise BrevoSendError(f"Brevo returned HTTP {response.status}: {body}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.error("Brevo send failed (HTTP %s): %s", exc.code, body)
        raise BrevoSendError(f"Brevo returned HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        logger.error("Brevo send failed (network error): %s", exc.reason)
        raise BrevoSendError(f"Could not reach Brevo API: {exc.reason}") from exc
