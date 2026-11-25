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

## Handoff

Added a root `AGENTS.md` with the environment, commands, verified state, the
ordered list of remaining Phase 2/3 tasks, and the gotchas that cost time
(dev-server hydration, `MissingGreenlet` after commit, partial unique index
permutations, OneDrive).

## Phase 2 — P2-1 route split and response models

- `app/routes/story_routes.py` (1,256 lines) is gone. Four resource routers now
  own the same URLs: `routes/stories.py` (103), `routes/chapters.py` (254),
  `routes/bible.py` (135), `routes/continuity.py` (113).
- Business logic and DB access moved into `services/stories.py`,
  `services/chapters.py`, and `services/bible.py`; the scan orchestration
  (readiness checks, per-chapter lock, cache re-check, finding carry-over) moved
  into `services/continuity.py`. No route file exceeds 300 lines.
- `app/schemas/{stories,chapters,bible,continuity}.py` now hold request *and*
  response models. Every endpoint declares a `response_model`; the 409 conflict
  path still returns its hand-built body so the dialog payload is unchanged.
- Verified: every path and method in `/openapi.json` is identical to the old
  router; `detail.chapters[]` still omits `content`; timestamps now serialize as
  RFC 3339 `Z` (pydantic) instead of `+00:00` (`isoformat`), which `new Date()`
  accepts.
- `tests/conftest.py` now stubs the AI tasks on `app.services.indexing` instead
  of the deleted route module, so both routers and services see the stub.
- 64 tests pass, ruff and pyright clean.

## Phase 2 — P2-2 pagination, ETags, story-list query test

- `services/pagination.py`: opaque base64url keyset cursors (`encode_cursor`,
  `decode_cursor`, `keyset_predicate`), with 400 on a malformed cursor. Cursors
  carry the actual ordering values, so a page boundary cannot skip or repeat a row.
- `GET /stories?limit=&cursor=` — `(updated_at DESC, id DESC)`, returns
  `next_cursor`. `GET /stories/{id}/bible?limit=&cursor=` pages in its existing
  display order `(status, category, name, id)`. `GET /stories/chapters/{id}/scan`
  pages findings by `(draft_line, id)`.
- `GET /stories/chapters/{id}` now returns `ETag: "<revision>-<saved-at>"` and
  `304` for a matching `If-None-Match` (weak or `*` accepted). The route returns a
  `JSONResponse` because this FastAPI version does not copy headers from an
  injected `Response`.
- Story detail caps `chapters[]` at 2,000 and reports `chapters_truncated`;
  `chapter_count`/`word_count` still describe the whole story.
- `frontend/lib/api.ts` follows `next_cursor` for stories, the bible list, and scan
  findings, so the existing UI still sees complete lists.
- New `tests/test_pagination.py` (6 tests): stable multi-page walks, bad cursor,
  bible page order, chapter-list cap, ETag round trip, and a SQL event listener
  asserting `GET /stories` runs exactly one aggregate query.
- 70 backend tests pass; ruff, pyright, eslint, tsc, and 19 vitest tests clean.

## Phase 2 — P2-3 batched continuity retrieval

- `services/continuity.py` no longer embeds-then-queries once per scene. The draft
  scenes are embedded in one call, the vectors travel as one JSON parameter, and
  `retrieve_evidence()` runs a single statement: a CTE over
  `jsonb_array_elements_text(...)::vector` with a `JOIN LATERAL (... ORDER BY
  embedding <=> q.vector LIMIT :top_k)` per scene, so pgvector can still use the
  HNSW index instead of sorting the whole story per query vector.
- Distances are deduplicated per evidence id in Python, sorted ascending, and
  capped at 24 rows, which are loaded in one `WHERE id IN (...)`.
- Before: N vector round trips for N scenes. After: 3 statements (vector search,
  evidence load, story settings), asserted by a SQL event-listener test in
  `tests/test_continuity_retrieval.py`.
- 72 backend tests pass; ruff and pyright clean.

## Phase 2 — P2-4 indexes and statement timeouts

- Migration `5c1f0b7a2d31` adds `ix_scans_chapter_created` on
  `continuity_scans (chapter_id, created_at)` (Postgres scans it backwards for the
  DESC latest-scan lookup) and runs `ANALYZE` on the four hot tables. The other
  indexes the manual lists already existed; `ix_findings_scan` would duplicate
  `ix_continuity_findings_scan_id`, so it was not created.
- `app/db.py` sets `statement_timeout = 15s` per connection via
  `connect_args.server_settings`, which — unlike `SET LOCAL` — survives `COMMIT`
  and therefore every request that commits mid-flight.
- `ALTER DATABASE stillroom/stillroom_test SET log_min_duration_statement='200ms'`
  applied locally and documented in `Docs/database.md`, together with how to
  verify the timeout from the app.

## Phase 2 — P2-6 / P2-7 durable worker, concurrency moved out of the API

- Migration `8f3b6d2e5a17` adds `jobs` (status, attempts, `run_at`, lock columns,
  `progress`, `last_error`, `dedupe_key`, `owner_id`) and `worker_heartbeats`.
  Partial unique index `uq_jobs_active_dedupe` allows one active job per
  `(type, dedupe_key)`; claim order is `(status, run_at)`.
- `app/services/jobs.py`: `enqueue` (upsert that also debounces `run_at`),
  `claim_next` (`UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1)`),
  `record_success`, `record_failure` (5s/15s/45s backoff, then `dead`),
  `requeue_superseded`, `recover_stuck` (15-minute lock), `heartbeat`,
  `worker_is_alive`, `counts_by_status`, `owned_job`.
- `app/worker.py`: one worker, concurrency 1, Postgres-backed queue, signal
  handling that finishes the job in hand, heartbeat every 15 s, crash recovery on
  startup, and a `--once` mode that drains due jobs and exits (used by tests).
  `STATEMENT_TIMEOUT_MS=300000` is set before `app.db` is imported.
- `indexing.reindex_chapter` / `extract_story_bible` now return
  `done|superseded|skipped` and re-raise real failures so the queue retries with
  backoff. A mid-run edit leaves the chapter `pending` and requeues instead of
  stranding it in `indexing`.
- Deleted the in-process plumbing the manual lists for P2-7: `_index_semaphore`,
  `_chapter_jobs`, `_bible_jobs`, `_bible_scan_locks`, `schedule_chapter_reindex`,
  `schedule_bible_extraction`, `stop_index_jobs`. The API no longer starts AI
  work; chapter create/save/restore/retry and Bible range scans enqueue rows.
- `GET /jobs/{id}` (owner only, 404 otherwise) and `/system/status` now reports
  real `queued_jobs`/`running_jobs`/`dead_jobs` and a heartbeat-based `worker`.
- `make worker` / `make worker-once`; `Docs/worker.md` documents lifecycle,
  recovery, inspection, and why one worker is correct.
- New `tests/test_jobs.py` (13 tests): dedupe while queued and while running,
  claim accounting, two workers claiming different rows, retry-then-dead,
  superseded requeue, stuck-job recovery, heartbeat, save-enqueues-one-job,
  job ownership, and `run_worker(once=True)` indexing a real chapter.
- Smoke-tested end to end against Ollama: enqueued reindex → worker → chapter
  `indexed`, job `succeeded`.
- 85 backend tests pass; ruff, pyright, eslint, tsc clean.

## Phase 2 — P2-8 request ids and readiness

- `app/middleware.py`: `RequestContextMiddleware` assigns `X-Request-ID` (or keeps
  an incoming one), stores it in a `ContextVar`, echoes it on the response, and
  logs one line per request with method, path, status, and duration. A logging
  filter adds `request_id=` to every `stillroom.*` line, worker lines included
  (`request_id=-`).
- Error bodies now carry the id: handlers for `HTTPException`,
  `RequestValidationError`, and unhandled exceptions all include `request_id` and
  keep the existing `detail` shape.
- `app/services/health.py` centralises the dependency checks; `routes/health.py`
  exposes `/health` (no I/O at all, asserted by a test) and `/ready` (database,
  pgvector, schema head, Ollama, fresh worker heartbeat). `/ready` answers 503
  with a per-dependency report when anything is missing.
- `routes/system_routes.py` reuses the same checks.
- New `tests/test_readiness.py` (6 tests): generated and preserved request ids,
  ids in error and validation bodies, `/ready` transitioning 503 -> 200 after a
  worker heartbeat, and `/health` issuing zero SQL statements.
- 91 backend tests pass; ruff and pyright clean.

## Phase 2 — P2-9 performance budget

- `backend/scripts/perf.py` measures the manual's targets through the real ASGI
  app on `stillroom_test` with synthetic vectors and cleans up after itself.
- `Docs/perf.md` records: chapter open 6.4 ms p95, chapter save 28.9 ms p95, story
  list 4.4 ms p95, retrieval at 10k chunks 20.3 ms p95, 2 DB statements per
  retrieval, 1,100-chapter reorder 248 ms. All targets met; `EXPLAIN` confirms the
  HNSW index is used.
- Fixed while measuring: reorder/import/delete refreshed response rows one query
  per chapter; they now reload in a single `WHERE id IN (...)`.
- First attempt produced a 7.8 s retrieval p95 because autovacuum had not analyzed
  the bulk-loaded table; the script now vacuums and warms up first, and
  `Docs/perf.md` explains the trap.
- 91 backend tests pass; ruff, pyright, eslint, tsc, and 19 vitest tests clean.

## Phase 3 - P3-1 schema, P3-2 backfill, P3-3 resolution

- Migration `3a9c7d1f6b42` (additive) creates `entities`, `entity_aliases`,
  `entity_facts`, `entity_relationships`, `story_events`, `story_threads`,
  `entity_mentions`, `canon_exceptions`, `chapter_meta`, `scene_meta`, `ai_usage`,
  with the partial unique index on active `(story_id, entity_type, canonical_name)`,
  a soft `merged_into_id`, pg_trgm plus GIN trigram indexes on names and aliases,
  and `ANALYZE` on the hot tables. `story_bible_entries` is untouched.
- `app/models/wiki_models.py` holds the models with typed `Mapped` columns,
  `UUID[]` columns for participants/characters/links, and JSONB `context`.
- `app/services/entities.py`: `normalize_name` (NFKC, casefold, punctuation,
  articles, honorifics), `find_candidates` (exact alias first, then
  `similarity()` above 0.55, never auto-merging), `create_entity`, `add_alias`,
  `resolve_entity` (follows merge chains), `merge_entities` with dry-run counts,
  soft merge (`status='merged'`, `merged_into_id`), alias movement, and array
  de-duplication for threads/events/scene meta, plus `extract_mentions`
  (regex, longest alias wins, word boundaries, stoplist, zero LLM calls).
- `app/backfill/bible.py` (`python -m app.backfill.bible [--mentions] [--story]`):
  same UUIDs for entities, `story_bible_entries.category` mapped to
  `entities.entity_type`, `plot_thread` rows become `story_threads`, summaries
  become `summary` facts with located line numbers, statuses map
  suggested->proposed / dismissed->rejected, and a second run reports only skips.
- Ran it against the live `stillroom` database: 36 entities (all ids preserved),
  36 aliases, 36 facts, 9 threads, 251 mentions; second run changed nothing.
- Two fixes found by the tests: an alias whose normalization strips to nothing
  ("the captain") is still stored and still matches mentions, and duplicate
  mentions of one entity on one line collapse to a single row.
- New `tests/test_entities.py` (8 tests): normalization, quote line location,
  exact-vs-fuzzy candidates, mention ranges, dry-run merge, merge guards,
  merged-id resolution, and backfill idempotency with preserved ids.
- 99 backend tests pass; ruff and pyright clean.

## Phase 3 - P3-4 wiki API, P3-5 compat writes, P3-6 canon context, P3-7 checks

- `app/schemas/wiki.py` and two routers: `routes/entities.py` (entity CRUD,
  aliases, merge/unmerge, appearances, search, facts and decisions including
  accept-supersedes-previous, relationships) and `routes/wiki.py` (threads,
  events, inbox, canon exceptions). Every endpoint has a response model; every
  one checks story ownership, so another user's id is a 404.
- `routes/bible.py` now serves the compatibility view and routes old-shaped
  writes to entities: decision moves the summary fact, edit updates name and
  summary, delete archives, plot-thread toggle updates the thread.
- `app/services/facts.py` requires the chapter on every fact, verifies AI quotes
  against chapter text, and locates line numbers server-side. Accepting a value
  supersedes the previous accepted one and records `supersedes_id`.
- `app/services/inbox.py` merges proposed facts and open findings into one
  ordered list with source, actions, and `why_held` ("Already recorded as
  'grey'.").
- `app/services/knowledge_context.py` builds `CANON NOTES` for continuity from
  accepted facts about entities named in the draft, their relationships, and
  open threads - regex only, no tokens. `app/services/canon_exceptions.py`
  suppresses findings whose quotes or explanation match a recorded exception.
- `entity_merges` (migration `0b5e2c7d9a64`) records every moved id; `undo_merge`
  reverses a merge from that audit, including aliases that were dropped at merge
  time and array memberships in threads, events, and scene meta.
- Bug found by the new tests: `RequestValidationError` handlers put validator
  exceptions in `ctx`, which is not JSON serializable, so any `model_validator`
  failure returned 500. The handler now returns type/loc/msg only.
- Also: aliases whose normalization strips to nothing ("the captain") are kept
  and matched; duplicates of the same entity on one line collapse to one mention;
  archived entities are hidden from lists and from the Bible view.
- `Tests: tests/test_entities.py` (9), `tests/test_wiki_api.py` (15). 115 backend
  tests; ruff, pyright, frontend lint, tsc, build, and 19 vitest tests pass.
- `Docs/phase-3-acceptance.md` maps each manual acceptance line to its test.

## Phase 4 — wiki UX

### P4-1 — Frontend data layer

- Installed TanStack Query/Virtual, Radix primitives, `cmdk`, `sonner`,
  `react-hook-form`, `zod`, `diff`; no UI kit. `lib/query-client.ts` holds one
  client (30 s stale, 5 min gc, retry 1 for queries and 0 for mutations) with a
  one-shot 401 redirect; `app/providers.tsx` wraps the app.
- `lib/query-keys.ts` is the single key factory, including the `entityList`
  prefix used to invalidate every filtered list at once.
- `lib/api-types.ts` is generated from `/openapi.json` by `npm run gen:api`;
  the hand-written wrappers in `lib/api.ts` keep their ergonomics.
- `Docs/frontend-data.md` documents the keys, the invalidation table, the
  optimistic-update policy (only decisions and deletes), and why the manuscript
  editor stays outside the cache.

### P4-2/P4-3 — Wiki list, entity detail, provenance

- `components/wiki/` gained `wiki-shell`, `entity-list` (virtualised past 100
  rows, `j`/`k`/`Enter`), `entity-detail`, `fact-section`, `fact-dialog`,
  `merge-dialog`, `provenance-chip`, and `wiki-filters` (URL state so a filtered
  view survives a refresh).
- Provenance chips link to `/stories/{id}?chapter=…&line=…`; the studio reads
  the search params and selects the cited line.

### P4-4 — Capture and name candidates

- Backend `app/services/name_candidates.py` finds repeated capitalised words that
  are not aliases yet — zero tokens, refuses common words, and accepts a
  candidate straight into an entity + alias + mention + appearance range.
- Studio: a selection toolbar opens `capture-dialog` (entry / fact / thread) with
  the quote and line prefilled; the desk shows the candidate list.

### P4-5 — Review inbox

- `app/services/inbox.py` now returns three kinds behind one envelope
  (`fact`, `merge`, `finding`) with counts, `why_held`, source, and actions.
  Every pending item explains itself even when there is no conflict.
- `POST /stories/{id}/inbox/decide` decides many ids in one transaction;
  `GET/PUT /inbox/rules`, `GET /inbox/rules/preview`, `POST /inbox/auto-accept`
  implement the rules (quote required, confidence floor, existing entity,
  conflict blocking, per-chapter cap) and a dry run that counts what they would
  do before anything is accepted.
- `MergeProposal` + `AutoAcceptRules` (migration `6d1f4b8c2e09`): near-duplicate
  entity pairs are proposed from one self-join `similarity()` query, dismissed
  opinions are remembered, and applying one runs the audited merge.
- `components/wiki/inbox-page.tsx`: kind tabs with counts, chapter/entry/
  confidence filters, select-all, batch accept/reject, `j`/`k`/`a`/`x`/`e`, and
  an auto-accept panel whose "Apply now" is a separate step from saving rules.

### P4-6 — Arcs, saved views, layout, accessibility

- `arcs` table plus `story_chapters.arc_id` (migration `7c2e5a9d4b31`); the
  migration gives every story with chapters a default "Act one" arc. Endpoints
  list, create, rename/delete, and assign chapters; `/stories/{id}/entities`
  accepts `arc_id` and matches either the appearance range **or** a fact recorded
  in an arc chapter, so the filter works before mention extraction exists.
- `components/studio/chapter-rail.tsx` groups chapters by collapsible arc
  headers and assigns each chapter from its own line; `components/wiki/arc-page.tsx`
  is the arc summary (chapters, open threads, entities, editable summary).
- The studio desk is now a collapsible, resizable context panel
  (`Cmd/Ctrl+.`, drag handle, width remembered) with three tabs — Notes,
  Findings, Mentions. AI provider settings live on `/settings`; the story-level
  toggles stayed in the Notes tab, and `Cmd/Ctrl+Shift+W` opens the wiki.
- `components/command-palette.tsx` (`cmdk`, `Cmd/Ctrl+K`) jumps to chapters and
  entries, starts a character/place/entry/thread, opens the inbox or settings,
  and toggles quiet view.
- `components/wiki/saved-views.tsx` keeps named filter sets and three presets in
  localStorage — no table yet, per the manual.
- Accessibility pass: no UI text below 12 px, muted text darkened to pass
  contrast (#6b6f66 family), Radix dialogs trap and restore focus, `aria-live`
  on save state and result counts, reduced-motion rules kept.

### P4-7 — Verification

- `frontend/scripts/wiki-qa.mjs` runs 24 Playwright checks covering the eight
  required flows plus arcs, threads, the inbox keyboard path, and the palette.
- `backend/scripts/seed_wiki.py` + `frontend/scripts/wiki-perf.mjs` measure the
  manual's performance targets on 1,000 entities: search 17 ms, list first paint
  430 ms, detail API 13 ms, detail render 173 ms, layout shift 21/1000.
- 129 backend tests, 31 frontend tests; ruff, pyright, eslint, tsc, and
  `next build` pass. `Docs/qa-phase-4.md` is the runbook;
  `Docs/phase-4-acceptance.md` maps each acceptance line to its evidence.
## Phase 5 — retrieval v2

- `story_chunks` (migration `90bb47e` history), sentence-aware chunking, and a
  `tsvector` + trigram index pair; hybrid vector, lexical, and name retrieval
  with reciprocal-rank fusion (`bc22a5c`, `b37f1a4`).
- `build_entity_context` reads accepted facts and relationships by entity id and
  trims to a token budget instead of embedding a whole chapter.
- `app/eval/run.py` measures recall/MRR/nDCG and the 30-case continuity set;
  baseline and hybrid results live in `Docs/eval/`.
- Find-in-story UI with filters, score breakdown, and line deep links
  (`60be11c`); embedding bake-off and the Nomic decision in
  `Docs/embedding-decision.md` (`aa032a0`).
- Acceptance status and the one open target (end-to-end p95 at 10k chunks) are
  recorded in `Docs/phase-5-acceptance.md`.

## Phase 6 — local-only AI

### P6-1 — Ollama and local model settings

- AI settings accept `provider=ollama` with no API key, a configurable base URL
  (default `http://127.0.0.1:11434`), and a model name. Local calls never
  require a cloud key; cloud providers remain optional (`ead4a3a`).
- `_ollama_structured` uses `/api/chat` with a JSON schema, validates the result
  again with `jsonschema`, retries malformed JSON once, and records usage.
- Provider/transport failures are readable 5xx errors instead of raw tracebacks:
  timeout → 504, unreachable Ollama/provider → 503.

### P6-2 — Incremental extraction

- Bible extraction is scene-level and hashes each scene; a chapter rescan only
  sends changed scenes (`eb68c12`). A no-op rescan makes zero model calls.

### P6-3 — Deterministic first, then per-scene continuity

- `app/services/deterministic.py` checks accepted facts for ages, eye/hair
  colour, titles, and POV. It is deliberately quiet: a complete sentence must
  name a canon entity and clearly contradict an accepted value, and near misses
  stay silent.
- `scan_chapter` runs the rules first, retrieves evidence once, then reviews each
  scene in its own prompt with the closest earlier evidence. A chapter with no
  earlier evidence returns only the free rules. Findings carry
  `source=deterministic|llm`, the rule id, scene index, and evidence id;
  deterministic findings have no earlier quote.
- Scans store `prompt_version=continuity-v2`, model, schema version, context
  hash, and scene counts so two scans can be compared honestly.
- Small local models sometimes loop inside one string until the output budget
  truncates the JSON. Every provider string now has a schema `maxLength`, and
  the parser accepts literal control characters (`strict=False`) before falling
  back to a preamble-tolerant decode.

### P6-4 — Durable scan jobs, progress, and cancel

- `POST /stories/chapters/{chapter_id}/scan-job` queues a `continuity_scan` job;
  the worker runs it with a progress callback and checks for cancellation
  between scenes. `POST /jobs/{job_id}/cancel` cancels a queued job and asks a
  running one to stop; `ScanCancelled` records `status=cancelled`.
- `ScanJobOut`, `GET /jobs/{job_id}`, and the worker handler keep long checks out
  of the request. The studio stores the job id in `sessionStorage`, resumes
  polling after a reload, shows scene progress, and offers a cancel action.

### P6-5 — Usage ledger and monthly budget

- `ai_usage` now records provider, model, purpose, token counts, latency, and
  estimated cost for local and cloud calls. `estimate_scan_tokens` bounds the
  preflight estimate.
- `Story.monthly_ai_budget` defaults to 0. A cloud call with no remaining budget
  returns 402 with a local-only message; Ollama is always free.
- `GET /stories/{story_id}/ai-usage` returns this month's totals by purpose; the
  studio shows the panel and lets the writer set the budget.
- `external_analysis_enabled` (default false) is the per-story confirmation for
  provider-backed checks; enabling it in the Notes tab is the explicit opt-in.

### P6-6 — Ask the story

- `app/services/ask_story.py` retrieves indexed chunks, asks for a structured
  answer, rejects citations whose quote is not a substring of the cited chunk,
  and refuses when retrieval is empty. The refusal path does not embed or call
  a model.
- `POST /stories/{story_id}/ask` has a Pydantic response model and an ownership
  check; `tests/test_ask_story.py` covers citations, refusals, ownership, and
  readable provider failures.
- The Find tab and the command palette (`Ask your story`) focus the question box;
  answers link to the cited chapter line.

### P6-7 — Verification

- Backend: 178 pytest tests; ruff and pyright clean.
- Frontend: 31 vitest tests; eslint (one existing compiler warning in
  `entity-list.tsx`), `tsc --noEmit`, and `next build` pass.
- `frontend/scripts/phase6-qa.mjs` runs 8 Playwright checks against the
  production build: usage panel, cited answer, palette focus, scan job tracking,
  reload resume, completion, and no page errors. `make qa-phase6` or
  `npm run qa:phase6` runs it with API :8000, `next start` :3000, and Ollama up.
- Acceptance mapping and deliberate omissions: `Docs/phase-6-acceptance.md`.
