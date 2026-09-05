"""
Task 98: a small stand-in for the real OCI Object Storage SDK client,
mirroring `fake_oracle.py`'s role for `oracledb` (Task 72) — the real
`oci` package *is* installed (it's a normal `requirements.txt`
dependency, same as `oracledb`), but there's no real OCI tenancy
available in CI/sandbox environments to actually authenticate against
or a real bucket to call `get_bucket` on.

Unlike `fake_oracle.py`, this doesn't need to fake query *shapes* —
`app/object_storage.py` only ever makes one kind of call
(`client.get_bucket(namespace, bucket_name)`), used solely by
`check_object_storage()` (Task 91) to prove the configured credentials/
namespace/bucket actually agree with something real in OCI. So this
fake started out much smaller than `fake_oracle.py`: one class
(`FakeObjectStorageClient`) with a configurable `get_bucket()` — no
in-memory "store" of buckets/objects was needed yet, since no code in
this codebase uploaded through this fake before Task 99.

Task 99 extends `FakeObjectStorageClient` with a `put_object()` method
(recording calls, configurable success/failure via
`FakePutObjectOutcome` — mirrors `FakeGetBucketOutcome`'s shape) so
`app/thumbnail.py`'s `upload_thumbnail()` (Task 93) can be tested the
same way `check_object_storage()` already is: no real store is needed
here either, since nothing in this codebase reads an uploaded object
back — `upload_thumbnail()` only needs to know whether the call
succeeded or raised, same as `get_bucket()`. `test_object_storage.py`'s
shared `ALL_OCI_ENV_VARS`/`_set_all_env()` env-var helpers also moved
here from that file with Task 99, since they're now used by two test
files, not one — this module, not either test file, is the right home
for OCI-related test fixtures/helpers, the same role `fake_oracle.py`
already plays for Oracle-related ones.

`app/object_storage.py`'s `get_client()` builds a *real*
`oci.object_storage.ObjectStorageClient(config)` from env vars — there
is no dependency-injection point to swap a fake in through. Tests
instead monkeypatch `oci.object_storage.ObjectStorageClient` itself
(the class object on the real, installed `oci` package) to this fake's
class, the same "monkeypatch the thing `main.py`/`object_storage.py`
looks up at call time" approach `test_health_and_startup.py` already
uses for `check_connection`/`check_browser`. Because `get_client()`
does `oci.object_storage.ObjectStorageClient(config)` (an attribute
lookup at call time, not a name imported into `object_storage.py`'s
own namespace), patching the attribute on the `oci.object_storage`
module is enough — no `object_storage.py`-specific patch target is
needed the way `fake_oracle.py` needs `make_fake_get_connection()` per
module that imported `get_connection` by name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

import oci

# All eight `object_storage.py` env vars a test needs set for
# `get_client()`/`check_object_storage()`/`upload_thumbnail()` to reach
# their "config present" path. `OCI_KEY_FILE_PASSPHRASE` is
# deliberately excluded — it's optional (see `_build_sdk_config()`),
# so `_set_all_env()` below explicitly deletes it rather than setting
# a value, so tests start from a known "no passphrase" baseline and
# opt in with their own `monkeypatch.setenv(...)` when a passphrase
# case is what they're testing.
ALL_OCI_ENV_VARS = {
    "OCI_NAMESPACE": "test-namespace",
    "OCI_REGION": "eu-frankfurt-1",
    "OCI_BUCKET_NAME": "test-bucket",
    "OCI_TENANCY_OCID": "ocid1.tenancy.oc1..aaaatenancy",
    "OCI_USER_OCID": "ocid1.user.oc1..aaaauser",
    "OCI_FINGERPRINT": "aa:bb:cc:dd:ee:ff",
    "OCI_KEY_FILE": "/tmp/fake-oci-key.pem",
}


def _set_all_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    """Set every required OCI_* env var to a valid fake value, with per-call overrides, and clear the optional passphrase var."""
    for key, value in ALL_OCI_ENV_VARS.items():
        monkeypatch.setenv(key, overrides.get(key, value))
    monkeypatch.delenv("OCI_KEY_FILE_PASSPHRASE", raising=False)


@dataclass
class FakeGetBucketOutcome:
    """
    What a `FakeObjectStorageClient.get_bucket()` call should do:
    either succeed (return a stand-in response object) or raise a
    given exception instance. Kept as one small config object rather
    than two constructor args so a test can build it once and reuse it
    across `FakeObjectStorageClient(...)` instantiations if needed.
    """

    raises: Exception | None = None


@dataclass
class FakePutObjectOutcome:
    """
    What a `FakeObjectStorageClient.put_object()` call should do:
    mirrors `FakeGetBucketOutcome`'s "succeed or raise a given
    exception instance" shape, for Task 99's `upload_thumbnail()`
    tests. Kept as its own dataclass, not reusing
    `FakeGetBucketOutcome`, since `get_bucket()` and `put_object()` are
    independent calls a test may want to configure independently (e.g.
    a bucket lookup that succeeds but an upload that fails, or vice
    versa) — one shared outcome object would force both to always
    agree.
    """

    raises: Exception | None = None


class FakeObjectStorageClient:
    """
    Drop-in stand-in for `oci.object_storage.ObjectStorageClient`.

    Records the `config` dict it was constructed with (so a test can
    assert `get_client()` assembled the right fields from env vars —
    e.g. that `pass_phrase` is only present when
    `OCI_KEY_FILE_PASSPHRASE` was set), every `get_bucket(namespace,
    bucket_name)` call it received (Task 98), and every
    `put_object(namespace, bucket_name, object_name, put_object_body,
    content_type=...)` call it received (Task 99). Each method either
    returns a minimal success stand-in or raises whatever its own
    outcome was configured with — the two are independent, per
    `FakePutObjectOutcome`'s docstring above.
    """

    def __init__(
        self,
        config: dict[str, Any],
        outcome: FakeGetBucketOutcome | None = None,
        put_object_outcome: FakePutObjectOutcome | None = None,
    ) -> None:
        self.config = config
        self.outcome = outcome or FakeGetBucketOutcome()
        self.put_object_outcome = put_object_outcome or FakePutObjectOutcome()
        self.get_bucket_calls: list[tuple[str, str]] = []
        self.put_object_calls: list[tuple[str, str, str, Any, str | None]] = []

    def get_bucket(self, namespace: str, bucket_name: str) -> Any:
        self.get_bucket_calls.append((namespace, bucket_name))
        if self.outcome.raises is not None:
            raise self.outcome.raises
        # Real `get_bucket` returns an `oci.response.Response` wrapping
        # a `Bucket` model; nothing in this codebase reads anything off
        # the return value (`check_object_storage()` only cares whether
        # the call raised), so a bare sentinel object is enough.
        return object()

    def put_object(
        self,
        namespace: str,
        bucket_name: str,
        object_name: str,
        put_object_body: Any,
        content_type: str | None = None,
        **kwargs: Any,
    ) -> Any:
        # `**kwargs` absorbs any other keyword the real SDK accepts
        # (e.g. `opc_client_request_id`) that `upload_thumbnail()`
        # doesn't currently pass, so adding one there later wouldn't
        # need a matching change here just to keep this fake callable.
        self.put_object_calls.append(
            (namespace, bucket_name, object_name, put_object_body, content_type)
        )
        if self.put_object_outcome.raises is not None:
            raise self.put_object_outcome.raises
        # Real `put_object` returns an `oci.response.Response`;
        # `upload_thumbnail()` never reads anything off it (it builds
        # the returned URL itself from namespace/bucket/region/object
        # name), so a bare sentinel object is enough here too.
        return object()


def make_fake_object_storage_client_class(
    outcome: FakeGetBucketOutcome | None = None,
    put_object_outcome: FakePutObjectOutcome | None = None,
) -> type[FakeObjectStorageClient]:
    """
    Returns a `FakeObjectStorageClient` subclass whose `__init__`
    doesn't need `outcome`/`put_object_outcome` passed in by the
    caller (since `get_client()` in `app/object_storage.py` constructs
    the client itself, as `oci.object_storage.ObjectStorageClient(config)`,
    with no way for a test to pass extra constructor args through). A
    test monkeypatches `oci.object_storage.ObjectStorageClient` to
    this class, then reads calls/outcomes back off the instance
    `get_client()` returns.
    """
    fixed_outcome = outcome or FakeGetBucketOutcome()
    fixed_put_outcome = put_object_outcome or FakePutObjectOutcome()

    class _Bound(FakeObjectStorageClient):
        def __init__(self, config: dict[str, Any]) -> None:
            super().__init__(config, fixed_outcome, fixed_put_outcome)

    return _Bound


def service_error(status: int = 404, code: str = "BucketNotFound", message: str = "The bucket 'nonexistent' does not exist in namespace 'ns'.") -> oci.exceptions.ServiceError:
    """A real `oci.exceptions.ServiceError`, built with realistic-looking args, for tests that need `check_object_storage()` to hit that specific except branch."""
    return oci.exceptions.ServiceError(status, code, {}, message)
