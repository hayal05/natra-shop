# NATRA

Multi-seller digital products marketplace.

This repository is developed incrementally, one small task at a time, following
the rules in `CLAUDE_MASTER_PROMPT.md`.

## Project Memory Files (read these first, in this order)

1. `CLAUDE_MASTER_PROMPT.md` — the full master development prompt (rules, stack, phases).
2. `PROJECT_ROADMAP.md` — the phase-by-phase roadmap.
3. `CURRENT_STATUS.md` — what has been built so far and the exact next task.
4. `ARCHITECTURE.md` — current architecture and technical decisions.
5. `DATABASE_SCHEMA.md` — current database tables/fields.
6. `SETUP.md` — local setup, environment variables, run commands.

## Structure

```
natra/
  backend/     FastAPI backend (Python)
  frontend/    React + TypeScript + Vite frontend
  deploy/      Production deployment configs (systemd, Nginx) — Task 46
```

## Status

Project structure only. No backend or frontend code has been written yet.
See `CURRENT_STATUS.md` for the next task.
