# Scale fixture import

The Phase 9 corpus is generated, not copied from any published work. The
generator and importer are tracked; the generated files under `data/` are not.

## Generate

```powershell
cd C:\Users\ACER\OneDrive\Desktop\AI
uv run --project backend python scripts/generate_fixture.py
```

Defaults: 1,100 chapters, about 1,000,000 words, seed `20261125`, 100
planted contradictions, 100 near-miss quotes, 750 entities, and 70 threads.
The full fixture used for Phase 9 has 1,029,590 words and 6,600 chunks after
sentence-aware chunking.

## Import into an isolated database

The importer refuses the real `stillroom` database. Use the scale database
and keep the API pointed at it only for measurements.

```powershell
$env:PGPASSWORD = "death373"
createdb -U postgres -h 127.0.0.1 stillroom_scale_test
$env:DBNAME = "stillroom_scale_test"
cd backend
uv run alembic upgrade head
uv run python ../scripts/import_fixture.py --migrate
```

`--force` deletes the synthetic story and imports from chapter 1. Without it
the importer reads `data/scale-import-state.json` and skips chapters already
committed. Each chapter is one transaction, so a killed process loses at most
the chapter in flight.

Useful controls:

| Flag | Effect |
|---|---|
| `--limit N` | import at most N new chapters this run |
| `--pause-file PATH` | stop before the next chapter while the file exists |
| `--embedding-mode ollama` | use the configured local embedding model |
| `--target-tokens-per-second N` | sleep between chapters to cap local embedding throughput |
| `--fail-at N` | test failure isolation by failing one chapter |

Ctrl-C is the same graceful pause. A failed chapter is recorded in the state
file and retried on the next run; later chapters continue.

## What it writes

- one story owned by `scale@example.com` (password `scale fixture only`, local
  only; never deploy this database)
- 12 arcs, 1,100 chapters and their `story_chunks`
- 750 entities with 1,350 aliases and 100 accepted facts
- 70 threads

Synthetic 768-dimension unit vectors are the default. They are deterministic
and keep the exact-vector scan honest for latency tests, but they carry no
meaning: do not use this fixture to judge retrieval relevance. Use
`--embedding-mode ollama` to measure real local embedding time.

`story_chapters.indexed_embedding_model` records the configured model so the
API does not immediately queue 1,100 reindex jobs. Each `story_chunks` row
still records `synthetic-scale-768` when synthetic vectors were written, so the
origin is visible.

## Measurements on this machine

Full synthetic import (1,100 chapters, 6,600 chunks):

| Metric | Value |
|---|---|
| Wall time | 27.9 s |
| Throughput | 36,920 words/s |
| `story_chunks` growth | 42.2 MB |
| Database size after import | 58 MB |
| Failed chapters | 0 |

Local `nomic-embed-text` sample (10 chapters, 60 chunks): 5.07 s, or 11.8
chunks/s. Extrapolated naively, 6,600 chunks would take about 9 minutes, but
that is an estimate, not a measured full run. The importer reports measured
words per second for whichever mode it ran.

Failure isolation and pause were exercised against a disposable database:
chapter 2 was forced to fail, the run recorded it and imported the next
chapters, a resume filled only the missing chapter, and a pause file stopped
the next run before any chapter. This is a script-level test, not a claim that
every provider timeout behaves identically.