"""
Task 98: automated tests for `app/object_storage.py` — the Object
Storage client wrapper (Task 90) and its health check (Task 91).
First of Phase 8's four test-writing tasks (98-101); Tasks 99-101
cover the validation/upload helper, the upload endpoint, and the three
surfaced GET endpoints respectively.

Unlike `test_products.py`/`test_receipts.py`/etc., this file tests
`app/object_storage.py`'s functions directly rather than going through
`TestClient` and an endpoint — `get_client()`, `get_namespace()`,
`get_bucket_name()`, and `get_region()` are plain functions with no
HTTP surface of their own (`GET /health/object-storage` is the one
endpoint that calls into this module, and is covered separately in
`test_health_and_startup.py`, the same file every other `/health*`
route already lives in).

`fake_oci.py`'s `FakeObjectStorageClient` stands in for the real
`oci.object_storage.ObjectStorageClient` the same way `fake_oracle.py`
stands in for a real Oracle connection — see that file's own docstring
for why a monkeypatched class attribute, not a constructor argument,
is the injection point here.

None of these tests need `conftest.py`'s `client`/`store` fixtures —
this module has no FastAPI route and no `sellers`/`products` tables
involved, just env vars and a monkeypatched OCI class.
"""

from __future__ import annotations

import pytest

import oci

from app import object_storage
from tests.fake_oci import (
    ALL_OCI_ENV_VARS,
    FakeGetBucketOutcome,
    _set_all_env,
    make_fake_object_storage_client_class,
    service_error,
)

# NOTE (Task 99): `ALL_OCI_ENV_VARS`/`_set_all_env()` used to be defined
# in this file. They moved to `fake_oci.py` when Task 99 added a second
# test file (`test_thumbnail.py`) that also needs a fully-configured
# OCI_* environment — see that module's docstring.


# --- get_namespace() / get_bucket_name() / get_region() -----------------


class TestSimpleGetters:
    def test_get_namespace_returns_the_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OCI_NAMESPACE", "my-namespace")
        assert object_storage.get_namespace() == "my-namespace"

    def test_get_namespace_raises_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OCI_NAMESPACE", raising=False)
        with pytest.raises(object_storage.ObjectStorageConfigError):
            object_storage.get_namespace()

    def test_get_bucket_name_returns_the_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OCI_BUCKET_NAME", "my-bucket")
        assert object_storage.get_bucket_name() == "my-bucket"

    def test_get_bucket_name_raises_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OCI_BUCKET_NAME", raising=False)
        with pytest.raises(object_storage.ObjectStorageConfigError):
            object_storage.get_bucket_name()

    def test_get_region_returns_the_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OCI_REGION", "us-ashburn-1")
        assert object_storage.get_region() == "us-ashburn-1"

    def test_get_region_raises_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OCI_REGION", raising=False)
        with pytest.raises(object_storage.ObjectStorageConfigError):
            object_storage.get_region()

    def test_missing_var_error_message_names_the_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OCI_NAMESPACE", raising=False)
        with pytest.raises(object_storage.ObjectStorageConfigError, match="OCI_NAMESPACE"):
            object_storage.get_namespace()


# --- get_client() / _build_sdk_config() ----------------------------------


class TestGetClient:
    @pytest.fixture(autouse=True)
    def _patch_client_class(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """
        Every test in this class monkeypatches the real
        `oci.object_storage.ObjectStorageClient` to
        `FakeObjectStorageClient`, so `get_client()` returns a fake
        whose `.config` a test can inspect, instead of the real SDK
        client attempting (and failing) to read a real key file.
        """
        monkeypatch.setattr(
            oci.object_storage, "ObjectStorageClient", make_fake_object_storage_client_class()
        )

    def test_raises_config_error_when_user_ocid_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_all_env(monkeypatch)
        monkeypatch.delenv("OCI_USER_OCID", raising=False)
        with pytest.raises(object_storage.ObjectStorageConfigError, match="OCI_USER_OCID"):
            object_storage.get_client()

    def test_raises_config_error_when_key_file_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_all_env(monkeypatch)
        monkeypatch.delenv("OCI_KEY_FILE", raising=False)
        with pytest.raises(object_storage.ObjectStorageConfigError, match="OCI_KEY_FILE"):
            object_storage.get_client()

    def test_raises_config_error_when_fingerprint_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_all_env(monkeypatch)
        monkeypatch.delenv("OCI_FINGERPRINT", raising=False)
        with pytest.raises(object_storage.ObjectStorageConfigError, match="OCI_FINGERPRINT"):
            object_storage.get_client()

    def test_raises_config_error_when_tenancy_ocid_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_all_env(monkeypatch)
        monkeypatch.delenv("OCI_TENANCY_OCID", raising=False)
        with pytest.raises(object_storage.ObjectStorageConfigError, match="OCI_TENANCY_OCID"):
            object_storage.get_client()

    def test_raises_config_error_when_region_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_all_env(monkeypatch)
        monkeypatch.delenv("OCI_REGION", raising=False)
        with pytest.raises(object_storage.ObjectStorageConfigError, match="OCI_REGION"):
            object_storage.get_client()

    def test_builds_expected_config_without_passphrase(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_all_env(monkeypatch)
        client = object_storage.get_client()
        assert client.config == {
            "user": ALL_OCI_ENV_VARS["OCI_USER_OCID"],
            "key_file": ALL_OCI_ENV_VARS["OCI_KEY_FILE"],
            "fingerprint": ALL_OCI_ENV_VARS["OCI_FINGERPRINT"],
            "tenancy": ALL_OCI_ENV_VARS["OCI_TENANCY_OCID"],
            "region": ALL_OCI_ENV_VARS["OCI_REGION"],
        }
        assert "pass_phrase" not in client.config

    def test_includes_passphrase_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_all_env(monkeypatch)
        monkeypatch.setenv("OCI_KEY_FILE_PASSPHRASE", "s3cret")
        client = object_storage.get_client()
        assert client.config["pass_phrase"] == "s3cret"

    def test_omits_passphrase_when_blank(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An empty string is falsy, same treatment as an unset var (mirrors `_get_required_env`'s own `if not value` check)."""
        _set_all_env(monkeypatch)
        monkeypatch.setenv("OCI_KEY_FILE_PASSPHRASE", "")
        client = object_storage.get_client()
        assert "pass_phrase" not in client.config


# --- check_object_storage() ----------------------------------------------


class TestCheckObjectStorage:
    def test_ready_when_bucket_lookup_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_all_env(monkeypatch)
        monkeypatch.setattr(
            oci.object_storage,
            "ObjectStorageClient",
            make_fake_object_storage_client_class(),
        )

        result = object_storage.check_object_storage()

        assert result == {"object_storage_ready": True}

    def test_calls_get_bucket_with_configured_namespace_and_bucket(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_all_env(monkeypatch)
        fake_class = make_fake_object_storage_client_class()
        monkeypatch.setattr(oci.object_storage, "ObjectStorageClient", fake_class)

        # get_client() builds a fresh instance internally, so capture it
        # by wrapping the class rather than reusing a pre-built one.
        instances: list = []
        real_init = fake_class.__init__

        def _capturing_init(self, config):  # noqa: ANN001 - test helper
            real_init(self, config)
            instances.append(self)

        monkeypatch.setattr(fake_class, "__init__", _capturing_init)

        object_storage.check_object_storage()

        assert len(instances) == 1
        assert instances[0].get_bucket_calls == [
            (ALL_OCI_ENV_VARS["OCI_NAMESPACE"], ALL_OCI_ENV_VARS["OCI_BUCKET_NAME"])
        ]

    def test_degrades_to_false_when_config_is_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Never raises — a completely unconfigured deployment (no OCI_* vars at all, e.g. thumbnails never set up) gets a clear health response, not a 500."""
        for key in ALL_OCI_ENV_VARS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv("OCI_KEY_FILE_PASSPHRASE", raising=False)

        result = object_storage.check_object_storage()

        assert result["object_storage_ready"] is False
        assert "OCI_USER_OCID" in result["error"]

    def test_degrades_to_false_on_oci_service_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reachable OCI endpoint, but the bucket call itself fails (bad credentials, wrong namespace, bucket doesn't exist) — `exc.message`, not the full exception, ends up in the response."""
        _set_all_env(monkeypatch)
        outcome = FakeGetBucketOutcome(
            raises=service_error(message="The bucket 'test-bucket' does not exist in namespace 'test-namespace'.")
        )
        monkeypatch.setattr(
            oci.object_storage,
            "ObjectStorageClient",
            make_fake_object_storage_client_class(outcome),
        )

        result = object_storage.check_object_storage()

        assert result == {
            "object_storage_ready": False,
            "error": "OCI error: The bucket 'test-bucket' does not exist in namespace 'test-namespace'.",
        }

    def test_degrades_to_false_on_unexpected_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mirrors `check_browser()`'s own broad `except Exception` — client construction can fail in ways as varied as a bad key-file path (`InvalidConfig`, `IOError`) that don't fit `ObjectStorageConfigError` or `ServiceError`."""
        _set_all_env(monkeypatch)
        outcome = FakeGetBucketOutcome(raises=IOError("No such file or directory: key.pem"))
        monkeypatch.setattr(
            oci.object_storage,
            "ObjectStorageClient",
            make_fake_object_storage_client_class(outcome),
        )

        result = object_storage.check_object_storage()

        assert result == {
            "object_storage_ready": False,
            "error": "No such file or directory: key.pem",
        }
