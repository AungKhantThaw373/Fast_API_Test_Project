# Stillroom — working notes for the next session

Read this first, then `Docs/build-log.md` for the chronological record.

## Where things are

| What | Value |
|---|---|
| Repo | `C:\Users\ACER\OneDrive\Desktop\AI` (still inside OneDrive; see gotchas) |
| Branch | `hardening/phase-0` (all work so far lives here) |
| Tags | `pre-hardening`, `phase-0-complete` … `phase-7-complete` |
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
make test             # backend pytest (190 tests)
make test-frontend    # vitest (47 tests)
make qa-phase6        # 8 Playwright local-AI checks
make qa-phase7        # 8 Playwright writing/export/accessibility suites (85 checks)
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
- **Phase 4 complete** (`Docs/phase-4-acceptance.md`, runbook `Docs/qa-phase-4.md`):
  TanStack Query data layer with generated OpenAPI types, wiki list/detail with
  virtualised rows and provenance deep links, capture + zero-token name
  candidates, a unified review inbox (facts, merge proposals, findings) with
  batch decisions and previewable auto-accept rules, arcs (rail grouping, wiki
  filter, arc summary page), the collapsible/resizable three-tab chapter desk,
  a `Ctrl/Cmd+K` command palette, localStorage saved views, and an accessibility
  pass (12 px floor, contrast, focus traps, `aria-live`).
  24/24 Playwright checks in `frontend/scripts/wiki-qa.mjs`; perf on 1,000
  entities via `backend/scripts/seed_wiki.py` + `frontend/scripts/wiki-perf.mjs`.
- **Phase 3 complete** (`Docs/phase-3-acceptance.md`): knowledge model v2
  (`entities`, `entity_aliases`, `entity_facts`, `entity_relationships`,
  `story_events`, `story_threads`, `entity_mentions`, `canon_exceptions`,
  `chapter_meta`, `scene_meta`, `ai_usage`, `entity_merges`), an idempotent
  backfill from `story_bible_entries` that keeps UUIDs, zero-LLM mention
  extraction, merge with dry run + audit + unmerge, the wiki/inbox/exceptions
  API, canon notes in the continuity prompt, and a compatibility `/bible` view
  that also routes the old UI's writes to entities.
- **Phase 5 complete** (`Docs/phase-5-acceptance.md`): sentence-aware chunks,
  hybrid vector/lexical/name retrieval, entity-first context, an evaluation
  harness, the embedding bake-off, and find-in-story. The end-to-end p95 target
  at 10k chunks stays open and is documented rather than hidden.
- **Phase 6 complete** (`Docs/phase-6-acceptance.md`): Ollama structured output
  with no cloud key, incremental scene extraction, deterministic continuity
  rules, per-scene evidence, durable scan jobs with progress/cancel, an AI usage
  ledger and monthly budget, and cited ask-your-story. 178 backend tests, 31
  frontend tests, and 8 Playwright checks in `frontend/scripts/phase6-qa.mjs`.
- **Phase 7 complete** (`Docs/phase-7-acceptance.md`): CodeMirror 6 with inline
  canon marks and findings, command-palette actions and recents, a read-only
  style/line-edit panel, cited chapter and arc recaps, the four-column thread
  board with keyboard drag and required payoff, Markdown/DOCX/EPUB/PDF export
  with a wiki appendix, JSON backup/restore, and the accessibility/responsive
  pass. 190 backend tests, 47 frontend tests, and 85 Playwright checks in eight
  suites via `frontend/scripts/phase7-qa.mjs`.
- Backend: 190 tests pass, ruff and pyright clean.
- Frontend: lint, `tsc --noEmit`, `next build`, and 47 vitest tests pass.
- CI workflow is committed but has never run on GitHub.

## Pick up here (in this order)

1. **Next manual phase** - Phase 7 ends at `phase-7-complete`. Read
   `Docs/phase-7-acceptance.md` for what was deliberately left out before
   extending the writing surface.
2. **Entity-scoped exceptions** - findings carry quotes and rule/evidence ids,
   but only pattern exceptions can suppress them. Once findings know the entity
   and predicate, `canon_exceptions.matches` should also honour those scopes.
3. **Legacy `story_bible_entries`** - extraction now proposes `entity_facts`, but
   the compatibility reader remains until nothing writes the old table.
4. **Retrieval p95** - the Phase 5 open target: end-to-end p95 at 10k chunks is
   437 ms against a 300 ms goal, mostly query embedding plus exact scan. See
   `Docs/retrieval.md` before changing indexes.

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
- **PDF page numbers need Chrome margin boxes.** `app/services/export.py` uses
  `@page { @bottom-center { content: counter(page) } }` and
  `--no-pdf-header-footer`. Current Chrome/Edge print the number; older engines
  produce a valid PDF without it.
- **Two uvicorn processes can fight over :8000** on this machine (one on
  `0.0.0.0`, one on `127.0.0.1`). After restarting, check
  `netstat -ano | grep ":8000" | grep LISTENING` for more than one PID; the
  stale socket from a killed parent can linger and answer with old code.
- **`uv run uvicorn` does not reload** in the way `make dev-backend` does when
  started with `nohup`; restart it after backend changes or the UI will 404/500
  on new routes.
- **Wiki QA must run against a build** (`npm run build && npx next start`).
  `node scripts/wiki-qa.mjs` assumes both servers are up and the API has the
  latest code.
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
