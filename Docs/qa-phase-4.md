# Phase 4 QA runbook

Two scripts cover the manual's Phase 4 verification. Both talk to the real
backend and the real database; nothing is mocked.

## Prerequisites

```bash
# API on :8000, built frontend on :3000
make dev-backend                     # or: cd backend && uv run uvicorn app.app:app --port 8000
cd frontend && npm run build && npx next start -p 3000
```

`next dev` is not usable here: its HMR websocket fails in this environment and
React never hydrates, so forms submit natively. Always test against a build.

## End-to-end flows — `frontend/scripts/wiki-qa.mjs`

```bash
cd frontend
node scripts/wiki-qa.mjs
```

Each run creates a fresh user (`qa<timestamp>@example.com`), a story with two
chapters, and cleans up nothing — the QA accounts are cheap and disposable.
It prints one line per check and exits non-zero on failure.

The 24 checks, in order:

1. Create an entity from the wiki.
2. Add an alias.
3. Add a fact with a quote; the provenance chip names chapter 1 line 1.
4. Follow the chip into the studio; the cited line is selected.
5. Capture a manuscript selection as a new entity; the quote and line are stored.
6. Read name candidates for chapter 2 and accept one.
7. Merge two entities with a dry-run preview, then undo it.
8. The merged-away entity stops resolving (409), and the survivor keeps the facts.
9. The inbox shows the frozen fact proposals with a "why held" line.
10. Accept a proposal with the `a` key; it disappears and the fact becomes accepted.
11. Auto-accept rules preview a concrete count.
12. Create an arc from the rail; assign a chapter to it; collapse the group.
13. The wiki filters by arc and agrees with the API.
14. The threads page lists an open question; resolving it requires a payoff chapter.
15. The command palette (`Ctrl+K`) finds an entry and opens it.
16. Filters survive a refresh (URL state).
17. No unexpected console errors or 404/409 responses.

Notes:

- Backend auth is a `token` cookie from `/token`, not a Bearer header.
- The login button has no `type="submit"`; use `getByRole("button", { name: "Sign in" })`.
- The inbox keyboard handler listens on `document`, so clicking a row is not
  needed — clicking lands on a link and leaves the page.
- Skeleton rows also carry `.wiki-row`; wait for `.wiki-row-main`.
- A 404/409 on `/entities/{uuid}` is expected for a merged-away entity and is
  excluded from the console-error check.

## Performance — `frontend/scripts/wiki-perf.mjs`

```bash
cd backend
uv run python -m scripts.seed_wiki --email you@example.com --title Perf --count 1000

cd ../frontend
node scripts/wiki-perf.mjs you@example.com 'your password' Perf
```

The seeder inserts entities (with one alias and one accepted/proposed fact each)
straight into the database in one transaction, spread across the story's existing
chapters. It never calls an AI provider.

Targets come from the manual: search under 250 ms, entity detail under 150 ms,
first list render under 200 ms after data load (the script reports network
included, so the budget is 2 s), and no layout shift.

## What is not automated

- Lighthouse / axe. Run Lighthouse against the built app before a release.
- Contrast: the muted palette was darkened to the `#6b6f66` family (≈5:1 on
  `#fffefa`), and there is no UI text below 12 px, but this is checked by grep,
  not by a tool.
