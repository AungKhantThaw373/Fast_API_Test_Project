# Phase 7 acceptance

Phase 7 turns the studio into a writing surface: CodeMirror replaces the
textarea, accepted canon is visible in the prose, the manuscript can be shaped
with read-only style tools, and the finished book leaves as a real manuscript
file. The browser flows run against the production build on native PostgreSQL,
with Pandoc and Chrome installed for export.

## Checklist

- [x] **The editor handles a book-length chapter.**
  CodeMirror 6 mounts the chapter, keeps a local IndexedDB draft, and restores
  undo history after a reload. `frontend/scripts/p7-editor-smoke.mjs` types into
  a 100,000-character chapter (14,250 words), asserts keystrokes stay under the
  20 ms budget, checks word count, and reloads to prove undo history survives.
- [x] **Canon is visible in the text without changing it.**
  Entity aliases and continuity findings become decorations, not content.
  Hovering an entity mark shows its accepted facts and a link into the wiki;
  clicking an entity opens its page. `p7-marks-smoke.mjs` verifies marks,
  hover cards, click-through, and that no scan finding edits the chapter.
- [x] **Writing tools stay opt-in and read-only.**
  The style panel reports reading ease, grade, sentence length, repeated
  openings, crutch/filter words, adverbs, passive voice, and tense observations.
  Clicking an observation selects the passage; dismissing or muting only hides
  annotations. `p7-style-smoke.mjs` proves the manuscript is byte-identical after
  the panel runs (296 characters before and after).
- [x] **Navigation and actions are available without the mouse.**
  The command palette (`Ctrl/Cmd+K`) exposes primary actions, chapter and entity
  search, manuscript passage search, theme changes, and recents. Escape returns
  focus to the writing surface. `p7-palette-smoke.mjs` covers the action list,
  keyboard hints, passage search, entity links, theme state, and recents.
- [x] **Recaps cite the manuscript.**
  Chapter synopses are editable from the desk and can be regenerated from the
  chapter. Story-so-far rows carry chapter citations and open the cited line;
  arc summaries are built from chapter synopses. `p7-recap-smoke.mjs` checks
  persistence, regeneration, the explicit chapter range, citations, and return
  to the manuscript.
- [x] **Plot threads are a board, not a table.**
  Four columns (open, touched, resolved, abandoned) accept drag-and-drop and a
  keyboard path; resolving always requires a payoff chapter. Filters by arc and
  entity survive the round trip. `p7-thread-smoke.mjs` covers all four states,
  persisted state, the payoff chapter, filters, and clearing them.
- [x] **The manuscript exports cleanly.**
  Markdown, DOCX, EPUB, and PDF download with the wiki as an optional appendix.
  DOCX uses generated double-spaced 12 pt Georgia with indented paragraphs and
  a page-number footer; PDF prints through Chrome with a serif stylesheet and
  page numbers in the page margin, with no browser URL or date header. Missing
  Pandoc or Chrome returns 503 with an install hint. `p7-export-smoke.mjs`
  verifies file signatures and contents for all four formats.
- [x] **Backups restore the whole book.**
  `GET /stories/{story_id}/backup` returns a versioned JSON document; import
  creates a new story, remaps every id, and excludes derived chunks,
  embeddings, and mentions. The browser test restores a backup and opens the
  new story route with its chapter intact. Backend coverage is in
  `tests/test_backup_export.py` (5 tests), including ownership and bad versions.
- [x] **The new surfaces are accessible.**
  Export and thread-payoff dialogs trap Tab and restore focus on Escape. The
  thread board supports Space to lift, arrow keys to change columns, and Space
  to drop. At 390 px the studio stacks instead of overlaying, the export dialog
  fits the viewport, and the thread board scrolls between full-width columns.
  No new text is below 12 px. `p7-responsive-smoke.mjs` checks 21 of these
  behaviours; reduced-motion rules remain from Phase 4.
- [x] **The suite is clean.**
  190 backend tests pass; ruff and pyright are clean. 47 frontend tests pass;
  eslint has no errors, `tsc --noEmit` and `next build` pass. `npm run qa:phase7`
  runs 8 browser suites and 85 checks against the production build, all passing.

## What shipped

| Task | Where |
|---|---|
| P7-1/P7-2 editor and inline canon | `frontend/components/manuscript-editor.tsx`, `frontend/lib/manuscript-decorations.ts`, `frontend/lib/entity-matcher.ts` (`e7bd940`) |
| P7-3 palette actions and recents | `frontend/components/command-palette.tsx` (`16fe40c`) |
| P7-4 style and line-edit panel | `frontend/components/style-panel.tsx`, `frontend/lib/style-analysis.ts` (`c064bfe`) |
| P7-5 cited recaps | `frontend/components/recap-panel.tsx`, `backend/app/services/recaps.py` (`ff9a926`) |
| P7-6 thread board | `frontend/components/wiki/threads-page.tsx` (`ff9a926`) |
| P7-7 export and backup | `backend/app/services/export.py`, `backend/app/services/backup.py`, `frontend/components/export-panel.tsx` (`b89acf6`) |
| P7-8 accessibility, responsive, QA | `frontend/lib/focus-trap.ts`, `frontend/app/globals.css`, `frontend/scripts/phase7-qa.mjs` (this commit) |

The editor and its canon decorations share one CodeMirror extension surface and
landed in a single commit; they are listed together rather than pretending the
history has two independently buildable halves.

## Running the acceptance flows

1. Start PostgreSQL and run `cd backend && uv run alembic upgrade head`.
2. `cd backend && uv run uvicorn app.app:app --host 127.0.0.1 --port 8000`.
3. `cd frontend && npm run build && npx next start -H 127.0.0.1 -p 3000`.
4. `cd frontend && npm run qa:phase7` (or `make qa-phase7`).

Exports need Pandoc 3.x and Chrome or Edge. The QA scripts create their own
users and stories and do not delete them; point them at a test database if the
rows should not remain. The scripts use `127.0.0.1`, so start both servers on
that host.

## Deliberately left out

- **Bundled Pandoc or a browser.** The backend shells out to installed tools and
  returns 503 rather than shipping a second copy or a half-written file.
- **PDF page numbers on every browser.** The page number uses Chrome's CSS
  margin box. Current Chrome and Edge print it; a browser without margin-box
  support still produces a valid PDF, just without the number.
- **In-app pagination or print preview.** The editor is a continuous manuscript;
  pagination is decided by the export stylesheet so the screen never lies about
  page breaks.
- **DOCX/EPUB import.** Only the JSON backup round-trips. Word and EPUB are
  export targets, not editing formats.
- **Cloud spelling or grammar.** Style analysis is deterministic and local; no
  prose leaves the machine for these checks.
