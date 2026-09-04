# NATRA — CURRENT STATUS

## Current Phase

Phase 8 — Product Thumbnails (opened by Task 89, at the user's explicit
instruction to skip ahead of Phase 7's still-outstanding Tasks 85-88 —
see "Note on phase order" below. Phase 7 — Automated Test Coverage —
is otherwise done through Task 84; Tasks 85-88, the Playwright E2E
suite, remain not started. Phase 6 — Backend Hardening / Ops — remains
complete, and Phase 5 — Frontend Build — remains complete)

### Note on phase order

Per the standing phase-control rule, doing Tasks 89-91 does NOT mean
Tasks 85-88 are being skipped permanently — they're simply not next by
default anymore. The user was told before Task 89 that 85 (E2E infra)
was the actual next task per PROJECT_ROADMAP.md and confirmed they
wanted 89 anyway. Tasks 85-88 are still tracked as "not started" in
PROJECT_ROADMAP.md and remain available whenever the user asks for
them; nothing about them was invalidated by doing 89-91 first.

## Completed Task

**Task 91: Object Storage health check.** Third and last of Phase 8's
twenty-one tasks (see PROJECT_ROADMAP.md) and last of the three tasks
the original Task 89 was split into (89 config — done — 90 client
wrapper — done — 91 health check). Adds `GET /health/object-storage`,
mirroring Task 18's `check_browser()` / `GET /health/playwright`
pattern field-for-field, using Task 90's `get_client()`,
`get_namespace()`, and `get_bucket_name()`.

- **`backend/app/object_storage.py`**: added `check_object_storage()`.
  Calls `get_client().get_bucket(namespace, bucket_name)` — the
  cheapest real API call that proves the credentials, namespace, and
  bucket name all agree with what's actually in OCI, the Object
  Storage equivalent of `check_connection()`'s `SELECT 1 FROM dual`.
  Never raises: catches `ObjectStorageConfigError` (missing env vars,
  same as Task 90 alone would raise), `oci.exceptions.ServiceError`
  (reachable endpoint, failed call — bad credentials, wrong namespace,
  bucket doesn't exist) separately for a cleaner `exc.message`, then a
  broad `Exception` fallback mirroring `check_browser()`'s — client
  construction can fail in shapes (bad key-file path, `InvalidConfig`,
  a raw `IOError`) that don't collapse into one specific OCI exception
  type. Returns `{"object_storage_ready": True}` or
  `{"object_storage_ready": False, "error": ...}`.
- **`backend/app/main.py`**: imports `check_object_storage`; adds
  `GET /health/object-storage`, a thin route handler identical in
  shape to `health_check_playwright()` — calls the `check_*` function,
  merges its dict into `{"service": "natra-backend", **result}`, no
  logic of its own. Added a Task 91 paragraph to the module docstring,
  after Task 89's, documenting the mirror-of-Task-18 shape and that
  Task 93 is still where real upload/download logic starts.
- **`PROJECT_ROADMAP.md`** (this task's row marked `done` in the
  Phase 8 table).

## Files Changed

- `backend/app/object_storage.py` — `check_object_storage()` added
- `backend/app/main.py` — import + `GET /health/object-storage` route
  + docstring paragraph
- `PROJECT_ROADMAP.md`, `CURRENT_STATUS.md` (this file) — Task 91
  marked done

No database changes. No frontend files touched. No new dependency —
`oci` was already added in Task 90.

## Database Changes

None.

## Errors Encountered

None.

## Fixes Made / Verification Performed

Unlike Tasks 89-90, this task's verification ran for real, not just as
a syntax check: `oci`, `fastapi`, `oracledb`, `playwright`, and the
rest of `requirements.txt`/`requirements-dev.txt` installed cleanly
into a fresh venv from PyPI (network access turned out to be available
in this sandbox after all — the "no network access" caveat on Tasks
89-90's verification no longer holds and can be disregarded going
forward).

- `pip install -r requirements.txt -r requirements-dev.txt` into
  `/tmp/venv` — succeeded, including `oci==2.135.2`.
- Imported `app.main` directly (not just `ast.parse`) — succeeds, and
  `[r.path for r in app.routes if 'health' in r.path]` confirms
  `/health/object-storage` is registered alongside the three existing
  health routes.
- Ran the full existing suite: `154 passed` — Task 91's changes don't
  break anything Tasks 73-78/98's precedent already covers (`GET
  /health/object-storage` itself has no dedicated tests yet; that's
  Task 98, which needs a fake in place of a real OCI client the same
  way `fake_oracle.py` stands in for `db.py`).
- Hit `GET /health/object-storage` directly via `TestClient` with no
  `OCI_*` vars set: `200 {"service": "natra-backend",
  "object_storage_ready": false, "error": "Missing required
  environment variable: OCI_USER_OCID"}` — confirms the endpoint
  degrades gracefully (200, not 500) exactly like `/health/db` and
  `/health/playwright` do when their own dependencies are unconfigured.
- Verified `oci.exceptions.ServiceError` (has a plain `.message`
  attribute) and `oci.object_storage.ObjectStorageClient` both import
  correctly from a bare `import oci`, confirming the exception-handling
  branches in `check_object_storage()` reference real, correctly-named
  symbols rather than assumed ones.

## Exact Next Small Task

**Task 92: Thumbnail file validation.** `validate_thumbnail_file()` —
content-type/extension allowlist and a max-size check, raising a clear
error. Pure function, no Object Storage interaction, no endpoint yet
(that's Task 94, after Task 93's upload helper). First of Phase 8's
"thumbnail logic" tasks, now that 89-91's Object Storage plumbing
(config, client, health check) is entirely done. Not started, per the
phase-control rule, awaiting explicit instruction the same as every
other task. Tasks 85-88 (Phase 7's Playwright E2E suite) also remain
not started and available whenever asked for (see "Note on phase
order" above).
