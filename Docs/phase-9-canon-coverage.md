# Phase 9 — lazy canon coverage (P9-3)

The importer writes chapter text and vectors immediately. Canon extraction is
the expensive, optional part, so it now runs by arc instead of by manuscript.

## What exists

- `GET /stories/{story_id}/canon/coverage` returns every arc with
  `chapter_count`, `extracted_count`, `pending_count`, `complete`, the current
  arc, and unassigned chapter count. "Extracted" means
  `bible_scan_revision == revision` for an active chapter; an edited chapter
  automatically becomes pending again.
- `POST /stories/{story_id}/canon/arcs/{arc_id}/extract` queues only chapters
  in that arc that still need extraction. `?force=true` re-queues the arc.
  The route queues the job immediately; estimated cost is shown in the usage
  ledger after the calls complete.
- The arc page shows `extracted / chapters`, a progress bar, pending count, and
  an **Extract remaining** button. The wiki rail shows the current arc as
  `Arc N of M` with its extracted chapter count.
- Coverage reads counts and the latest arc only; it never loads chapter text.
  The extraction selection reads IDs and revisions plus `length(trim(content))`
  to skip empty chapters, not the manuscript body.

## Scale check

Against the generated 1,100-chapter corpus in `stillroom_scale_test`:

| Measure | Result |
|---|---|
| Arcs | 12 |
| Chapters | 1,100 |
| Extracted at import | 0 (deliberate) |
| Unassigned chapters | 0 |
| Current arc | Arc 12: Lantern Quay (92 chapters) |
| Coverage latency, 30 runs | p50 22.2 ms, p95 29.5 ms, max 33.7 ms |

The current arc alone is 92 chapters; opening it does not extract anything
until the writer presses the button. The other 1,008 chapters remain untouched.

## End-to-end drill

`scripts/canon_extract_drill.py` registers a throwaway account, points it at
local Ollama (`qwen3:4b-instruct`), creates one chapter and one arc, queues the
arc, and polls coverage. Verified result:

```
queued 202 {"scheduled_count": 1, "skipped_count": 0, "chapter_count": 1}
coverage 0 / 1 pending 1
coverage 1 / 1 pending 0
```

The worker was already running with one concurrency. The API stayed responsive
while the job ran.

`frontend/scripts/canon-qa.mjs` checks the rendered arc page and rail against a
production build: 7/7 checks, including that the button queues only the arc
and that coverage remains lazy until the worker finishes.

## Limits

- A queued arc is a whole arc. With roughly 92 chapters per generated arc that
  is still a large batch; there is no scene-level partial extraction yet.
- Coverage says a chapter was scanned at its current revision. It does not
  prove every entity or fact in that chapter was found correctly.
- There is no automatic background scan of the current arc on story open. It is
  one click by design, so a writer never unknowingly spends tokens.
- Local extraction needs an Ollama provider selected in AI settings. The
  presence of an OpenRouter key in `.env` makes cloud the fallback; choose
  local and disable external analysis for the story to keep prompts offline.
- Coverage counts active chapters, including empty placeholders. Queuing skips
  empty chapters, so an arc made only of placeholders can show a pending count
  the button cannot act on until text is added.
- Synthetic scale vectors carry no meaning, so this task proves selection,
  counting, and queue behavior — not extraction quality on the fixture.