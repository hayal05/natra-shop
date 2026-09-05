"""
NATRA backend — thumbnail file validation and upload.

Phase 8, Task 92: `validate_thumbnail_file()` — a content-type/extension
allowlist plus a max-size check for a seller-uploaded product
thumbnail, raising `ThumbnailValidationError` with a clear, specific
message on any violation.

Phase 8, Task 93: `upload_thumbnail()` — generates a stable/unique
object name, uploads the file's bytes via `object_storage.py`'s Task
90 client, and returns the uploaded object's public URL. Calls Task
92's `validate_thumbnail_file()` first, so an invalid file never
reaches Object Storage at all.

Deliberately its own module, not added to `object_storage.py`: per
`object_storage.py`'s own Task 90 docstring, that module's entire
reason to exist is wrapping the OCI SDK client (client + namespace +
bucket + region + health check) — it has no opinion about thumbnails
specifically. This module is the other way around: it knows about
thumbnails (validation rules, object naming, URL shape) and treats
`object_storage.py` as a dependency, importing `get_client()`,
`get_namespace()`, `get_bucket_name()`, and `get_region()` from it
rather than re-reading the OCI_* env vars itself — the same
"`cbe.py`/`telebirr.py` build on `browser.py`" layering Tasks 20-23
already established.

## Scoped decisions made for Task 92

1. **Allowlist, not a denylist.** Only three raster formats a browser
   can always preview inline: JPEG, PNG, WebP. No SVG (XML-based — a
   real, documented XSS vector when served back to other users'
   browsers) and no GIF (animated thumbnails aren't a NATRA product
   requirement per `CLAUDE_MASTER_PROMPT.md`).
2. **Both content-type AND extension are checked, independently.**
   A content type is only what the client claims in its multipart
   upload; a mismatched or absent extension is one cheap, additional
   signal that something's off before `upload_thumbnail()` ever
   uploads the bytes. Neither check alone is real file-type
   verification (that would mean sniffing magic bytes, out of scope
   here — a validator, not a scanner), but requiring both to agree
   with the allowlist is a meaningfully higher bar than checking just
   one.
3. **500 KB max size**, matching the "thumbnails max 500 KB" limit
   already fixed for this project. Enforced in bytes
   (`MAX_THUMBNAIL_SIZE_BYTES`), not KB, since that's the unit every
   upload framework reports `file_size` in.
4. **`validate_thumbnail_file()` raises, doesn't return a result
   dict.** Unlike `validation.py`'s `validate_payment()` (which models
   several *expected*, distinct "this receipt didn't qualify" outcomes
   a caller needs to branch on), an invalid thumbnail upload is a
   single "reject this request" case with no further branching needed
   — Task 94's endpoint just needs to catch `ThumbnailValidationError`
   and turn it into a 400. Matches `object_storage.py`'s own
   `ObjectStorageConfigError` precedent for "a single clear reason
   this can't proceed" rather than `validation.py`'s multi-outcome
   dict shape.

## Scoped decisions made for Task 93

5. **Object naming: `thumbnails/{uuid4 hex}{extension}`.** Unique
   (UUID4, collision-proof for practical purposes) and stable (never
   derived from or reused across re-uploads of "the same" logical
   thumbnail — each upload gets its own object, matching Task 94's
   later job of just overwriting `products.thumbnail_ref` with the new
   URL rather than needing to delete the old object first). The
   `thumbnails/` prefix keeps this feature's objects visually grouped
   in the bucket from Task 90's seller-profile-picture objects that
   may be added later, without needing a second bucket. The extension
   is taken from the now-validated filename, so the stored object
   always carries a real, allowlisted extension even though the
   generated name has nothing else to do with the original filename.
6. **URL shape: OCI's standard public object URL**,
   `https://objectstorage.{region}.oraclecloud.com/n/{namespace}/b/{bucket}/o/{object_name}`
   — no pre-authenticated request (PAR) generation. This assumes the
   bucket itself is configured with public object-read visibility in
   the OCI Console (a one-time bucket setting, not something this code
   controls); if that's ever not the case, this URL will 404 for
   buyers even though the upload itself succeeded. Flagged here rather
   than silently assumed, since nothing in this codebase verifies
   bucket visibility.
7. **`upload_thumbnail()` wraps Object Storage failures in
   `ThumbnailUploadError`, a distinct exception from
   `ThumbnailValidationError`.** Task 94's endpoint needs to tell "the
   file itself was invalid" (400, the caller's fault) apart from "the
   file was fine but the upload to OCI failed" (502/500, not the
   caller's fault) — one combined exception type would force Task 94
   to inspect the message text to tell those apart. Mirrors
   `check_object_storage()`'s two-tier
   `oci.exceptions.ServiceError` / broad-`Exception` catch, but wraps
   and re-raises here instead of returning a dict, since an upload
   helper (unlike a health check) has no reason to make partial
   failure look like a normal return value.
"""

import os
import uuid

import oci

from .object_storage import get_bucket_name, get_client, get_namespace, get_region

ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})

# 500 KB, per the project's fixed thumbnail size limit. Stored in bytes
# since that's the unit `file_size` arrives in from any upload framework.
MAX_THUMBNAIL_SIZE_BYTES = 500 * 1024


class ThumbnailValidationError(ValueError):
    """
    Raised by `validate_thumbnail_file()` when a thumbnail fails the
    content-type, extension, or size check. A `ValueError` subclass
    (not `RuntimeError`, unlike `ObjectStorageConfigError`) since this
    is about the caller-supplied *input* being invalid, not about the
    app's own environment/config being broken.
    """


def validate_thumbnail_file(filename: str, content_type: str, file_size: int) -> None:
    """
    Validate a candidate product thumbnail before Task 93 ever uploads
    its bytes to Object Storage.

    Args:
        filename: the uploaded file's original name (used only for its
            extension — never trusted as a storage path; Task 93 will
            generate its own stable/unique object name).
        content_type: the MIME type the client declared for the upload
            (e.g. from `UploadFile.content_type` in FastAPI).
        file_size: size of the uploaded content in bytes.

    Raises `ThumbnailValidationError` with a specific, user-facing
    message on the first check that fails, in this order:
      1. file is empty (`file_size <= 0`)
      2. file exceeds `MAX_THUMBNAIL_SIZE_BYTES`
      3. `content_type` isn't in `ALLOWED_CONTENT_TYPES`
      4. `filename`'s extension isn't in `ALLOWED_EXTENSIONS`

    Returns `None` (no value) when the file passes every check — the
    "valid" outcome is simply "didn't raise", matching
    `object_storage.py`'s `_get_required_env()` style rather than
    `validation.py`'s result-dict style (see decision 4 above).
    """
    if file_size <= 0:
        raise ThumbnailValidationError("Thumbnail file is empty.")

    if file_size > MAX_THUMBNAIL_SIZE_BYTES:
        raise ThumbnailValidationError(
            f"Thumbnail file is too large ({file_size} bytes). "
            f"Maximum allowed size is {MAX_THUMBNAIL_SIZE_BYTES} bytes (500 KB)."
        )

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ThumbnailValidationError(
            f"Unsupported content type '{content_type}'. "
            f"Allowed types: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}."
        )

    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ThumbnailValidationError(
            f"Unsupported file extension '{ext or '(none)'}'. "
            f"Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )


class ThumbnailUploadError(RuntimeError):
    """
    Raised by `upload_thumbnail()` when the file passed validation but
    the actual Object Storage upload failed (bad/expired credentials,
    unreachable endpoint, bucket misconfiguration, etc.). Kept distinct
    from `ThumbnailValidationError` so Task 94's endpoint can map each
    to a different HTTP status without parsing message text — see
    decision 7 above.
    """


def _build_object_url(region: str, namespace: str, bucket_name: str, object_name: str) -> str:
    """
    OCI's standard public object URL shape. Assumes the bucket has
    public object-read visibility (decision 6 above) — this function
    only formats the URL, it never checks that assumption.
    """
    return (
        f"https://objectstorage.{region}.oraclecloud.com/"
        f"n/{namespace}/b/{bucket_name}/o/{object_name}"
    )


def upload_thumbnail(file_bytes: bytes, filename: str, content_type: str) -> str:
    """
    Validate and upload a seller-supplied product thumbnail, returning
    its public URL.

    Args:
        file_bytes: the raw uploaded file content.
        filename: the uploaded file's original name (used only for its
            extension, both for validation and for the generated
            object name's own extension).
        content_type: the MIME type the client declared for the
            upload.

    Steps:
        1. Calls `validate_thumbnail_file()` with `len(file_bytes)` as
           the size, so validation and upload always agree on the same
           byte count — no separate, possibly-stale `file_size`
           argument for a caller to pass inconsistently.
        2. Generates a unique object name: `thumbnails/{uuid4 hex}{ext}`
           (decision 5 above).
        3. Uploads via Task 90's `get_client().put_object(...)`, using
           Task 90's `get_namespace()`/`get_bucket_name()` and this
           task's new `get_region()`.
        4. Returns the object's public URL via `_build_object_url()`
           (decision 6 above).

    Raises `ThumbnailValidationError` unchanged if validation fails
    (nothing is uploaded in that case). Raises `ThumbnailUploadError`
    if validation passes but the Object Storage call itself fails —
    wraps `ObjectStorageConfigError` (missing OCI_* env vars),
    `oci.exceptions.ServiceError` (reachable endpoint, failed call),
    and any other exception the client construction or upload can
    raise, mirroring `check_object_storage()`'s three-tier catch
    (decision 7 above).
    """
    validate_thumbnail_file(filename, content_type, len(file_bytes))

    ext = os.path.splitext(filename)[1].lower()
    object_name = f"thumbnails/{uuid.uuid4().hex}{ext}"

    try:
        client = get_client()
        namespace = get_namespace()
        bucket_name = get_bucket_name()
        region = get_region()
        client.put_object(namespace, bucket_name, object_name, file_bytes, content_type=content_type)
    except oci.exceptions.ServiceError as exc:
        raise ThumbnailUploadError(f"OCI error: {exc.message}") from exc
    except Exception as exc:  # noqa: BLE001 - deliberately broad, mirrors check_object_storage(): covers ObjectStorageConfigError (missing env vars) and client-construction failures (bad key-file path, InvalidConfig, IOError) alike
        raise ThumbnailUploadError(str(exc)) from exc

    return _build_object_url(region, namespace, bucket_name, object_name)
