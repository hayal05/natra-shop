"""
NATRA backend — Oracle Autonomous Database connection helper.

Phase 1, Task 4: establish a way to connect to Oracle Autonomous Database
and verify the connection works. No tables/schema/queries beyond a basic
liveness check yet — that starts at Task 5.

All connection details come from environment variables. Never hard-code
credentials here, and never commit a real `.env` file to GitHub.

Expected environment variables:
- ORACLE_USER            database username
- ORACLE_PASSWORD        database password
- ORACLE_DSN             connection string / TNS alias, e.g. the DSN name
                         from the Autonomous DB wallet's tnsnames.ora
- ORACLE_WALLET_DIR      optional; path to the unzipped Autonomous DB wallet
                         directory (contains tnsnames.ora, cwallet.sso, etc.)
- ORACLE_WALLET_PASSWORD optional; only needed if the wallet itself is
                         password-protected

If ORACLE_WALLET_DIR is not set, oracledb attempts a direct connection using
ORACLE_DSN as a full connect string instead (useful for local testing against
a non-Autonomous Oracle instance).
"""

import os
from contextlib import contextmanager
from typing import Iterator

import oracledb


class OracleConfigError(RuntimeError):
    """Raised when required Oracle connection environment variables are missing."""


def _get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise OracleConfigError(f"Missing required environment variable: {name}")
    return value


@contextmanager
def get_connection() -> Iterator["oracledb.Connection"]:
    """
    Open an Oracle connection using environment-provided credentials.

    Usage:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM dual")
    """
    user = _get_required_env("ORACLE_USER")
    password = _get_required_env("ORACLE_PASSWORD")
    dsn = _get_required_env("ORACLE_DSN")

    wallet_dir = os.environ.get("ORACLE_WALLET_DIR")
    wallet_password = os.environ.get("ORACLE_WALLET_PASSWORD")

    connect_kwargs = {"user": user, "password": password, "dsn": dsn}
    if wallet_dir:
        connect_kwargs["config_dir"] = wallet_dir
        connect_kwargs["wallet_location"] = wallet_dir
        if wallet_password:
            connect_kwargs["wallet_password"] = wallet_password

    connection = oracledb.connect(**connect_kwargs)
    try:
        yield connection
    finally:
        connection.close()


def check_connection() -> dict:
    """
    Attempt a real connection and a trivial query.

    Returns a plain dict describing success/failure. Never includes the
    password, and only includes enough detail to debug — not a full
    traceback with connection internals.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM dual")
                cur.fetchone()
        return {"connected": True}
    except OracleConfigError as exc:
        return {"connected": False, "error": str(exc)}
    except oracledb.Error as exc:
        return {"connected": False, "error": f"Oracle error: {exc}"}
