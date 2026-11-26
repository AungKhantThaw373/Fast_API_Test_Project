# Evaluation guide

This page explains what each benchmark measures, how to reproduce it, and what it
does not prove. Numbers live next to the harness where possible; the main Phase 9
summary is [scale-report.md](scale-report.md).

## Evidence map

| Artifact | Measures | Does not prove |
|---|---|---|
| `Docs/eval/baseline.json` | Exact-vector retrieval baseline on the seeded evaluation set | Production speed at larger scale |
| `Docs/eval/hybrid.json` | Hybrid vector + lexical + name retrieval quality/latency | Literary judgment or answer correctness |
| `Docs/eval/bakeoff.json` | Embedding-model bake-off | That the winner is best for every corpus |
| `Docs/eval/local-models.json` | Local chat-model structured-output behavior | General reasoning quality |
| `Docs/eval/latency-10k.json` | End-to-end retrieval latency at 10k chunks | 1M-word story latency (different corpus) |
| `Docs/eval/hnsw-10k-50k-ef400.json` | HNSW vs exact at 10k/50k, ef400 | Recall on arbitrary real-world vectors |
| `Docs/eval/hnsw-100k.json` | HNSW ef200/400/800 + iterative scans at 100k | Runtime behavior after deletes/updates |
| `Docs/eval/scale-api-exact.json` | API latency on the 1.1M-word fixture before HNSW | A repeatable SLA |
| `Docs/eval/scale-api-hnsw.json` | API latency on the same fixture with HNSW | Multi-user concurrency |

## Retrieval evaluation

```bash
cd backend
uv run python -m app.eval.bench_retrieval --chunks 10000 --queries 1 --keep
uv run python -m app.eval.bench_retrieval --measure-only --keep \
  --chunks 10000 --queries 50 --out ../Docs/eval/latency-10k.json
```

The harness seeds a deterministic story/chunk set, runs exact and hybrid
retrieval, and writes JSON. Recall is measured against known relevant chunks in
that set. It is a retrieval-quality check, not an end-to-end answer-quality
check.

## HNSW benchmark

```powershell
# Disposable database; does not touch stillroom.
$env:PGPASSWORD = "death373"
createdb -U postgres -h 127.0.0.1 stillroom_hnsw_test
cd backend
uv run python ../scripts/bench_hnsw.py --sizes 10000 50000 100000 --ef-search 200 400 800 --out Docs/eval/hnsw-100k.json
```

The script creates its own `bench_chunks` table in `stillroom_hnsw_test`,
inserts 768-dimensional clustered noisy vectors (two stories, 50/50), builds
m=16/ef_construction=64 indexes, compares exact filtered top-30 with HNSW, and
reports recall plus p50/p95 over repeated query points. The synthetic clustering
is deliberate: uniform random vectors made recall look worse than a real
embedding distribution.

Measured result:

| Chunks | Exact p50 / p95 | HNSW ef400 p50 / p95 | Recall@30 | Build |
|---:|---:|---:|---:|---:|
| 10,000 | 26.3 / 56.7 ms | 3.0 / 4.2 ms | 1.0 | 14.3 s |
| 50,000 | 385.4 / 668.6 ms | 3.4 / 5.4 ms | 1.0 | 59.2 s |
| 100,000 | 1,460.4 / 1,598.1 ms | 2.2 / 4.8 ms | 1.0 | 112.2 s |

At 100k, ef200 recall was 0.80 and ef400/800 were 1.0. Production uses
`ef_search=400` with relaxed iterative scanning. This is a synthetic benchmark:
it establishes the order of magnitude and the recall trade-off, not a guarantee
for every corpus.

## Scale API measurement

```powershell
# Terminal 1: API against the scale database only.
$env:DBNAME = "stillroom_scale_test"
cd backend
uv run uvicorn app.app:app --host 127.0.0.1 --port 8001

# Terminal 2: measure.
cd C:\Users\ACER\OneDrive\Desktop\AI
uv run --project backend python scripts/measure_scale_api.py --base http://127.0.0.1:8001 --iterations 20 --save
```

Each benchmark uses a unique query nonce so a warm plan/cache is not mistaken for
a cold run. The script also creates and deletes a probe chapter to measure a
changed save. Final HNSW numbers at 6,600 chunks:

| Operation | p50 | p95 |
|---|---:|---:|
| Story list | 6.2 ms | 7.1 ms |
| Story detail | 41.0 ms | 112.5 ms |
| Chapter load | 5.0 ms | 8.3 ms |
| Hybrid search | 135.5 ms | 191.2 ms |
| Changed save | 29.9 ms | 71.7 ms |

The first search after idle took about 4.66 s (model/page cache warm-up). Search
stages: query embedding 69.6 ms, vector 20.2 ms, lexical 2.5 ms, name 1.7 ms.
The p95 search number is not a 300 ms claim; it is a measured local result with a
local embedding model and one writer.

## Import measurement

Full synthetic import: 1,100 chapters, 6,600 chunks, 27.9 s wall time, 36,920
words/s, 0 failed chapters. Database: 58 MB before HNSW, 92 MB after (69 MB of
chunk relations, 26 MB HNSW index). Local embedding was measured on a 10-chapter
sample only (11.8 chunks/s); the full 6,600-chunk local run was extrapolated, not
executed. See [scale-import.md](scale-import.md).

## Test and browser evidence

- Backend: `uv run pytest -q` -> 260 passed at P9-5.
- Frontend: `npm run test` -> 47 vitest tests.
- Lint/types: ruff, pyright, eslint, `tsc --noEmit`, `next build`.
- Browser: Phase 7 (85 checks), Phase 8 (13), Phase 9 storage (10), plus the
  Phase 9 canon coverage drill and release QA. These are Chromium/Playwright
  checks against a production build.

## What would strengthen this

1. Run extraction and retrieval quality on a real, licensed corpus and have a
   writer grade a sample.
2. Repeat the API measurement across several runs and machines, reporting
   variance, not one sample.
3. Run a genuine multi-hour soak with a real worker and real model calls.
4. Test concurrent writers and a second API replica.
5. Pin and run the Compose stack and CI workflow.