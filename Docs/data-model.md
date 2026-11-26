# Data model

This is a map, not a schema dump. The executable schema is in
`backend/app/models/`; migration history is in `backend/alembic/versions/`. The
current head is `f1b7c3d9e5a2` (the HNSW chunk index).

All primary keys are UUIDs. Timestamps are UTC. User-owned rows carry an
`owner_id` or reach an owner through `story_id`; routes enforce that scope.

## Manuscript

```text
users
  └── stories
        ├── arcs
        ├── story_chapters
        │     ├── story_chapter_revisions
        │     ├── story_chunks
        │     ├── story_scene_embeddings
        │     ├── chapter_meta / scene_meta
        │     └── entity_mentions
        ├── entities
        │     ├── entity_aliases
        │     ├── entity_facts
        │     ├── entity_relationships
        │     └── entity_merges / merge_proposals
        ├── story_events
        ├── story_threads
        ├── canon_exceptions
        ├── continuity_scans / continuity_findings
        └── auto_accept_rules
```

| Table | What it holds | Important behavior |
|---|---|---|
| `stories` | Title, collection name, scan interval, monthly AI budget, owner, optional trash timestamp | Story list is one indexed query; `deleted_at` means trash, not gone |
| `arcs` | Named/numbered groupings of chapters | Chapter order and arc coverage drive the wiki rail |
| `story_chapters` | Prose, display/chapter number, revision counter, indexing state | Active `(story_id, chapter_number)` is a partial unique index; reorders use temporary numbers |
| `story_chapter_revisions` | Immutable saved prose snapshots | Retention is tiered; diffs and restore use these rows |
| `story_chunks` | 1,200-2,400-character retrieval units plus 768-d vector | HNSW index; embeddings can be deferred from list reads |
| `story_scene_embeddings` | Scene-level vectors used by older extraction/retrieval paths | Kept for compatibility; chunk retrieval is the current primary path |
| `story_bible_entries` | Legacy compatibility view of the old bible | Still read by `/bible`; new writes go to the knowledge model |

## Knowledge model

| Table | What it holds |
|---|---|
| `entities` | People, places, items, organizations, concepts; type, description, aliases |
| `entity_aliases` | Alternate names and normalized lookup keys |
| `entity_facts` | Predicate/value facts with source chapter, confidence, status |
| `entity_relationships` | Typed links between two entities |
| `story_events` | Dated/ordered events with participants and evidence |
| `story_threads` | Open/resolved plot threads with payoff chapter |
| `entity_mentions` | Zero-LLM mentions with chapter offsets and surface form |
| `canon_exceptions` | Writer-approved exceptions to a continuity rule or pattern |
| `chapter_meta` / `scene_meta` | Summaries, POV, time/place, extraction state |
| `entity_merges` / `merge_proposals` | Merge audit and reviewable pending merges |
| `auto_accept_rules` | Previewable rules for the review inbox |
| `continuity_scans` / `continuity_findings` | Durable scan state and per-scene evidence |

Facts, findings, recaps, and answers keep provenance. A quote without a chapter
and scene is not enough to be actionable, so the model records both.

## Identity, operations, and money

| Table | What it holds |
|---|---|
| `users` | Account identity, password hash, admin flag, created/deleted state |
| `auth_sessions` | Revocable session records; the signed JWT carries the row id (`jti`) |
| `login_attempts` | Every sign-in attempt with email, IP, time, and outcome; in-process rate-limit buckets reset when the API restarts |
| `password_reset_tokens` | One-time reset tokens with expiry and use state |
| `audit_events` | Security-relevant account and data actions |
| `jobs` | Durable worker queue: type, payload, status, attempts, heartbeat, progress |
| `worker_heartbeats` | Liveness for the single worker |
| `ai_usage` | Per-call provider, model, purpose, tokens, cost estimate |
| `user_ai_settings` | Per-user provider/model/budget choices |
| `editing_folders` / `editing_draft_files` | Draft-file library, separate from manuscript chapters |

`jobs` is the only queue. Statuses in use are `queued`, `running`, `succeeded`,
`failed`, `cancelled`, and `dead`; a failed job is retried with backoff until
`max_attempts`, then becomes `dead`. Finished jobs older than 30 days are
eligible for the manual cleanup described in [data-retention.md](data-retention.md).

## Indexes that matter

- `ix_story_chunks_embedding_hnsw`: HNSW cosine index over chunk vectors,
  `m=16`, `ef_construction=64`. It nearly doubles chunk storage at 100k rows
  but replaces an exact scan that took seconds.
- Partial unique index on active `(story_id, chapter_number)`: prevents duplicate
  chapter numbers without blocking trashed rows.
- Trigram and full-text indexes for lexical retrieval and name matching.
- Foreign-key indexes for story/chapter lookups and ownership checks.

## Retention and deletion

Deleting a story or chapter sets `deleted_at`; the row stays in trash for 30
days. Trash purge removes expired rows, and account deletion is explicit and
typed. Backup files are outside the database and follow their own rotation. See
[data-retention.md](data-retention.md) for the full policy.

## Scale fixture shape

`scripts/import_fixture.py` writes one synthetic account and one story with
1,100 chapters, 6,600 chunks, 12 arcs, 750 entities, 1,350 aliases, 100 facts,
and 70 threads. Its 92 MB database is a useful size test, not a semantic
benchmark: the vectors are deterministic synthetic units unless the importer is
run with `--embedding-mode ollama`.