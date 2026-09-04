# NATRA — SETUP

## Status

Phase 1 (Tasks 1–17) is complete. Backend and frontend scaffolds exist,
and the backend can connect to Oracle Autonomous Database as of Task 4
(not yet confirmed against a real instance locally — see
`CURRENT_STATUS.md`). Phase 2 (payment verification) has begun: Task 18
adds a Playwright browser-automation liveness check.

## Repository Layout

```
natra/
  backend/     FastAPI backend (Python)
  frontend/    React + TypeScript + Vite frontend
```

## Prerequisites

- Python 3.11+ and `pip`
- Node.js 18+ and `npm` (for Task 3 onward)
- An Oracle Autonomous Database instance (for Task 4 onward)
- Oracle Object Storage bucket + credentials (for later image upload tasks)
- A Playwright-supported OS/browser environment (for Task 18 onward,
  Phase 2 receipt verification) — see "Playwright Setup" below

## Environment Variables

None yet. Will be documented here (names only — never real values) as they
are introduced, e.g. database connection details, JWT secret, Object Storage
credentials. **Never commit a real `.env` file or real credentials to GitHub.**
An `.env.example` file should be added once environment variables exist.

## Local Development Commands

### Backend (FastAPI)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Then check it's running:

```bash
curl http://127.0.0.1:8000/health
# Expected: {"status":"ok","service":"natra-backend"}
```

**As of Task 39**, the backend now fails fast on startup if
`ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_DSN`, or `JWT_SECRET_KEY` is
missing from the environment — Uvicorn will refuse to start and print
a `StartupConfigError` naming which one(s), instead of starting and
only failing on the first request that needs one. Make sure
`backend/.env` (copied from `backend/.env.example`) is loaded before
running `uvicorn` (e.g. via `python-dotenv`, or export the variables
in your shell). `ADMIN_EMAIL`/`ADMIN_PASSWORD_HASH` are not required to
start — a missing one only logs a warning, and admin login will keep
returning its normal "Invalid email or password" response until both
are set.

**As of Task 40**, set `CORS_ALLOWED_ORIGINS` in `backend/.env` to the
frontend's dev origin (typically `http://localhost:5173`) so the
frontend (once it exists — see `CURRENT_STATUS.md`) can actually call
this API from a browser. Leaving it unset is not a startup error, but
means every cross-origin browser request is blocked — fine for
backend-only work (`curl`, this repo's own tests) but not for testing
against a real frontend.

### Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

Then open the local URL Vite prints (typically `http://localhost:5173`) and
confirm the page loads and shows "NATRA".

## Oracle Configuration

1. Provision an Oracle Autonomous Database instance (Always Free tier works)
   and download its client credentials wallet (a `.zip`), then unzip it
   somewhere local, e.g. `backend/wallet/` (already covered by `.gitignore`
   patterns for secrets — do not commit the wallet contents).
2. Copy `backend/.env.example` to `backend/.env` and fill in:
   - `ORACLE_USER` / `ORACLE_PASSWORD` — your DB user credentials
   - `ORACLE_DSN` — the TNS alias name from the wallet's `tnsnames.ora`
     (e.g. `mydb_high`)
   - `ORACLE_WALLET_DIR` — path to the unzipped wallet directory
   - `ORACLE_WALLET_PASSWORD` — only if the wallet itself is
     password-protected
3. With the backend running (see commands above), check:

```bash
curl http://127.0.0.1:8000/health/db
# Expected: {"service":"natra-backend","connected":true}
```

Never commit a real `.env` file or the wallet contents to GitHub.

## Admin Login (Task 14)

There is exactly one Master Admin identity. It is provisioned via
environment variables, not a database row, and there is no admin
self-registration endpoint.

1. Generate a password hash for your chosen admin password:

   ```bash
   cd backend
   python -c "from app.security import hash_password; print(hash_password('your-password-here'))"
   ```

2. In `backend/.env`, set:
   - `ADMIN_EMAIL` — plain text, e.g. `admin@natra.example`
   - `ADMIN_PASSWORD_HASH` — the hash string printed above (never the
     plain-text password)
   - `JWT_SECRET_KEY` — required for the token issued on login (same
     variable used for seller login)

3. With the backend running, check:

   ```bash
   curl -X POST http://127.0.0.1:8000/admin/login \
     -H "Content-Type: application/json" \
     -d '{"email": "admin@natra.example", "password": "your-password-here"}'
   # Expected: 200 with {"access_token": "...", "token_type": "bearer"}
   ```

## Deployment (Tasks 46-47)

Target: Oracle Cloud Free Tier Linux VM running Nginx + Uvicorn
(FastAPI) + a built React production bundle. Both halves — backend
process management (Task 46) and the frontend build's static-serving
integration (Task 47) — are covered below.

### Files

- `backend/.env.production.example` — the same environment variables
  as `backend/.env.example`, with production-appropriate guidance
  (fresh `JWT_SECRET_KEY`, the real domain for `CORS_ALLOWED_ORIGINS`,
  etc.). Copy it to `backend/.env.production` **on the VM itself** and
  fill in real values there — never commit `.env.production` (only the
  `.example` file is tracked).
- `deploy/systemd/natra-backend.service` — a systemd unit that runs
  the backend under Uvicorn as a long-lived service, restarting it on
  failure. See the file's own header comment before installing it —
  in particular, it must never be run with more than one worker
  process (Task 44's rate limiter is in-memory and single-process by
  design).
- `deploy/nginx/natra.conf` — an Nginx server block that proxies the
  backend's existing path prefixes (`/health`, `/sellers/`,
  `/products`, `/payment-info`, `/receipts/`, `/admin/`) to Uvicorn,
  and serves the built frontend (`frontend/dist/`) for everything
  else, falling back to `index.html` for client-side routing. See the
  file's own header comment for why this split needed no backend code
  change.

### One-time VM setup (outline)

1. Clone the repo to `/opt/natra` on the VM (adjust the paths in both
   deploy files if a different location is used).
2. Backend: `cd /opt/natra/backend && python3 -m venv .venv && source
   .venv/bin/activate && pip install -r requirements.txt && python -m
   playwright install --with-deps chromium` (see "Playwright Setup"
   below for why the second install step is separate).
3. Frontend: `cd /opt/natra/frontend && npm install && npm run build`
   — produces `frontend/dist/`, which `deploy/nginx/natra.conf`
   expects at `/opt/natra/frontend/dist`. Re-run this after any
   frontend change and reload; Nginx serves the static files directly
   and does not rebuild them itself.
4. Copy `backend/.env.production.example` to
   `backend/.env.production` and fill in real production values —
   never the same `JWT_SECRET_KEY` or admin password used locally.
5. `sudo useradd --system --no-create-home natra` (the dedicated,
   unprivileged user `deploy/systemd/natra-backend.service` runs as),
   then make sure it can read `/opt/natra/backend` and the Oracle
   wallet directory. The frontend's built files only need to be
   world-readable by Nginx, not owned by this user.
6. Install and enable the systemd service and Nginx config — see each
   file's own header comment for the exact commands.
7. `curl http://<vm-ip>/health` should return the same
   `{"status":"ok",...}` this file's local dev section shows, now
   served through Nginx instead of directly hitting Uvicorn.
   `curl http://<vm-ip>/` should return the built `index.html`.

TLS (via `certbot --nginx`, see `deploy/nginx/natra.conf`'s own note)
is intentionally left for later — a real domain pointed at the VM is
a prerequisite.

## Monitoring (Task 48)

**Logging.** The backend logs structured JSON, one object per line, to
stdout — configured by `backend/app/logging_config.py` and controlled
by the `LOG_LEVEL` env var (default `INFO`; avoid `DEBUG` in
production). Under the systemd unit from Task 46, stdout is captured
by the journal, so `journalctl -u natra-backend -f` shows live JSON
log lines, and `journalctl -u natra-backend --since "1 hour ago"` (or
any journalctl filter) works normally against them. Every HTTP request
produces one line from the `natra.request` logger (method, path,
status, duration); uncaught exceptions still produce the existing
`natra` logger error line from Task 43's handler, now also JSON with
the traceback as a string field.

**Health-endpoint polling frequency.** The three `/health*` endpoints
are not equally cheap, so an external monitor should not poll all
three at the same interval:

| Endpoint | Cost | Recommended external polling |
|---|---|---|
| `GET /health` | No I/O | Frequent (e.g. every 10-30s) — fine for a load balancer or uptime monitor |
| `GET /health/db` | Opens a real, unpooled Oracle connection + query every call | Infrequent (e.g. every 1-5 min), or deploy-time only |
| `GET /health/playwright` | Launches a full headless Chromium process every call | Rare (e.g. every 15-30 min at most), or deploy-time only — the most expensive of the three |

`/health` is the one to point a standard uptime/liveness checker at.
`/health/db` and `/health/playwright` exist for deeper diagnosis (is
the DB reachable, is the browser automation installed correctly) and
were designed as Tasks 4/18's own liveness checks for those
subsystems — not as something to hammer continuously from outside.

## Backup Strategy (Task 49)

Documentation only — no code or schema change for this task. Covers what
is backed up automatically, what still needs a manual/periodic action,
and how to restore.

**Database (Oracle Autonomous Database) — automatic, no setup needed.**
Autonomous DB takes automatic incremental backups continuously and a
full backup roughly weekly, retained for **60 days** by default, at no
extra cost and with no configuration required from this project —
nothing in `db.py` or the schema needs to change for this to be active.
Within that 60-day window, Oracle supports **point-in-time recovery**
(restore to any timestamp, not just to a backup boundary) from the
Autonomous DB console or the `oci db` CLI/API.

- **Restore mechanics:** a restore can either replace the existing
  instance in place, or (preferred here) **clone to a new Autonomous DB
  instance at a chosen timestamp**, leaving the live instance untouched.
  Cloning to a new instance lets the restored data be inspected/tested
  (e.g. point a local `.env` at the clone's wallet) before deciding
  whether to cut production over to it — safer than an in-place restore,
  which cannot be undone.
- **Longer retention:** if a backup needs to be kept longer than 60 days
  (e.g. before a risky migration, or an end-of-month archive), Oracle
  supports **manual on-demand long-term backups** with retention
  configurable up to 360 days. This is a deliberate action (console/CLI),
  not automatic — worth doing before any destructive schema change.
- **Wallet backup:** the Autonomous DB wallet (`ORACLE_WALLET_DIR`,
  containing `tnsnames.ora`/`cwallet.sso`) is what a restored/cloned
  instance's *new* wallet would replace — the current wallet itself isn't
  something Oracle backs up as data, so a copy of it should be kept
  somewhere secure outside the VM and outside Git (same rule as
  `backend/.env.production` — never committed).

**Object Storage (thumbnails, seller profile pictures) — not covered by
the above.** Autonomous DB backups only cover the database; the images
referenced by key from `products`/`sellers` rows live in Oracle Object
Storage separately and are **not currently versioned or replicated** by
anything this project has configured. Practical implication: restoring
the database to an earlier point can leave rows referencing an image key
that a since-deleted/replaced object no longer matches. Two options exist
if this gap needs closing later (neither implemented now — flagging only,
per the "small task" rule): enable Object Storage bucket versioning, or
a periodic bucket-to-bucket copy job. Out of scope for Task 49 itself.

**Code and configuration.** Already covered — the application code and
schema are in Git (`backend/db/schema.sql` is the source of truth for
schema, applied via `init_db.py`); secrets/credentials are deliberately
*not* in Git (`.env.production`, the wallet) and must be backed up
separately by whoever holds them, per the wallet note above.

**What this project does not yet have:** an automated restore-test
schedule, or an automated Object Storage backup job. Both are reasonable
future hardening but are new work, not part of "document the backup
strategy" — noted here rather than silently expanding this task's scope.

## Playwright Setup (Task 18)

Phase 2 (payment receipt verification) uses Playwright for browser
automation. Installing the `playwright` Python package (already in
`requirements.txt`) is not enough by itself — it also needs an actual
browser binary downloaded once, separately:

```bash
cd backend
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

On some Linux distributions, Playwright also needs a few system libraries
for Chromium to run; if `playwright install chromium` reports missing
dependencies, use:

```bash
python -m playwright install --with-deps chromium
```

With the backend running, confirm the browser launches successfully:

```bash
curl http://127.0.0.1:8000/health/playwright
# Expected: {"service":"natra-backend","browser_ready":true}
```

If this instead returns `"browser_ready": false` with an error mentioning
a missing executable, the `playwright install chromium` step above was
not run (or didn't complete) in this environment.

