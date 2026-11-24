# Build log

## Phase 0 baseline

- Started on branch `hardening/phase-0`, tag `pre-hardening`.
- Recorded baseline checks in `docs/baseline.md`.
- Native PostgreSQL 18 and pgvector files are installed; local authentication failed with existing app credentials.
- Existing remote database credentials were rejected, so remote schema and data could not be verified or backed up. No database changes were made.
- The frontend has a pnpm lockfile, so `npm ci` fails until a deliberate package-manager conversion.

## Phase 0 dead-code cleanup

- Removed unused legacy RAG models, routes, schemas, storage client, and unused dependencies.
- Updated Alembic's model imports to include the Editing models.
- `uv sync`, backend import, metadata check, `alembic heads`, and offline SQL generation passed. Live migration remains unverified because the configured database rejects authentication.
- Ignored personal scratch files were left untouched.
- Next: configure and verify native PostgreSQL, and recover remote data only after obtaining working access.

## Phase 0 local database

- Created native PostgreSQL 18 databases `stillroom` and `stillroom_test`; enabled
  `vector` and `pg_trgm` on both.
- `backend/.env` now points at `127.0.0.1:5432/stillroom`; the Supabase credentials
  are kept in `backend/.env.supabase-backup` (git-ignored).
- Ran `alembic upgrade head` against the empty local database.
- Dumped the live Supabase data with `pg_dump --data-only` to
  `backups/supabase-data.sql` and restored it with `psql -f`. Row counts match the
  source exactly (4 users, 1 story, 5 chapters, 3 revisions, 25 scene embeddings,
  45 bible entries, 6 scans, 18 findings, 1 folder, 1 AI settings row).
- Added `Docs/database.md`; rewrote `backend/.env.example` to match the variables
  the app actually reads.
- Next: fail-fast configuration and startup schema check.

## Phase 0 fail-fast configuration

- `app/config.py` now validates `JWT_SECRET` length/placeholder values, the
  encryption key length, provider base URLs, database fields, and
  `COOKIE_SECURE` in production. Validation failures print a readable
  `Configuration error:` block instead of a Pydantic traceback.
- Added `app/schema_check.py`; the FastAPI lifespan refuses to start when
  `alembic_version` is not at head.
- Removed the dead `SUPABASE_*` and `MinerU_API_KEY` keys from the environment and
  rewrote `.env.example` to document every variable the app reads.
- Verified: `JWT_SECRET=short uv run python -c "import app.app"` and
  `APP_ENV=production ...` both fail with readable messages; normal config imports.

## Phase 0 email normalization

- Migration `1e10de6c20dc` aborts if lowercasing would create duplicates, then
  lowercases addresses and adds the functional unique index `uq_users_email_lower`.
- `UserCreate`/`UserLogin` normalize with `normalize_email`; login and register
  compare case-insensitively.

## Phase 0 test foundation

- Added a `dev` dependency group (pytest, pytest-asyncio, httpx, ruff, pyright).
- `tests/conftest.py` builds the schema in `stillroom_test` via Alembic, truncates
  every application table between tests, and stubs indexing/provider background
  tasks so tests never call Ollama.
- 36 tests across auth, ownership, chapter conflicts, reorder, scene splitting, and
  quote verification.
- `uv run ruff check .` and `uv run pyright` are clean. Existing tab-indented and
  long-prompt modules are excluded from E501 rather than reformatted here.
- Fixed two real defects the tests found: reorder/delete serialized server-onupdate
  `updated_at` after commit (MissingGreenlet under asyncpg), and legacy `rooms`/`docs`
  ORM models with no schema had been left behind after the route cleanup.
- Added `pyrightconfig.json` and `[tool.pytest.ini_options]`.
- Next: CI, backups, and the task runner.

## Phase 0 CI, backups, tooling

- `.github/workflows/ci.yml`: backend job (ruff, pyright, Alembic, pytest on a
  `pgvector/pgvector:pg16` service) and frontend job (npm ci, lint, tsc, build).
- Converted the frontend from pnpm to npm: removed `pnpm-lock.yaml`, generated
  `package-lock.json`; `npm run lint`, `npx tsc --noEmit`, and `npm run build` pass.
- `scripts/backup.sh` and `scripts/restore.sh` read `backend/.env` and call
  `pg_dump`/`pg_restore` directly (no Docker). Documented in `Docs/backups.md`.
- Restore drill passed: backed up, inserted a throwaway story (count 2), restored
  (count back to 1) with the original data intact.
- Added a root `Makefile` (`install`, `dev-backend`, `dev-frontend`, `test`, `lint`,
  `typecheck`, `migrate`, `backup`) and `Docs/versions.md`.
- `uv.lock` and `package-lock.json` are the only lockfiles.

## Phase 1 save reliability

Backend:

- Migration `7103cb022fd3`: `deleted_at` on stories and chapters, a partial unique
  index on active chapter numbers, `last_client_save_id`, and snapshot metadata
  (`kind`, `content_hash`, `char_count`).
- `services/snapshots.py`: snapshot policy (always for checkpoints/restores; else
  60 s of editing or a 500-word change), never the same content twice, tiered
  retention (48 h all, hourly for 7 days, daily for 90 days, checkpoints forever),
  and `difflib`-based hunk diffs.
- `services/trash.py`: soft delete, restore, and a 30-day purge that now runs in the
  startup lifespan.
- `update_chapter` accepts `client_save_id` (idempotent retries) and returns
  `current_revision`, `current_title`, `current_content`, and `updated_at` in a 409
  body.
- New endpoints: `POST /stories/chapters/{id}/checkpoint`,
  `GET /stories/chapters/{id}/revisions/{a}/diff/{b}`, `/trash` (list, restore,
  permanent delete), and `/system/status`.
- Startup reconciliation resets chapters stuck in `indexing` and re-queues them.
- Fixed a pre-existing 500: reorder/delete serialized the server-onupdate
  `updated_at` after commit, which raised `MissingGreenlet` under asyncpg.

Frontend:

- `lib/draft-buffer.ts` (IndexedDB via `idb`) with `decideDraft` and
  `clearBufferIfSaved`; `lib/save-state.ts` state machine and retry policy.
- Studio writes every keystroke to IndexedDB within 250 ms, flushes on page hide,
  tab hide, unmount, and guarded navigation, and recovers a dirty draft when a
  chapter opens.
- Conflict dialog (Radix Dialog) with a line diff, "Keep mine", "Reload saved
  version", and "Merge by hand".
- `ConfirmProvider` (Radix AlertDialog) and `StoryNameDialog` replace every
  `window.confirm` and `window.prompt` in the studio and dashboard.
- Trash panel on the dashboard with restore and permanent delete.
- History dialog shows snapshot kind, supports checkpoints, and diffs two versions.

## Phase 1 verification

- 58 backend tests and 19 frontend unit tests pass; ruff, pyright, eslint, and
  `tsc --noEmit` are clean.
- `frontend/scripts/phase1-qa.mjs` drives a real Chromium against a production
  build. Passed 2026-11-24: no keystroke lost on navigation, checkpoint saved and
  listed, chapter trashed and restored from the dashboard, and a two-tab conflict
  produced the dialog where "Keep mine" preserved the local text.
- The DeepAI preview browser timed out on every snapshot in this environment, so
  the flow runs on standalone Playwright instead.
- Next: Phase 2 route split, query batching, stable positions, and the durable
  worker.

## Phase 2 (partial) stable chapter positions

- Migration `72e3aad68ab6`: `story_chapters.position DOUBLE PRECISION`, backfilled
  from `chapter_number`, indexed on `(story_id, position)`.
- `services/chapter_order.py`: `next_position` (+1024), `assign_positions` (one
  executemany), `renumber_display` (two bulk statements plus bulk updates of the
  denormalized `chapter_number` copies), and `rebalance_story`.
- Create/import/reorder/move/delete use positions. Reorder of 1,100 chapters is
  covered by a timing test and no longer issues one UPDATE per chapter or uses the
  negative-number dance.
- Fixed two bugs found by the new tests: moving a chapter between stories collided
  with the destination's unique display number, and `ChapterReorder` capped the
  list at 500 chapters (now 5,000).
- `list_stories` is a single aggregate query (the N+1 noted in P2-2).
- Not done yet: P2-1 route split/response models, P2-2 pagination and ETags,
  P2-3 batched continuity retrieval, P2-4 index/statement-timeout migration,
  P2-6 durable worker, P2-7 worker concurrency, P2-8 request ids and `/ready`,
  and all of Phase 3.
