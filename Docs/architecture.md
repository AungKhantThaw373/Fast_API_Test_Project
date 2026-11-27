# Architecture

Stillroom is a local-first writing studio. A writer edits chapters in the browser,
the API stores them in PostgreSQL, and an optional worker turns new prose into
searchable chunks and structured story knowledge. There is no message broker and
no external application database: PostgreSQL is both the source of truth and the
job queue.

## Processes

```text
browser
  |  HTTPS / same-origin proxy
  v
Next.js web (3000)  -- /api proxy -->  FastAPI (8000)  -->  PostgreSQL 18 + pgvector
                                              ^                    |
                                              |                    | jobs, chunks
                                         worker (one) <------------+
```

| Process | Responsibility | Notes |
|---|---|---|
| `web` | Server-rendered Next.js app, same-origin proxy to the API | Holds no story data of its own; browser state is UI state and the IndexedDB draft buffer |
| `api` | Authentication, ownership checks, validation, reads/writes, job creation, exports | Never runs long AI work in-process |
| `worker` | Claims durable jobs (`reindex_chapter`, `bible_scan`, `continuity_scan`) | One process, concurrency 1 by default for a single local GPU |
| `db` | Stories, revisions, chunks, knowledge model, jobs, audit, usage ledger | PostgreSQL with `vector` and `pg_trgm` extensions |

The native Windows setup runs these as separate terminal processes. The Compose
file describes four containers plus optional Caddy, but Docker has not been
installed on this machine; see [limitations.md](limitations.md).

## Request path

1. The browser calls the Next.js app. `frontend/next.config.ts` proxies `/api/*`
   to `http://127.0.0.1:8000` so the auth cookie stays same-origin.
2. FastAPI middleware assigns a request id, applies security headers, and checks
   origin/CSRF on writes. Authentication uses an HttpOnly `token` (or
   `__Host-token` on HTTPS) cookie; writes also need the readable `csrf` cookie
   echoed in `X-CSRF-Token`.
3. A route resolves the current user and delegates to a service. Every story
   read/write is scoped by `owner_id`; a missing or foreign id is a 404, not a
   403 that reveals existence.
4. SQLAlchemy async sessions use a 15-second statement timeout on the request
   path. Slow statements are logged with the request id.

Error responses carry `detail` and `request_id`. The UI shows the request id so
a failure can be matched to the server log.

## Write path and indexing

```text
save chapter
  -> validate ownership, expected revision, content limits
  -> update chapter + insert revision (when prose changed)
  -> mark indexing stale / enqueue reindex_chapter
  -> commit

worker claims reindex_chapter
  -> sentence-aware chunks (1,200-2,400 chars, 12% overlap)
  -> embed with the configured model
  -> replace story_chunks, update indexed_embedding_model
```

The save request does not wait for embeddings. If the worker is stopped, the
chapter is still saved and searchable by its previous index until the queue
drains. The UI reports indexing state rather than pretending it is complete.

Story Bible extraction and continuity scans follow the same pattern: the API
creates a durable job, the worker calls the model, and progress is stored on the
job row. Cloud calls are recorded in the usage ledger; a local-only story sends
nothing to a provider.

## Retrieval

Hybrid retrieval combines three signals:

- vector similarity over `story_chunks.embedding` (768 dimensions);
- lexical matching with PostgreSQL full-text/trigram indexes;
- entity/name matches from the knowledge model.

Story chunk vectors use a global HNSW index (`vector_cosine_ops`, `m=16`,
`ef_construction=64`). Retrieval sets `hnsw.ef_search=400` and enables relaxed
iterative scanning so a story filter can still fill the requested result count.
The index is approximate by design; the measured recall and latency trade-off is
in [scale-report.md](scale-report.md) and [retrieval.md](retrieval.md).

Canon extraction is deliberately lazy. Importing or saving text and embeddings is
immediate; structured extraction runs only when the writer asks for the current
arc or opens an entity that needs it. This avoids an unexpected full-manuscript
AI bill after a large import.

## Data and jobs

PostgreSQL tables fall into five groups:

1. identity and security (`users`, sessions, password resets, audit events);
2. manuscript (`stories`, `story_chapters`, `story_chapter_revisions`);
3. retrieval (`story_chunks`, embeddings, HNSW index);
4. knowledge (`entities`, aliases, facts, relationships, events, threads,
   mentions, canon exceptions, chapter/scene metadata);
5. operations (`jobs`, `ai_usage`, trash retention, backups).

Jobs are claimed with `FOR UPDATE SKIP LOCKED`, have attempts and heartbeats, and
survive an API or worker restart. Exactly one worker is the supported topology
today. See [data-model.md](data-model.md) for the relationships and
[worker.md](worker.md) for job lifecycle.

## Scale shape

The Phase 9 fixture is 1,029,590 words in 1,100 chapters, producing 6,600
chunks, 750 entities, 1,350 aliases, 100 facts, and 70 threads. With the HNSW
index the database is 92 MB. The measured request latencies are in
[scale-report.md](scale-report.md); the short version is that chapter reads and
saves stay in the low tens of milliseconds, while hybrid search is dominated by
the query embedding call (about 70 ms of a 135 ms p50 on this machine).

## Design boundaries

- Single writer account model: collaboration, sharing, and multi-tenant teams are
  not implemented.
- One API process and one worker are the supported local deployment. The job
  queue supports more workers, but the GPU/model residency assumption does not.
- The API is not a general file server; uploads and exports have explicit limits.
- The database is the only durable store. Browser drafts are a crash buffer, not
  a second source of truth.
- There is no application-level telemetry. Operational evidence comes from logs,
  `/health`, `/ready`, `/system/status`, `/system/diagnostics`, and
  `/system/storage`.