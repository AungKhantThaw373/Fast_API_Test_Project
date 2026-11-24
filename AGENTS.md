# Stillroom — working notes for the next session

Read this first, then `Docs/build-log.md` for the chronological record.

## Where things are

| What | Value |
|---|---|
| Repo | `C:\Users\ACER\OneDrive\Desktop\AI` (still inside OneDrive; see gotchas) |
| Branch | `hardening/phase-0` (all work so far lives here) |
| Tags | `pre-hardening`, `phase-0-complete`, `phase-1-complete`, `phase-2-complete` |
| Backend | `backend/` — FastAPI + SQLAlchemy 2 async + Alembic + pgvector |
| Frontend | `frontend/` — Next 16, React 19, npm |
| Database | Native PostgreSQL 18 on `127.0.0.1:5432`, databases `stillroom` and `stillroom_test`, password `death373` (`backend/.env`) |
| Docs | `Docs/` (tracked; `Jupyter/`, `data/` are not) |

## Commands

```bash
# psql is not on PATH on this machine
export PATH="/c/Program Files/PostgreSQL/18/bin:$PATH"

cd backend  && uv sync && uv run alembic upgrade head
cd frontend && npm ci

make dev-backend      # uvicorn app.app:app --reload --port 8000
make dev-frontend     # next dev on :3000
make worker           # durable job worker (long AI work); run exactly one
make test             # backend pytest (85 tests)
make test-frontend    # vitest (19 tests)
make lint typecheck   # ruff + eslint, pyright + tsc
./scripts/backup.sh   # pg_dump, no Docker
```

## Current state (verified)

- **Phase 0 complete** (`Docs/phase-0-acceptance.md`): local DB is the source of
  truth, fail-fast config, email normalization, CI workflow, backups, Makefile.
- **Phase 1 complete** (`Docs/qa-phase-1.md`): IndexedDB draft buffer, save state
  machine, idempotent saves + conflict dialog, soft delete/trash, snapshots with
  retention and diffs, startup reconciliation, `/system/status`.
- **Phase 2 complete** (`Docs/perf.md`, `Docs/worker.md`): split routers with
  response models, cursor pagination + chapter ETags, one-query story list and
  continuity retrieval, scan index + statement timeouts, durable `jobs` worker
  with `SKIP LOCKED` (no in-process AI work), request ids, `/ready`, and all
  performance targets met. Server logs now carry `request_id=` and error bodies
  include it.
- Backend: 85 tests pass, ruff and pyright clean.
- Frontend: lint, `tsc --noEmit`, `next build`, and 19 vitest tests pass.
- CI workflow is committed but has never run on GitHub.

## Pick up here (in this order)

1. **Phase 3, P3-1** - knowledge model v2. Add `entities`, `entity_aliases`,
   `entity_facts`, `entity_relationships`, `story_events`, `story_threads`,
   `entity_mentions`, `canon_exceptions`, `chapter_meta`, `scene_meta`, `ai_usage`
   in one additive migration (do not drop `story_bible_entries`), plus models.
2. **P3-2** - backfill from `story_bible_entries` keeping the same UUIDs;
   `plot_thread` becomes `story_threads`. Make it idempotent.
3. **P3-3** - `normalize_name`, entity resolution, soft merge with dry run,
   zero-LLM mention extraction.
4. **P3-4..P3-7** - entities/facts/threads/events/inbox API with response models
   and ownership tests, compatibility serializer for the old `/bible` shape,
   continuity context built from facts, then the ten Phase 3 tests.

## Gotchas that cost time

- **`next dev` + Playwright**: the HMR websocket fails here and React never
  hydrates, so forms submit natively. Browser tests must run against
  `npm run build && npx next start` (see `Docs/qa-phase-1.md`).
- **The DeepAI preview browser** (`preview_*` tools) timed out on every snapshot in
  this environment; standalone Playwright works.
- **Alembic + asyncpg**: after `commit()`, `updated_at` (server `onupdate`) is
  expired. Serializing it raises `MissingGreenlet` — refresh or reload first.
- **`load_only(...)`** must include any column you touch later, or it lazy-loads
  outside the greenlet (this broke `get_story` when `deleted_at` was added).
- **Unique `(story_id, chapter_number)`** is a partial index over active rows;
  permutations must pass through temporary values (`chapter_order.renumber_display`
  does this in two bulk statements).
- **OneDrive** syncs `node_modules`, `.next`, `.venv`. Builds can be slow and file
  locks appear. Moving the repo to `C:\dev\stillroom` is still recommended.
- **`ACCESS_TOKEN_EXPIRE_MINUTES=30`** in `backend/.env` — sessions are short.
- **Supabase credentials** are preserved in `backend/.env.supabase-backup`
  (git-ignored). The live project is still reachable and was the dump source;
  `backups/supabase-data.sql` holds that data.
- Tests set `DBNAME=stillroom_test` in `tests/conftest.py` and stub background AI
  tasks; never call Ollama or a provider from a test.

## Conventions

- One task, one commit, verify before moving on (manual's rule).
- Do not rename API paths or change response shapes during a refactor task.
- New endpoints get a Pydantic response model and an ownership test.
- Migrations are additive; never edit one that has already run.
