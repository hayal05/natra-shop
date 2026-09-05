"""
Task 99: automated tests for `app/thumbnail.py` — thumbnail file
validation (Task 92, `validate_thumbnail_file()`) and the upload
helper (Task 93, `upload_thumbnail()`). Second of Phase 8's four
test-writing tasks (98-101); Task 98 (already done) covers
`app/object_storage.py` itself and provides the `fake_oci.py` fake
this file builds on. Task 100 (the upload endpoint) and Task 101 (the
three surfaced GET endpoints) are separate, not-yet-started tasks.

Two very different functions under test, split into two test classes:

- `validate_thumbnail_file()` is a pure function with no Object
  Storage interaction at all (see `thumbnail.py`'s own docstring,
  decision 4) — its tests need no fake, no monkeypatched OCI client,
  and no OCI_* env vars, just plain function calls and
  `pytest.raises`/message assertions.
- `upload_thumbnail()` does call Object Storage (via
  `object_storage.py`'s `get_client()`), so its tests reuse
  `fake_oci.py`'s `FakeObjectStorageClient` the same way
  `test_object_storage.py` does: monkeypatch
  `oci.object_storage.ObjectStorageClient` to a fake class (Task 98),
  now exercising that fake's Task-99-added `put_object()` method
  rather than `get_bucket()`. `ALL_OCI_ENV_VARS`/`_set_all_env()` also
  come from `fake_oci.py` (moved there by this task — see that
  module's docstring) so both this file and `test_object_storage.py`
  share one definition of "a fully-configured OCI_* environment"
  instead of keeping two copies in sync by hand.

Nothing here touches `conftest.py`'s `client`/`store` fixtures — like
`test_object_storage.py`, this module has no FastAPI route and no
`sellers`/`products` tables involved (Task 100's endpoint tests are
where a real `TestClient` call first shows up for this feature).
"""

from __future__ import annotations

import re

import pytest

import oci

from app import thumbnail
from tests.fake_oci import (
    ALL_OCI_ENV_VARS,
    FakePutObjectOutcome,
    _set_all_env,
    make_fake_object_storage_client_class,
)

_OBJECT_NAME_RE = re.compile(r"^thumbnails/[0-9a-f]{32}(\.[a-z0-9]+)$")


# --- validate_thumbnail_file() -------------------------------------------


class TestValidateThumbnailFile:
    def test_accepts_a_valid_jpeg(self) -> None:
        assert (
            thumbnail.validate_thumbnail_file("photo.jpg", "image/jpeg", 1024) is None
        )

    def test_accepts_a_valid_png(self) -> None:
        assert (
            thumbnail.validate_thumbnail_file("photo.png", "image/png", 1024) is None
        )

    def test_accepts_a_valid_webp(self) -> None:
        assert (
            thumbnail.validate_thumbnail_file("photo.webp", "image/webp", 1024) is None
        )

    def test_accepts_extension_at_exactly_the_size_limit(self) -> None:
        """The boundary itself (`file_size == MAX_THUMBNAIL_SIZE_BYTES`) is still valid — only exceeding it fails."""
        assert (
            thumbnail.validate_thumbnail_file(
                "photo.jpg", "image/jpeg", thumbnail.MAX_THUMBNAIL_SIZE_BYTES
            )
            is None
        )

    def test_extension_check_is_case_insensitive(self) -> None:
        assert (
            thumbnail.validate_thumbnail_file("photo.JPG", "image/jpeg", 1024) is None
        )

    def test_rejects_empty_file(self) -> None:
        with pytest.raises(thumbnail.ThumbnailValidationError, match="empty"):
            thumbnail.validate_thumbnail_file("photo.jpg", "image/jpeg", 0)

    def test_rejects_negative_file_size(self) -> None:
        """Not something a real upload framework should ever report, but `file_size <= 0` is the actual check, not `== 0` — covered directly."""
        with pytest.raises(thumbnail.ThumbnailValidationError, match="empty"):
            thumbnail.validate_thumbnail_file("photo.jpg", "image/jpeg", -1)

    def test_rejects_file_over_max_size(self) -> None:
        too_big = thumbnail.MAX_THUMBNAIL_SIZE_BYTES + 1
        with pytest.raises(thumbnail.ThumbnailValidationError, match="too large"):
            thumbnail.validate_thumbnail_file("photo.jpg", "image/jpeg", too_big)

    def test_size_error_message_names_both_the_actual_and_max_size(self) -> None:
        too_big = thumbnail.MAX_THUMBNAIL_SIZE_BYTES + 1
        with pytest.raises(
            thumbnail.ThumbnailValidationError,
            match=f"{too_big} bytes.*{thumbnail.MAX_THUMBNAIL_SIZE_BYTES} bytes",
        ):
            thumbnail.validate_thumbnail_file("photo.jpg", "image/jpeg", too_big)

    def test_rejects_disallowed_content_type(self) -> None:
        with pytest.raises(
            thumbnail.ThumbnailValidationError, match="Unsupported content type"
        ):
            thumbnail.validate_thumbnail_file("photo.jpg", "image/gif", 1024)

    def test_rejects_svg_content_type(self) -> None:
        """Explicitly called out in `thumbnail.py`'s decision 1 as excluded on purpose (XSS vector), not just an accidental omission — worth its own test."""
        with pytest.raises(thumbnail.ThumbnailValidationError, match="Unsupported content type"):
            thumbnail.validate_thumbnail_file("photo.svg", "image/svg+xml", 1024)

    def test_rejects_disallowed_extension_with_allowed_content_type(self) -> None:
        """Content type and extension are checked independently (decision 2) — a spoofed content type paired with a bad extension is still rejected."""
        with pytest.raises(
            thumbnail.ThumbnailValidationError, match="Unsupported file extension"
        ):
            thumbnail.validate_thumbnail_file("photo.gif", "image/jpeg", 1024)

    def test_rejects_missing_extension(self) -> None:
        with pytest.raises(
            thumbnail.ThumbnailValidationError, match=r"\(none\)"
        ):
            thumbnail.validate_thumbnail_file("photo", "image/jpeg", 1024)

    def test_rejects_empty_filename(self) -> None:
        with pytest.raises(thumbnail.ThumbnailValidationError, match=r"\(none\)"):
            thumbnail.validate_thumbnail_file("", "image/jpeg", 1024)

    def test_checks_are_evaluated_in_documented_order(self) -> None:
        """Size is checked before content type (documented order 1-4 in `validate_thumbnail_file()`'s docstring) — an oversized file with a bad content type still reports the size problem first."""
        too_big = thumbnail.MAX_THUMBNAIL_SIZE_BYTES + 1
        with pytest.raises(thumbnail.ThumbnailValidationError, match="too large"):
            thumbnail.validate_thumbnail_file("photo.exe", "application/exe", too_big)


# --- upload_thumbnail() ---------------------------------------------------


class TestUploadThumbnail:
    @pytest.fixture(autouse=True)
    def _configure_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Every test in this class needs a fully-configured OCI_* environment — `upload_thumbnail()`'s own config-missing behavior is exercised separately below by deleting one var back out."""
        _set_all_env(monkeypatch)

    def _patch_client(
        self, monkeypatch: pytest.MonkeyPatch, put_object_outcome: FakePutObjectOutcome | None = None
    ) -> type:
        fake_class = make_fake_object_storage_client_class(put_object_outcome=put_object_outcome)
        monkeypatch.setattr(oci.object_storage, "ObjectStorageClient", fake_class)
        return fake_class

    def test_returns_the_expected_public_url_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_client(monkeypatch)

        url = thumbnail.upload_thumbnail(b"fake-bytes", "photo.jpg", "image/jpeg")

        expected_prefix = (
            f"https://objectstorage.{ALL_OCI_ENV_VARS['OCI_REGION']}.oraclecloud.com/"
            f"n/{ALL_OCI_ENV_VARS['OCI_NAMESPACE']}/b/{ALL_OCI_ENV_VARS['OCI_BUCKET_NAME']}/o/"
        )
        assert url.startswith(expected_prefix)
        object_name = url[len(expected_prefix) :]  # e.g. "thumbnails/<uuid4 hex>.jpg"
        assert _OBJECT_NAME_RE.match(object_name)
        assert object_name.endswith(".jpg")

    def test_object_name_extension_matches_original_filename_lowercased(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_client(monkeypatch)

        url = thumbnail.upload_thumbnail(b"fake-bytes", "photo.PNG", "image/png")

        assert url.endswith(".png")

    def test_two_uploads_of_the_same_filename_get_different_object_names(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Object naming is UUID4-based (decision 5), so re-uploading "the same" logical thumbnail never collides or overwrites the previous object."""
        self._patch_client(monkeypatch)

        first = thumbnail.upload_thumbnail(b"fake-bytes-1", "photo.jpg", "image/jpeg")
        second = thumbnail.upload_thumbnail(b"fake-bytes-2", "photo.jpg", "image/jpeg")

        assert first != second

    def test_calls_put_object_with_the_uploaded_bytes_and_content_type(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_class = self._patch_client(monkeypatch)
        instances: list = []
        real_init = fake_class.__init__

        def _capturing_init(self, config):  # noqa: ANN001 - test helper
            real_init(self, config)
            instances.append(self)

        monkeypatch.setattr(fake_class, "__init__", _capturing_init)

        url = thumbnail.upload_thumbnail(b"fake-image-bytes", "photo.jpg", "image/jpeg")
        object_name = url.rsplit("/o/", 1)[1]  # already "thumbnails/<uuid4 hex>.jpg"

        assert len(instances) == 1
        assert instances[0].put_object_calls == [
            (
                ALL_OCI_ENV_VARS["OCI_NAMESPACE"],
                ALL_OCI_ENV_VARS["OCI_BUCKET_NAME"],
                object_name,
                b"fake-image-bytes",
                "image/jpeg",
            )
        ]

    def test_validates_before_touching_object_storage(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An invalid file is rejected by Task 92's validator before `get_client()` is ever called — no OCI client gets constructed at all, matching `upload_thumbnail()`'s own docstring ("nothing is uploaded in that case")."""
        fake_class = self._patch_client(monkeypatch)
        instances: list = []
        real_init = fake_class.__init__

        def _capturing_init(self, config):  # noqa: ANN001 - test helper
            real_init(self, config)
            instances.append(self)

        monkeypatch.setattr(fake_class, "__init__", _capturing_init)

        with pytest.raises(thumbnail.ThumbnailValidationError):
            thumbnail.upload_thumbnail(b"fake-bytes", "photo.gif", "image/gif")

        assert instances == []

    def test_uses_len_of_file_bytes_as_the_validated_size_not_a_separate_argument(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`upload_thumbnail()` has no separate `file_size` parameter — validation and upload always agree on the same byte count because both derive it from `file_bytes` itself."""
        self._patch_client(monkeypatch)
        too_big = b"x" * (thumbnail.MAX_THUMBNAIL_SIZE_BYTES + 1)

        with pytest.raises(thumbnail.ThumbnailValidationError, match="too large"):
            thumbnail.upload_thumbnail(too_big, "photo.jpg", "image/jpeg")

    def test_wraps_missing_config_as_upload_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A valid file, but Object Storage isn't configured at all (e.g. thumbnails feature never set up) — `ObjectStorageConfigError` gets wrapped into `ThumbnailUploadError`, not left as-is, so Task 100's endpoint only needs to catch one exception type for every "upload itself failed" case."""
        self._patch_client(monkeypatch)
        monkeypatch.delenv("OCI_USER_OCID", raising=False)

        with pytest.raises(
            thumbnail.ThumbnailUploadError, match="OCI_USER_OCID"
        ):
            thumbnail.upload_thumbnail(b"fake-bytes", "photo.jpg", "image/jpeg")

    def test_wraps_oci_service_error_as_upload_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Reachable OCI endpoint, but the `put_object` call itself fails — `exc.message`, the concise half of a `ServiceError`, ends up in `ThumbnailUploadError`'s message, not the full exception."""
        outcome = FakePutObjectOutcome(
            raises=oci.exceptions.ServiceError(
                403, "NotAuthorizedOrNotFound", {}, "You are not authorized to perform this request."
            )
        )
        self._patch_client(monkeypatch, put_object_outcome=outcome)

        with pytest.raises(
            thumbnail.ThumbnailUploadError,
            match="OCI error: You are not authorized to perform this request.",
        ):
            thumbnail.upload_thumbnail(b"fake-bytes", "photo.jpg", "image/jpeg")

    def test_wraps_unexpected_exception_as_upload_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mirrors `check_object_storage()`'s own broad `except Exception` (decision 7) — client construction/upload can fail in ways as varied as a bad key-file path that don't fit `ObjectStorageConfigError` or `ServiceError`."""
        outcome = FakePutObjectOutcome(raises=IOError("No such file or directory: key.pem"))
        self._patch_client(monkeypatch, put_object_outcome=outcome)

        with pytest.raises(
            thumbnail.ThumbnailUploadError, match="No such file or directory: key.pem"
        ):
            thumbnail.upload_thumbnail(b"fake-bytes", "photo.jpg", "image/jpeg")

    def test_validation_error_is_not_wrapped_as_upload_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`ThumbnailValidationError` and `ThumbnailUploadError` are deliberately distinct (decision 7) — a validation failure must never come back as the "upload" error type."""
        self._patch_client(monkeypatch)

        with pytest.raises(thumbnail.ThumbnailValidationError):
            thumbnail.upload_thumbnail(b"fake-bytes", "photo.gif", "image/gif")
