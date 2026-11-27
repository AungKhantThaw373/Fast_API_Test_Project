# Phase 0 acceptance

- [x] **App boots against local Postgres.** `uvicorn app.app:app` started, `/health`
      returned `{"status":"ok"}`, and the startup schema check passed.
- [x] **Data counts match the Supabase dump.** users 4, stories 1, chapters 5,
      revisions 3, scene embeddings 25, bible entries 45, scans 6, findings 18,
      folders 1, AI settings 1 — verified on both sides.
- [x] **Config validation fails on weak secrets.** `JWT_SECRET=short` and
      `APP_ENV=production` without `COOKIE_SECURE` both exit with a readable
      `Configuration error:` message.
- [x] **Email normalization works.** Mixed-case registration, case-insensitive
      login, and a 409 on a case-variant duplicate are covered by tests.
- [x] **Test files pass.** 36 tests in `tests/` (auth, ownership, chapter conflicts,
      reorder, scenes, quote verification, plus bookkeeping).
- [ ] **CI is green.** The workflow is committed; it has not run on GitHub from this
      machine. The same commands pass locally (`ruff`, `pyright`, `pytest`,
      `npm run lint`, `npx tsc --noEmit`, `npm run build`).
- [x] **Backup and restore are verified.** Restore drill recorded in
      `Docs/backups.md`.
- [x] **No dead imports, no dead routes.** Legacy RAG models/routes, the Supabase
      client, and the unused `rooms`/`docs` ORM models are gone.
- [x] **`make test`, `make lint`, `make typecheck` work** (verified on Windows with
      GNU make available; otherwise run the commands directly).

## Manual smoke test

Performed 2026-11-24 against the local database with the API on port 8011:

- register: 201
- login with a different email case: 200
- create story: 201
- create chapter: 201, revision 1
- autosave with `expected_revision`: 200, revision 2, word count updated
- indexing: `indexed` after Ollama embedded one scene (8.1 s cold)
- list stories: one story with chapter and word counts

The smoke-test account and story were removed afterwards.
