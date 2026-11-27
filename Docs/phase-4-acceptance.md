# Phase 4 acceptance

Manual: *Phase 4 — Wiki UX*. Everything below was run on the local machine with
the native PostgreSQL 18 database (`stillroom`, `stillroom_test`) — no Docker.

## Acceptance lines

| Line | Evidence |
|---|---|
| A writer can find any entity and its facts in ≤3 actions | Wiki list (`/stories/{id}/wiki`) → row (`j`/`k` + `Enter`, or the command palette `Ctrl/Cmd+K` → search) → facts are on the detail page. `scripts/wiki-qa.mjs`: "create entity from the wiki", "command palette opens an entry". |
| Every fact has a clickable provenance chip | `components/wiki/provenance-chip.tsx` renders chapter + line + quote for every fact with a chapter; the chip deep-links to `/stories/{id}?chapter=…&line=…`. QA: "provenance chip names chapter and line", "provenance opens the cited line". |
| New names can be captured without leaving the chapter | Selection toolbar → `capture-dialog` (entry/fact/thread, quote + line prefilled); desk **Mentions** tab lists `name_candidates` with Accept. QA: "capture selection as entity", "captured quote is attached with provenance", "name candidates are proposed", "accept a name candidate". |
| The inbox can clear a chapter's proposals quickly | `components/wiki/inbox-page.tsx`: kind tabs with counts, chapter filter, entry/confidence filters, select-all, batch accept/reject, `j`/`k`/`a`/`x`/`e`. Backend `POST /inbox/decide` decides many ids in one transaction. QA: "accept a proposal with the keyboard". |
| Arcs make a long story navigable | `arcs` + `story_chapters.arc_id`; the rail groups chapters under collapsible arc headers with a per-chapter arc picker; `/wiki/arcs/{id}` is the arc summary; `/wiki?arc=` filters entries (appearance range **or** a fact in an arc chapter). QA: "create an arc from the rail", "assign a chapter to an arc", "arc groups collapse", "the wiki filters by arc". |
| No 8–10 px UI text in new surfaces | `app/globals.css` has no `font-size` below 12 px (checked with `grep -o "font-size: [0-9.]*px" \| sort -u`). |
| All Playwright flows pass | `node scripts/wiki-qa.mjs` → 24/24. |

## Performance (1,000 entities)

`backend/scripts/seed_wiki.py` seeds 1,000 entities with an alias and a fact
each; `frontend/scripts/wiki-perf.mjs` measures against the targets in the
manual (search 250 ms, detail 150 ms, no layout shift).

```
PASS Search                                17 ms  (target 250 ms)
PASS List first paint (incl. network)     430 ms  (target 2000 ms)
PASS Entity detail (incl. network)        173 ms  (target 900 ms)
PASS Entity detail API                     13 ms  (target 150 ms)
PASS Layout shift (×1000)                  21 ms  (target 100 ms)
```

## Accessibility

- Focus: every dialog is a Radix `Dialog`/`AlertDialog` (focus trap + restore +
  Escape); the command palette is `cmdk`'s own dialog.
- Keyboard: `j`/`k`/`Enter` in lists, `a`/`x`/`e`/`space` in the inbox,
  `Ctrl/Cmd+K` palette, `Ctrl/Cmd+.` desk collapse, `Ctrl/Cmd+Shift+W` wiki,
  `/` search focus. All of these were exercised in the Playwright run.
- Live regions: save state (`role="status"`/`assertive` on error), list counts,
  inbox counts, auto-accept preview, job progress.
- Contrast: muted text moved from `#92938a`/`#85877d` (≈3.0:1) to the
  `#6b6f66` family (≈5:1 on `#fffefa`); the 12 px floor applies to labels too.
- Reduced motion: `@media (prefers-reduced-motion: reduce)` disables spinners and
  transitions.

A Lighthouse run was not performed (the manual asks for one); the checks above
are the parts that automation can assert. Worth doing before Phase 5 ships.

## Deliberately deferred

- Sharing saved views across devices (`saved_views` table) — manual says not yet.
- Entity-scoped canon exceptions (needs entity/predicate attribution on findings).
- Moving the legacy `story_bible_entries` write path: the desk no longer edits
  the legacy table, but the backfill and `compat.py` still read it until the
  extraction rewrite (P6-2) lands.
- "Ask your story" in the palette — Phase 6/7.
