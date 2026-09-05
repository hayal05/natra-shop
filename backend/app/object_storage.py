"""
NATRA backend — Oracle Object Storage client wrapper.

Phase 8, Task 90: initialize an OCI SDK client from Task 89's eight
config env vars. Mirrors `db.py`'s Task 4 role for the Oracle database
connection: a small, isolated "build me a working client" helper that
later tasks build on. Task 91 (health check) is the one that actually
calls something on this client to prove it's reachable — this module's
only job is assembling a correctly-configured client (and the two
resource identifiers, namespace and bucket, that every later Object
Storage call will need alongside it).

No upload/download/list logic lives here yet — that starts at Task 93
(`upload_thumbnail()`, in `app/thumbnail.py`), which imports
`get_client()`, `get_namespace()`, `get_bucket_name()`, and (Task 93's
own small addition) `get_region()` from this module instead of
re-reading the OCI_* env vars itself, the same way `cbe.py`/`telebirr.py`
(Tasks 20-23) build on `browser.py`'s Task 18 role rather than each
launching their own browser.

Expected environment variables (added in Task 89 — see
`.env.example`/`.env.production.example` for where to find each value
in the OCI Console):
- OCI_NAMESPACE             Object Storage namespace (tenancy-specific,
                            NOT the bucket name)
- OCI_REGION                region the bucket lives in, e.g. eu-frankfurt-1
- OCI_BUCKET_NAME           the bucket itself; must already exist — this
                            app never creates buckets, only objects
                            inside one
- OCI_TENANCY_OCID          tenancy OCID
- OCI_USER_OCID             user OCID
- OCI_FINGERPRINT           fingerprint of the API signing key added
                            under that user
- OCI_KEY_FILE              path to that key's PEM private key file
                            (mirrors ORACLE_WALLET_DIR's path-not-
                            contents convention — never commit the key
                            file itself)
- OCI_KEY_FILE_PASSPHRASE   optional; only needed if OCI_KEY_FILE's key
                            was generated with a passphrase

All eight are "recommended", not fatal, at app startup (Task 89's call
in `_validate_startup_config()`) — nothing outside this module reads
them, so a deployment with thumbnails not yet configured keeps serving
every other existing flow. Calling `get_client()` without them
configured raises `ObjectStorageConfigError`, the same lazy-failure
shape `db.get_connection()` already has for Oracle.
"""

import os
from typing import Optional

import oci


class ObjectStorageConfigError(RuntimeError):
    """Raised when required Object Storage environment variables are missing."""


def _get_required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ObjectStorageConfigError(f"Missing required environment variable: {name}")
    return value


def _build_sdk_config() -> dict:
    """
    Assemble the config dict the OCI SDK's clients expect (`user`,
    `key_file`, `fingerprint`, `tenancy`, `region`, and optionally
    `pass_phrase`) from Task 89's env vars.
    """
    config = {
        "user": _get_required_env("OCI_USER_OCID"),
        "key_file": _get_required_env("OCI_KEY_FILE"),
        "fingerprint": _get_required_env("OCI_FINGERPRINT"),
        "tenancy": _get_required_env("OCI_TENANCY_OCID"),
        "region": _get_required_env("OCI_REGION"),
    }

    passphrase = os.environ.get("OCI_KEY_FILE_PASSPHRASE")
    if passphrase:
        config["pass_phrase"] = passphrase

    return config


def get_client() -> "oci.object_storage.ObjectStorageClient":
    """
    Build an `ObjectStorageClient` from Task 89's env vars.

    Unlike `db.get_connection()`, this isn't a context manager: OCI SDK
    clients are lightweight, reusable HTTP clients with no connection to
    open/close, so callers just call this each time (or hold onto the
    result) rather than wrapping it in a `with` block.

    Raises `ObjectStorageConfigError` if any required var is missing.
    Raises `oci.exceptions.InvalidConfig` (or a key-file read error) if
    the vars are present but don't describe a usable config, e.g. an
    `OCI_KEY_FILE` path that doesn't exist.
    """
    config = _build_sdk_config()
    return oci.object_storage.ObjectStorageClient(config)


def get_namespace() -> str:
    """
    The Object Storage namespace string later calls need alongside the
    client (e.g. `client.put_object(namespace, bucket, ...)`). Kept here,
    not re-read by each caller, for the same "one source of truth for
    OCI_* config" reason `get_client()` exists.
    """
    return _get_required_env("OCI_NAMESPACE")


def get_bucket_name() -> str:
    """The bucket name later calls need alongside the client and namespace."""
    return _get_required_env("OCI_BUCKET_NAME")


def get_region() -> str:
    """
    The region string later calls need to build a public object URL
    (Task 93's `upload_thumbnail()`), in OCI's standard
    `https://objectstorage.{region}.oraclecloud.com/n/{namespace}/b/{bucket}/o/{object}`
    form. Added alongside `get_namespace()`/`get_bucket_name()` rather
    than having Task 93 re-read `OCI_REGION` itself, for the same
    "one source of truth for OCI_* config" reason those two exist.
    """
    return _get_required_env("OCI_REGION")


def check_object_storage() -> dict:
    """
    Verify Object Storage is actually reachable and correctly configured
    by building a client from Task 90's `get_client()` and fetching the
    configured bucket's metadata (`get_bucket`) — the Object Storage
    equivalent of `check_connection()`'s "SELECT 1 FROM dual": the
    cheapest call that proves the credentials, namespace, and bucket
    name all agree with what's actually in OCI, not just that they're
    present as env vars.

    Returns a plain dict describing success/failure, the same shape as
    `check_browser()`/`check_connection()` — never raises, so a broken
    or unconfigured Object Storage setup degrades to a clear health
    response instead of a 500.
    """
    try:
        client = get_client()
        namespace = get_namespace()
        bucket_name = get_bucket_name()
        client.get_bucket(namespace, bucket_name)
        return {"object_storage_ready": True}
    except ObjectStorageConfigError as exc:
        return {"object_storage_ready": False, "error": str(exc)}
    except oci.exceptions.ServiceError as exc:
        # Reachable OCI endpoint, but the call itself failed (bad
        # credentials, wrong namespace, bucket doesn't exist, etc.) —
        # exc.message is the concise, user-facing half of what's
        # otherwise a large exception object.
        return {"object_storage_ready": False, "error": f"OCI error: {exc.message}"}
    except Exception as exc:  # noqa: BLE001 - deliberately broad, mirrors check_browser(): client construction can fail in ways as varied as a bad key-file path (InvalidConfig, IOError) that don't fit one specific OCI exception type
        return {"object_storage_ready": False, "error": str(exc)}
