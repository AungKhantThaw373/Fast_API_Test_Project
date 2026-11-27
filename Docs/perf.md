# Performance budget

Phase 2 targets from the build manual, measured 2026-11-24 on the local machine
(Windows 11, native PostgreSQL 18, Ollama idle). Reproduce with:

```bash
cd backend
uv run python scripts/perf.py
```

The script drives the real ASGI app in-process with `httpx.ASGITransport`, so
there is no socket or network jitter in the numbers. It writes to
`stillroom_test`, uses synthetic 768-dimensional vectors (no Ollama calls), and
deletes everything it created. Iterations: 50 for request paths, 30 for retrieval
after 5 warm-up calls, and one reorder of 1,100 chapters.

| Operation | p50 | p95 | Target | Result |
|---|---|---|---|---|
| Chapter open (`GET /stories/chapters/{id}`) | 3.9 ms | 6.4 ms | < 150 ms | pass |
| Chapter save (`PUT`, snapshot + revision) | 14.9 ms | 28.9 ms | < 150 ms | pass |
| Story list (`GET /stories`, one aggregate query) | 3.6 ms | 4.4 ms | < 100 ms | pass |
| Continuity retrieval, 10,000 chunks | 11.8 ms | 20.3 ms | < 300 ms | pass |
| One-chapter retrieval DB queries | 2 | | <= 5 | pass |
| Reorder 1,100 chapters | | 248.4 ms | < 500 ms | pass |

## What made those numbers possible

- **Story list** is a single `LEFT JOIN` aggregate (`count`/`sum`), asserted by a
  SQL event-listener test.
- **Continuity retrieval** sends every draft scene's vector in one JSON parameter
  and runs one statement. The `LATERAL` subquery keeps pgvector on the HNSW index
  (`EXPLAIN` confirms `ix_story_scene_embedding_hnsw`), so it is a nearest-neighbour
  search per scene rather than a sort of the whole story.
- **Reorder** rewrites positions in one `executemany`, renumbers display numbers in
  two bulk statements, and reloads response rows in one `WHERE id IN (...)`.
  Refreshing each chapter individually was 1,100 round trips.
- **Chapter save** pays for a snapshot policy check, the update, and a job enqueue;
  the reindex itself happens in the worker.

## Notes and limits

- These are local, single-user numbers. A hosted database adds network round
  trips, which is why query *count* is tracked as well as latency.
- Retrieval cost grows with the number of chunks in a story, not with the number
  of scenes in the draft: the draft scene count only adds work inside one
  statement. Phase 5 re-measures at 50k and 100k chunks and decides whether exact
  search is still acceptable.
- The first measurement attempt showed a 7.8 s p95 for retrieval because
  autovacuum had not yet analyzed the freshly bulk-loaded table. `scripts/perf.py`
  now runs `VACUUM (ANALYZE)` and warms up before measuring; a real bulk import
  should do the same.
