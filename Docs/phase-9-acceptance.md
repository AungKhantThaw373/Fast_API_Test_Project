# Phase 9 acceptance — scale and proof

Goal: prove the app works at JJK/One Piece scale and document the limits honestly.

Tagged `phase-9-complete`. This page maps the acceptance claims to checks that
actually ran. The corpus is synthetic and the default vectors are meaningless by
construction, so this is a scale and operations proof, not a literary-quality
claim. Read it with [limitations.md](limitations.md).

## Verdict

Stillroom imports a 1,029,590-word manuscript and keeps the story list, chapter
load, and changed save fast in a 30-minute soak. Hybrid search is low-hundreds
of milliseconds when idle but its p95 rose to about 700 ms under continuous
query embedding plus worker reindexing; that is documented, not hidden. It also
survives a fresh install, a backup/restore drill, and the measured mixed soak.
The 24-hour soak was **not** run; the actual duration is recorded below and must
not be rounded up in later retrospectives.

| Claim | Status | Evidence |
|---|---|---|
| 1M-word corpus imports and remains usable | **Proven for this fixture** | 1,100 chapters / 6,600 chunks imported in 27.9 s; API numbers below |
| Retrieval and save latency documented | **Proven locally** | `Docs/eval/scale-api-hnsw.json`; search p95 191.2 ms |
| App responsive during bulk indexing | **Measured in soak** | Search/load while the worker reindexed saved chapters; no 5xx |
| Restore drill | **Proven locally** | Scale dump restored; 1,101 chapters / 6,610 chunks; 7/7 API reads |
| Export drill | **Proven at scale** | Backup, Markdown, DOCX, EPUB, PDF, account ZIP all returned |
| No process scans the whole manuscript | **Proven by lazy design and drill** | Canon drill queued only the requested arc; no whole-story scan path |
| Runbook followed once | **Proven** | Fresh database + release checks below |
| 24-hour soak | **Not run** | Actual soak duration below |
| Docker/Compose and GitHub Actions | **Not run here** | Docker is not installed; CI has never executed |

## P9-1 — deterministic scale fixture

- `scripts/generate_fixture.py` creates a synthetic serial: 1,100 chapters,
  1,029,590 words, 12 arcs, 750 entities, 1,350 aliases, 100 accepted facts,
  70 threads, 100 planted contradictions, and 100 near-misses. It copies no
  published text.
- The fixture is reproducible from a seed and is isolated in
  `stillroom_scale_test`. The import account is local-only.
- Evidence: [scale-import.md](scale-import.md), [scale-report.md](scale-report.md).

## P9-2 — resumable import and indexing

- `scripts/import_fixture.py --migrate` writes chapter text and synthetic
  vectors immediately, records a per-chapter state, and can resume after a failed
  chapter. The measured full import was 27.89 s (36,919.83 words/s) with zero
  failed chapters.
- 6,600 chunks were created; the database grew from 58 MB before the HNSW index
  to 92 MB after it. Chunk relations are 69 MB and the HNSW index is 26 MB.
- Canon extraction is not part of import. That is deliberate; see P9-3.

## P9-3 — lazy canon coverage

- The canon coverage service/route (`app/services/canon_coverage.py`,
  `backend/app/routes/canon.py`) and the UI expose extraction as an explicit
  per-arc action. Opening a 1,100-chapter story does not start 1,100 AI scans.
- Older arcs show their coverage state instead of being silently marked
  complete. Backfill is an explicit action.
- The canon coverage drill passed 7/7 checks; the policy and deliberate
  omissions are recorded in [phase-9-canon-coverage.md](phase-9-canon-coverage.md).

## P9-4 — HNSW at scale

- Migration `f1b7c3d9e5a2` adds `ix_story_chunks_embedding_hnsw` with `m=16`,
  `ef_construction=64`, and `ef_search=400` at query time using relaxed iterative
  scanning.
- The 100k benchmark measured exact p50 1,460.4 ms vs HNSW ef400 p50 2.2 ms,
  recall@30 1.0; build 112.2 s and index 390.6 MB. At ef200 recall was 0.80, so
  the app keeps 400.
- The index is global across stories; selective story/arc filters rely on
  iterative scan. This is approximate search, not an exact guarantee.
- Evidence: [scale-report.md](scale-report.md), `Docs/eval/hnsw-100k.json`,
  `Docs/eval/scale-api-hnsw.json`.

## P9-5 — storage and retention

- `GET /system/storage` reports database bytes, the eight largest relations, and
  account-scoped active/trashed/job counts. `POST /system/storage/cleanup` purges
  the signed-in account's trashed rows older than 30 days and terminal jobs older
  than 30 days.
- The dashboard is read-only apart from that explicit cleanup. It never deletes
  active prose, does not run `VACUUM`, and does not claim immediate disk
  reclamation.
- Five backend tests cover report shape, chapter cleanup, story cascade,
  ownership isolation, and finished-job pruning. The browser storage QA passed
  10/10 checks.
- Evidence: `backend/tests/test_storage.py`, `frontend/scripts/storage-qa.mjs`,
  [data-retention.md](data-retention.md).

## P9-6 — operational documentation

- [architecture.md](architecture.md): process topology, request/write/indexing
  paths, retrieval, jobs, and scale shape.
- [data-model.md](data-model.md): manuscript, knowledge, identity tables,
  relationships, indexes, retention.
- [runbook.md](runbook.md): first start, health checks, migrations, backups,
  worker, storage, scale fixture, common failures, release commands.
- [privacy.md](privacy.md): data locations, cloud/local AI flow, secrets, logs,
  retention/deletion, browser storage, threat model.
- [limitations.md](limitations.md): the blunt list repeated below.
- [evaluation.md](evaluation.md): artifact map and reproduction commands.

## P9-7 — release checks

### Fresh install from an empty database

Created `stillroom_fresh_test`, ran `alembic upgrade head`, and started the API
and worker against it. The database reached revision `f1b7c3d9e5a2` with
`vector`, `pg_trgm`, 34 public tables, and the HNSW index. `scripts/fresh_install_check.py`
then passed 10/10 checks: health, CSRF, readiness, register, login, create story,
create chapter, story detail, save with revision increment, and trash. The
disposable database was dropped afterward.

### Restore from a real dump

Took a custom-format `pg_dump` of the scale database (27,664,692 bytes), created
an empty `stillroom_scale_restore_test`, and restored it with
`pg_restore --no-owner --no-privileges`. The restored database reported revision
`f1b7c3d9e5a2`, 1,101 chapters, 6,610 chunks, and the HNSW index. Pointing the
API at it passed 7/7 checks: login, story list, scale story present, story
detail, 1,101 chapters readable, chapter load, and hybrid search. The restored
database was dropped afterward.

The dump was taken after the soak probe existed, which is why those counts are
one chapter/ten chunks above the 1,100/6,600 base fixture.

### Exports at scale

All exports were requested through the running API against the scale database.

| Export | Result | Size | Time |
|---|---|---:|---:|
| Story JSON backup | 1,101 chapters | 6,691,664 bytes | 0.2 s |
| Markdown | full manuscript + wiki | 6,172,381 bytes | 0.4 s |
| DOCX | full manuscript + wiki | 940,035 bytes | 7.0 s |
| EPUB | full manuscript + wiki | 1,687,692 bytes | 14.9 s |
| PDF | full manuscript + wiki | 9,224,809 bytes | 31.0 s |
| Account ZIP | JSON + combined Markdown + README | 1,412,412 bytes | 0.7 s |

The account ZIP contains one story, 1,101 chapters, and the combined Markdown
file. PDF is the slowest export and depends on the local Chrome print engine, as
documented; it is not a streaming export.

### Mixed soak

`scripts/soak_scale.py` ran searches, story detail, and a probe chapter load every
10 seconds against the scale API, with a changed save every 180 seconds. The
worker reindexed each save while the reads continued. The actual run and measured
latencies are in `Docs/eval/soak-30m.json`.

| Operation | n | p50 | p95 | max |
|---|---:|---:|---:|---:|
| Story list | 166 | 18.9 ms | 29.0 ms | 20,933.7 ms |
| Story detail (1,100 chapters) | 166 | 49.9 ms | 151.4 ms | 15,382.0 ms |
| Chapter load | 166 | 10.4 ms | 14.4 ms | 23.0 ms |
| Hybrid search | 166 | 196.5 ms | 700.7 ms | 14,797.2 ms |
| Read before save | 10 | 9.6 ms | 20.1 ms | 20.1 ms |
| Changed save | 10 | 33.2 ms | 82.6 ms | 82.6 ms |

Measured 1,800.0 seconds (30.0 minutes), 166 search/detail/load/list rounds and
10 saves, zero errors. The worker reindexed all 10 saved revisions; the API
returned no 5xx.

Honest reading: the p95 numbers are the useful ones. The maxima on three
operations are one-off outliers (about 15-21 seconds) in an otherwise healthy
run, not normal request cost; they are left in the raw file rather than
trimmed. Search p95 rose from the isolated 191.2 ms benchmark to 700.7 ms under
continuous query embedding plus worker reindexing. That is still responsive for
local single-writer use, but it is not a multi-user SLA. The 24-hour run was
not attempted.

### Final suites

| Suite | Result |
|---|---|
| Backend pytest | **260 passed** in 247.17 s |
| Backend ruff / pyright | clean / 0 errors |
| Backend dependency audit | `pip-audit`: no known vulnerabilities |
| Frontend vitest | **47 passed** (8 files) |
| Frontend tsc / eslint / build | clean / clean / production build succeeded |
| Frontend dependency audit | `npm audit --audit-level=high`: 0 vulnerabilities |
| Phase 8 browser QA | **13/13** |
| Phase 9 storage browser QA | **10/10** |
| Phase 9 canon browser QA | **7/7** |
| Documentation links | 32 checked, 0 missing |

These were run against the production build on the release tree, with a fresh
native API process, one worker, and Ollama available for the canon drill. The
earlier Phase 7 writing/export/accessibility run remains **85/85**; Phase 9 did
not change those flows. Docker and GitHub Actions were not run.

## Deliberate limits and follow-ups

- **No 24-hour soak.** Do not describe this release as one. A multi-hour soak with
  provider-backed models and multiple writers is the follow-up.
- **The corpus is synthetic.** It proves structure, size, and latency; it does not
  prove extraction or retrieval quality on JJK, One Piece, or any other real
  fiction.
- **Docker/Compose and GitHub Actions are unexecuted artifacts here.** Docker is
  not installed on this machine; CI must run once on GitHub before it is trusted.
- **Single API, single worker.** Multi-worker queue behavior and multi-user load
  are not proven.
- **HNSW is approximate.** Recall 1.0 came from a clustered synthetic benchmark;
  another corpus can do worse.
- **Scale API numbers are single-machine samples**, not an SLA. Cold model load
  can add seconds to the first search.
- **The full local-embedding import was extrapolated**, not run end to end; the
  synthetic-vector import and the 10-chapter sample were measured.

## Tag

`phase-9-complete` points at the release commit containing this page, the fixed
restore verifier, the release scripts, and the Phase 9 documentation. The tree,
not an individual benchmark run, is the artifact.
