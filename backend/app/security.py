"""
NATRA backend — password hashing.

Phase 1, Task 6: secure password hashing/verification for seller accounts.
Uses PBKDF2-HMAC-SHA256 from the Python standard library (`hashlib`) so no
extra dependency is needed. Passwords are never stored or compared in
plain text.
"""

import hashlib
import hmac
import os

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 260_000


def hash_password(password: str) -> str:
    """
    Hash a password for storage.

    Returns a self-describing string: "<algorithm>$<iterations>$<salt_hex>$<hash_hex>",
    so verify_password() can re-derive the same hash later even if the
    iteration count changes in the future.
    """
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _ITERATIONS
    )
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plain-text password against a hash produced by hash_password()."""
    try:
        algorithm, iterations_str, salt_hex, hash_hex = stored_hash.split("$")
    except ValueError:
        return False
    if algorithm != _ALGORITHM:
        return False

    iterations = int(iterations_str)
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(hash_hex)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(derived, expected)
