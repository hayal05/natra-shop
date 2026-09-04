"""
NATRA backend — one-time-passcode (OTP) issuance and verification for
email-based signup verification and password reset.

Task 68 (Phase 6): closes the gap flagged when the project was
reviewed after Task 67 — sellers could register and never have their
email confirmed, and had no self-service way to regain access to an
account if they forgot their password. Both are closed the same way:
a 6-digit numeric OTP, emailed via Brevo's transactional email API
(see brevo_email.py), that the seller submits back within a short
window. `main.py` wires this into four endpoints: signup verification
(+ resend) and password-reset request/confirm.

Design decisions:

1. **Codes are hashed at rest, never stored in plain text** — same
   reasoning as `security.py`'s password hashing: a DB read (backup,
   leaked snapshot, insider) shouldn't hand out live, usable
   credentials. Reuses `security.hash_password`/`verify_password`
   (PBKDF2-HMAC-SHA256) rather than introducing a second hashing
   scheme for a six-digit value.
2. **One active code per (email, purpose) at a time.** Requesting a
   new OTP deletes any previous unconsumed one for that email/purpose
   pair first — simpler to reason about than several valid codes
   coexisting, and it means an intercepted old code stops working the
   moment a new one is requested rather than remaining live alongside
   it. `otp_codes.email` + `purpose` also carries a UNIQUE constraint
   at the DB level (see schema.sql) as a safety net against a race
   between two concurrent `issue_otp()` calls for the same pair.
3. **10-minute expiry, 5 verify attempts.** Short-lived enough that an
   intercepted code is only useful briefly. `attempts` increments on
   every *failed* verify and the code is rejected outright (without
   even comparing) once it reaches 5 — forcing a fresh `request`
   rather than allowing unlimited guesses against one code. Combined
   with `rate_limit.py`'s existing per-IP throttle (Task 44), reused
   by every endpoint in `main.py` that calls into this module, this
   bounds both "guess the code" and "spam my inbox" attacks.
4. **Purpose-scoped.** The same table backs both signup verification
   and password reset (`purpose` is `PURPOSE_SIGNUP` or
   `PURPOSE_PASSWORD_RESET`) so a code issued for one can never be
   replayed for the other.
5. **No account-existence leakage.** This module itself doesn't check
   whether a seller row exists for `email` before issuing a code — the
   caller decides that. `main.py`'s
   `POST /sellers/password-reset/request` only calls `issue_otp()`
   when a matching seller was actually found, but still returns the
   same generic response either way, mirroring the anti-enumeration
   reasoning `POST /sellers/login` already documents.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from .brevo_email import send_email
from .db import get_connection
from .security import hash_password, verify_password

logger = logging.getLogger("natra")

PURPOSE_SIGNUP = "signup"
PURPOSE_PASSWORD_RESET = "password_reset"

_TTL_MINUTES = 10
_MAX_ATTEMPTS = 5
_CODE_DIGITS = 6


class OTPResult:
    """String constants returned by `verify_otp()` describing the outcome."""

    VALID = "valid"
    INVALID = "invalid"
    EXPIRED = "expired"
    TOO_MANY_ATTEMPTS = "too_many_attempts"
    NOT_FOUND = "not_found"


def _generate_code() -> str:
    """Cryptographically random 6-digit code, zero-padded (e.g. "004821")."""
    return f"{secrets.randbelow(10 ** _CODE_DIGITS):0{_CODE_DIGITS}d}"


def issue_otp(email: str, purpose: str) -> str:
    """
    Generate a new OTP for `email`/`purpose`, store only its hash
    (replacing any previous unconsumed code for the same pair), and
    return the plain-text code. The caller is responsible for emailing
    it out immediately (see `send_signup_otp_email()` /
    `send_password_reset_otp_email()` below) — this function itself
    never sends anything, so it can't be used to leak a code anywhere
    but a fresh outbound email.
    """
    code = _generate_code()
    code_hash = hash_password(code)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_TTL_MINUTES)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM otp_codes WHERE email = :email AND purpose = :purpose",
                email=email,
                purpose=purpose,
            )
            cur.execute(
                """
                INSERT INTO otp_codes (email, purpose, code_hash, expires_at)
                VALUES (:email, :purpose, :code_hash, :expires_at)
                """,
                email=email,
                purpose=purpose,
                code_hash=code_hash,
                expires_at=expires_at,
            )
            conn.commit()

    return code


def verify_otp(email: str, purpose: str, code: str) -> str:
    """
    Verify `code` for `email`/`purpose`. On success, consumes the code
    (deletes its row, so it can never be reused) and returns
    `OTPResult.VALID`. On failure, returns one of the other
    `OTPResult` constants; every case except `NOT_FOUND` and
    `TOO_MANY_ATTEMPTS` (where there's nothing useful left to count)
    increments the stored row's attempt counter first.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT RAWTOHEX(id), code_hash, expires_at, attempts
                FROM otp_codes
                WHERE email = :email AND purpose = :purpose
                """,
                email=email,
                purpose=purpose,
            )
            row = cur.fetchone()

            if row is None:
                return OTPResult.NOT_FOUND

            otp_id, code_hash, expires_at, attempts = row

            if attempts >= _MAX_ATTEMPTS:
                return OTPResult.TOO_MANY_ATTEMPTS

            if expires_at < datetime.now(timezone.utc):
                cur.execute("DELETE FROM otp_codes WHERE id = HEXTORAW(:id)", id=otp_id)
                conn.commit()
                return OTPResult.EXPIRED

            if not verify_password(code, code_hash):
                cur.execute(
                    "UPDATE otp_codes SET attempts = attempts + 1 WHERE id = HEXTORAW(:id)",
                    id=otp_id,
                )
                conn.commit()
                return OTPResult.INVALID

            cur.execute("DELETE FROM otp_codes WHERE id = HEXTORAW(:id)", id=otp_id)
            conn.commit()
            return OTPResult.VALID


def invalidate_otp(email: str, purpose: str) -> None:
    """Delete any outstanding code for `email`/`purpose`, if one exists."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM otp_codes WHERE email = :email AND purpose = :purpose",
                email=email,
                purpose=purpose,
            )
            conn.commit()


def send_signup_otp_email(email: str, code: str) -> None:
    """
    Email a signup-verification code via Brevo. Raises `BrevoConfigError`/
    `BrevoSendError` (from brevo_email.py) on failure — callers in
    main.py decide whether that should fail the request or just be
    logged (see POST /sellers/register's handling: the account is
    already created by the time this runs, so a send failure there
    doesn't roll back the registration).
    """
    send_email(
        to_email=email,
        subject="Verify your NATRA email address",
        html_content=(
            "<p>Welcome to NATRA!</p>"
            f"<p>Your email verification code is: <strong>{code}</strong></p>"
            f"<p>This code expires in {_TTL_MINUTES} minutes. If you didn't create "
            "a NATRA seller account, you can ignore this email.</p>"
        ),
    )


def send_password_reset_otp_email(email: str, code: str) -> None:
    """Email a password-reset code via Brevo."""
    send_email(
        to_email=email,
        subject="Your NATRA password reset code",
        html_content=(
            "<p>We received a request to reset your NATRA seller password.</p>"
            f"<p>Your password reset code is: <strong>{code}</strong></p>"
            f"<p>This code expires in {_TTL_MINUTES} minutes. If you didn't request "
            "this, you can safely ignore this email — your password will not be "
            "changed.</p>"
        ),
    )
