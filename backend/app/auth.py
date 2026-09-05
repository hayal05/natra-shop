"""
NATRA backend — JWT access tokens for seller/admin authentication.

Phase 1, Task 7: issues a signed JWT after a successful seller login.
Phase 1, Task 8: adds verification of that token, used by the first
protected endpoint (POST /products).
Phase 1, Task 14: adds create_admin_access_token() for Master Admin login.
Both seller and admin tokens now carry a `role` claim ("seller"/"admin")
so a protected endpoint can tell them apart (needed starting with Task 15,
which restricts some endpoints to the admin role only).
"""

import os
from datetime import datetime, timedelta, timezone

import jwt

_ALGORITHM = "HS256"
_EXPIRES_HOURS = 24


class JWTConfigError(RuntimeError):
    """Raised when JWT_SECRET_KEY is not configured."""


class InvalidTokenError(RuntimeError):
    """Raised when a token is missing, malformed, expired, or has a bad signature."""


def _get_secret() -> str:
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        raise JWTConfigError("Missing required environment variable: JWT_SECRET_KEY")
    return secret


def create_access_token(seller_id: str, email: str) -> str:
    """Create a signed JWT identifying this seller, valid for 24 hours."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": seller_id,
        "email": email,
        "role": "seller",
        "iat": now,
        "exp": now + timedelta(hours=_EXPIRES_HOURS),
    }
    return jwt.encode(payload, _get_secret(), algorithm=_ALGORITHM)


def create_admin_access_token(email: str) -> str:
    """
    Create a signed JWT identifying the Master Admin, valid for 24 hours.

    There is exactly one Master Admin identity (see ARCHITECTURE.md) — no
    admin id/row, so `sub` is the fixed string "admin" rather than a
    database id, and `role` is "admin" so admin-only endpoints (starting
    Task 15) can be distinguished from seller endpoints by a protected
    route's dependency.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "admin",
        "email": email,
        "role": "admin",
        "iat": now,
        "exp": now + timedelta(hours=_EXPIRES_HOURS),
    }
    return jwt.encode(payload, _get_secret(), algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Verify a JWT's signature and expiry and return its payload
    (``sub`` = seller id, ``email``).

    Raises `InvalidTokenError` for any malformed/expired/bad-signature
    token, and `JWTConfigError` if `JWT_SECRET_KEY` isn't configured.
    """
    try:
        return jwt.decode(token, _get_secret(), algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
