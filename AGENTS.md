# Stillroom — working notes for the next session

Read this first, then `Docs/build-log.md` for the chronological record.

## Where things are

| What | Value |
|---|---|
| Repo | `C:\Users\ACER\OneDrive\Desktop\AI` (still inside OneDrive; see gotchas) |
| Branch | `hardening/phase-0` (all work so far lives here) |
| Tags | `pre-hardening`, `phase-0-complete`, `phase-1-complete` |
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
make test             # backend pytest (70 tests)
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
- **Phase 2 partial**: stable `position` ordering is done; `list_stories` is a
  single aggregate query; the route monolith is split into `routes/stories.py`,
  `chapters.py`, `bible.py`, `continuity.py` with response models and matching
  services. Everything else in Phase 2 is untouched.
- Backend: 70 tests pass, ruff and pyright clean.
- Frontend: lint, `tsc --noEmit`, `next build`, and 19 vitest tests pass.
- CI workflow is committed but has never run on GitHub.

## Pick up here (in this order)

1. **P2-2 pagination + ETag** — `limit`/`cursor` on `/stories`, `/stories/{id}/bible`,
   chapter scan findings; `If-None-Match` on chapter GET.
2. **P2-3 batched continuity retrieval** — `services/continuity.py` still embeds
   each draft scene and runs one vector query per scene.
2. **P2-4 index migration** — `ix_scans_chapter_created`, `ix_findings_scan`,
   `ix_bible_story_status` (the others exist); `statement_timeout` per request.
3. **P2-6 durable worker** — `jobs` table, `SKIP LOCKED` claim query, `app/worker.py`;
   then P2-7 (remove `_index_semaphore`, `_continuity_locks`, in-process tasks) and
   switch indexing/Bible scans to enqueue.
4. **P2-8 request ids, `/ready`** — middleware + contextvar; `/health` exists,
   `/system/status` exists but `/ready` does not.
6. **Phase 3** — knowledge model (`entities`, `entity_aliases`, `entity_facts`,
   `entity_relationships`, `story_events`, `story_threads`, `entity_mentions`,
   `canon_exceptions`, `chapter_meta`, `scene_meta`, `ai_usage`) per the manual.
   Do not drop `story_bible_entries` in the same migration.

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
