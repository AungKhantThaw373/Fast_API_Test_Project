# Phase 1 QA

Automated backend and unit coverage:

```bash
cd backend && uv run pytest -q          # 58 tests
cd frontend && npm test                 # 19 unit tests (IndexedDB buffer, diff, state machine)
```

Browser flows against a real Chromium (Playwright):

```bash
# Terminal 1
cd backend && uv run uvicorn app.app:app --port 8000
# Terminal 2 — use a production build; the dev HMR socket breaks automation here
cd frontend && npm run build && npx next start -p 3001
# Terminal 3 — needs a user (ui@test.dev / ui-test-password) with one story that
# has two chapters
cd frontend && BASE_URL=http://127.0.0.1:3001 npm run qa:phase1
```

The script covers:

1. Type a sentence, click **Stories** immediately, reopen the chapter — the
   sentence is still there.
2. Open version history, save a checkpoint, confirm it is listed.
3. Delete a chapter, open the dashboard trash, restore it.
4. Open the same chapter in two tabs, save in both, choose **Keep mine** in the
   conflict dialog — the local text survives.

Manual checks that remain manual: offline editing (stop the backend, keep typing,
reload, restart, save), and the 30-day purge clock (covered by a unit test with a
simulated date).
