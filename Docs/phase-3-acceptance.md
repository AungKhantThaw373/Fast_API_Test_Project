# Phase 3 acceptance — knowledge model

Adapted from the manual's Phase 3 list. Each line names the check and where to
see it.

## Acceptance

| Requirement | Status | Evidence |
|---|---|---|
| Old bible UI still works through the compatibility serializer | Pass | `GET /stories/{id}/bible` reads entities, summary facts, and threads and projects them into the old entry shape (`app/services/compat.py`). On the live `stillroom` database it returns the same 45 entries as before the migration, no duplicates. `PATCH /stories/bible/{id}/decision`, `PUT /stories/bible/{id}`, `DELETE /stories/bible/{id}`, and `PATCH /stories/bible/{id}/thread` accept entity and thread ids and act on the knowledge model. `tests/test_wiki_api.py::test_old_bible_endpoints_edit_entities` |
| Entities preserve existing IDs and content | Pass | `app/backfill/bible.py` keeps `story_bible_entries.id` as `entities.id` (and for plot threads as `story_threads.id`). Live run: 36 entities all matching their legacy ids, 36 aliases, 36 summary facts with located lines, 9 threads, 251 mentions. `tests/test_entities.py::test_backfill_preserves_ids_and_is_idempotent` |
| Every fact links to a chapter, and AI facts need a verified quote | Pass | `create_fact` rejects a missing chapter (422), requires a quote for `created_by="ai"`, locates the line itself, and verifies the quote's words appear in that chapter. `tests/test_wiki_api.py::test_ai_fact_requires_provenance`, `::test_fact_requires_a_value_and_owned_chapter` |
| Merge is previewable, atomic, and reversible | Pass | `POST /entities/{id}/merge` supports `dry_run` (rolls back, reports counts), runs in one transaction with `FOR UPDATE` locks, and writes an `entity_merges` audit row with every moved id. `POST /entities/{id}/unmerge` restores facts, mentions, relationships, aliases, and array memberships from that audit. `tests/test_wiki_api.py::test_merge_endpoint_moves_facts_and_honours_dry_run`, `::test_merge_can_be_undone_from_its_audit` |
| Mention extraction runs with zero LLM calls | Pass | `extract_mentions` is a regex over aliases: longest alias first, word boundaries, stoplist, one row per entity per line. `tests/test_entities.py::test_mention_extraction_is_case_insensitive_and_range_limited` (no AI stub, no provider) |
| Continuity prefers facts and respects exceptions | Pass | `build_fact_context` sends accepted facts for entities named in the draft, their relationships, and open threads as `CANON NOTES`. `filter_exceptions` drops any finding matching a recorded exception pattern before it reaches the inbox. `tests/test_entities.py::test_canon_notes_include_only_mentioned_accepted_facts`, `tests/test_wiki_api.py::test_canon_exceptions_suppress_matching_findings` |
| All tests pass | Pass | 115 backend tests, ruff and pyright clean; frontend lint, `tsc --noEmit`, `next build`, and 19 vitest tests pass |

## Not in this phase

- AI extraction still writes `story_bible_entries` directly. The compatibility
  view appends those rows, so nothing disappears, but the new proposal path
  (extract → `entity_facts` with `status='proposed'` → inbox) lands in Phase 6
  (P6-2).
- Entity- and predicate-scoped canon exceptions are stored and validated, but
  only pattern-scoped ones can suppress a finding until findings carry entity
  attribution.
- The wiki UI itself is Phase 4.

## Commands

```bash
cd backend
uv run alembic upgrade head                       # 0b5e2c7d9a64 is head
uv run python -m app.backfill.bible --mentions     # idempotent
uv run pytest -q
cd ../frontend && npm run lint && npx tsc --noEmit && npm test -- --run
```
