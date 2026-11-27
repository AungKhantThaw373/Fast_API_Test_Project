# Embedding decision

Phase 5 keeps **`nomic-embed-text:latest` at 768 dimensions** for the story
index. It is the best speed/quality trade-off on the English evaluation set,
and it keeps the existing 768-dimension `story_chunks.embedding` column and
hybrid retrieval proof valid.

## What was measured

The bake-off held the corpus and chunking constant: the 12 scene chunks of
“The Lantern Coast”, the 12-chapter evaluation story, and all 70 labelled
questions in `backend/eval/datasets/stillroom.json`. Only the embedding model
changed. Quality uses binary evidence labels, the same metric code as
`python -m app.eval.run`.

Warm latency is one query embedding plus an exact cosine scan over the 12
vectors. Cold start is the first document batch, including model load. Storage
is the raw float32 payload for the test corpus; the 10k estimate extrapolates
that payload and excludes PostgreSQL row and index overhead. Reproduce with:

```bash
cd backend
uv run python -m app.eval.bakeoff
```

The raw per-question results are in `Docs/eval/bakeoff.json`.

## Results

| Model | Dims | Recall@5 | Recall@10 | MRR | nDCG@10 | Warm p50 | Warm p95 | Cold start | VRAM | Raw storage, 10k chunks |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `nomic-embed-text:latest` | 768 | 0.9857 | 1.0000 | 0.7667 | 0.8254 | 41 ms | 60 ms | 4.13 s | 308 MB | 29.3 MiB |
| `qwen3-embedding:0.6b` | 768 | 0.9857 | 1.0000 | 0.7888 | 0.8384 | 273 ms | 376 ms | 3.08 s | 2,261 MB | 29.3 MiB |
| `bge-m3:latest` | 1024 | 1.0000 | 1.0000 | 0.8195 | 0.8644 | 377 ms | 457 ms | 5.67 s | 633 MB | 39.1 MiB |

All three models use the same documents and questions. Nomic and Qwen were
requested at 768 dimensions; BGE-M3 uses its native 1024 dimensions. The
quality numbers for Nomic match the committed vector-only baseline
(`0.9857 / 1.0 / 0.7667 / 0.8254`), which is the expected cross-check.

## Decision

Keep Nomic. BGE-M3 is the quality leader, but it adds 1.4 recall@5 points,
5.3 MRR points, and 3.9 nDCG@10 points while making the embedding step about
7.6× slower at p95 than Nomic. Qwen3 adds 1.3 nDCG points for about 6.3× the
p95 latency and 2.2 GB of resident memory. Neither gain is large enough to
justify a new 1024-dimension column, a full reindex, and a slower search
experience on this machine.

Nomic is also the only candidate already wired into the running index, so this
choice avoids mixing models in one table. The hybrid pipeline remains the main
quality lever: it beats vector-only on the same labels
(`Docs/eval/hybrid.json`).

## When to revisit

- **Bengali or mixed-language manuscripts.** Re-run the same bake-off with
  language-matched questions; Qwen3 or BGE-M3 is likely to win clearly.
- **A GPU with enough headroom.** BGE-M3 query latency may fall enough to make
  its quality edge cheap. Measure again; do not reuse these CPU-era numbers.
- **A larger labelled set.** Twelve chunks are enough to compare models, but
  not enough to detect small differences. Re-run after the corpus grows.

If the choice changes, do it as a separate migration and task: add a new
`vector(1024)` column or table, reindex with the new `embedding_model`, shadow
run the eval, switch reads, then drop the old column. Never put two dimensions
in one embedding column.

## Known limitations

- The bake-off measures retrieval over the evaluation story only; it does not
  measure indexing throughput.
- Warm latency excludes SQL and fusion. Compare it to the hybrid p95 in
  `Docs/eval/hybrid.json` only as an embedding-cost component.
- The query instruction for Qwen3 is tuned for story-memory retrieval, not a
  general benchmark, so the result is deliberately application-specific.
- Character-level multilingual quality is untested; the evaluation set is
  English.
