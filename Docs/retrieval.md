# Retrieval v2

Retrieval answers "where did I say X?" without an LLM in the loop. It is the
foundation for the find-in-story panel and for continuity evidence.

## Architecture

1. **Chunks.** `services/chunking.py` detects scenes, splits on sentence
   boundaries into 1,200–2,400 character chunks (roughly 300–600 tokens), and
   carries a 12% overlap plus exact start/end lines.
2. **Index.** `story_chunks` stores the scene text, a generated `text_search`
   tsvector, entity ids, content hash, and a 768-d embedding. GIN indexes cover
   full-text and entity arrays; trigram indexes cover entity names and aliases.
3. **Three candidate lists, one per request:**
   - HNSW vector scan, top 30 (`ef_search=400`, relaxed iterative scan);
   - `websearch_to_tsquery`, top 30;
   - entity name/alias lookup plus entity-array overlap, top 10.
4. **Weighted reciprocal rank fusion.** `RRF_K = 60`, weights
   `[8.0, 0.5, 0.2]` (vector, lexical, name). Equal weights and a lexical-heavy
   variant both ranked worse on the labelled set.
5. **Post-fusion.** Adjacent chunks from the same scene merge, the per-chapter
   cap is 3, and the caller receives at most `limit` hits (default 10).
6. **Entity-first context.** `build_entity_context` emits accepted facts and
   relationships for the entities in the scene before any prose, so an old fact
   survives even when its passage is far away. The context budget is enforced
   with `approximate_tokens`; no query is issued per scene.
7. **Cache.** An in-memory TTL/LRU keyed by story, query, filters, limit and a
   cheap index version; invalidated by new chunks or changed facts.

## Evaluation

Label set: 70 questions over the 12-chapter *Lantern Coast* manuscript
(`backend/eval/datasets/stillroom.json`).

| Metric | Vector-only baseline | Hybrid v2 |
|---|---:|---:|
| recall@5 | 0.9857 | **1.0000** |
| recall@10 | 1.0000 | 1.0000 |
| MRR | 0.7667 | **0.7674** |
| nDCG@10 | 0.8254 | **0.8259** |
| p50 | 122.98 ms | 142.75 ms |
| p95 | 148.68 ms | 176.24 ms |

Raw reports: `Docs/eval/baseline.json`, `Docs/eval/hybrid.json`. The hybrid
gain is small because the 12-chapter label set is easy for dense retrieval;
lexical and name signals matter most on aliases and exact phrases.

### Embedding bake-off

| Model | dims | recall@5 | MRR | nDCG@10 | p50 | VRAM |
|---|---:|---:|---:|---:|---:|---:|
| nomic-embed-text (kept) | 768 | 0.9857 | 0.7667 | 0.8254 | 41.0 ms | 308 MB |
| qwen3-embedding:0.6b | 768 | 0.9857 | 0.7888 | 0.8384 | 272.6 ms | 2,261 MB |
| bge-m3 | 1024 | 1.0000 | 0.8195 | 0.8644 | 377.1 ms | 633 MB |

BGE-M3 is the quality leader but roughly 7.6× slower here. Nomic stays until
a multilingual manuscript or a GPU makes the trade worthwhile. See
`Docs/embedding-decision.md` for the switch procedure.

## Latency at 10k chunks

Measured on the local machine with Ollama `nomic-embed-text:latest`, exact
vector scan, a retained 10,000-chunk story, `pg_prewarm`, and a 250 ms gap
between queries (an interactive pace, not a saturated loop):

| Stage | p50 | p95 |
|---|---:|---:|
| query embedding | 109 ms | 120 ms |
| vector scan | 256 ms | 291 ms |
| lexical | 2 ms | 4 ms |
| **end-to-end search** | **381 ms** | **437 ms** |

The table is 66 MB. The retrieval SQL stage stays under 300 ms at p95; the
end-to-end request does not, because query embedding adds ~110 ms on this CPU.
The acceptance target was therefore only partially met at 10k with the exact
scan (see `Docs/phase-5-acceptance.md`). Phase 9 replaced the exact scan with
HNSW and measured the 1M-word/6,600-chunk story at search p50 135.5 ms / p95
191.2 ms; see `Docs/scale-report.md`.

Reproduce:

```bash
cd backend
uv run python -m app.eval.bench_retrieval --chunks 10000 --queries 1 --keep
uv run python -m app.eval.bench_retrieval --measure-only --keep \
  --chunks 10000 --queries 50 --out ../Docs/eval/latency-10k.json
```

### HNSW decision

Phase 5 removed HNSW after a 10k benchmark. Phase 9 reran the comparison at
10k, 50k and 100k chunks with clustered noisy vectors and a known exact top-30:

| Chunks | Exact p50 / p95 | HNSW ef400 p50 / p95 | Recall@30 |
|---:|---:|---:|---:|
| 10,000 | 26.3 / 56.7 ms | 3.0 / 4.2 ms | 1.0 |
| 50,000 | 385.4 / 668.6 ms | 3.4 / 5.4 ms | 1.0 |
| 100,000 | 1,460.4 / 1,598.1 ms | 2.2 / 4.8 ms | 1.0 |

`ef_search=200` lost 20% of the exact top-30 at 100k; 400 and 800 both held
recall at 1.0 in this benchmark. The production setting is 400 with
`hnsw.iterative_scan=relaxed_order`, so a selective story/arc filter keeps
filling the list. The global index is
`ix_story_chunks_embedding_hnsw` (migration `f1b7c3d9e5a2`). It roughly doubles
chunk storage at 100k and blocks writes while it builds. This requires pgvector
0.8 or newer for iterative scanning; `Docs/versions.md` records the tested
version. Full numbers and limitations are in `Docs/scale-report.md`.

## Tuning decisions

- Chunk size: 1,200–2,400 characters, sentence boundaries, 12% overlap.
- RRF `k`: 60; weights `[8.0, 0.5, 0.2]`.
- Per-chapter cap: 3; default result limit: 10.
- Lexical query joins distinctive terms with **AND**. OR matched almost every
  synthetic chunk and produced 500–650 ms FTS spikes at 10k. The vector list
  carries broad recall; AND keeps lexical precise.
- Reranker: not enabled. The eval set is small and the local cross-encoder
  would add latency without a measured gain.

## Known failure modes

- **Epithets.** "the lighthouse keeper" only retrieves if that phrase is an
  alias or appears in the text; an unlisted epithet is invisible to the name
  retriever.
- **Short common words.** AND semantics can drop a lexical hit when one query
  term is absent; vector recall usually recovers it.
- **Entity mentions.** `extract_mentions` matches whole aliases. Pronouns and
  partial names do not attach the entity to the chunk.
- **Shared table.** Every story shares `story_chunks`; the vector scan filters
  by `story_id` but reads rows for other stories.
- **Cache freshness.** Up to 60 seconds of staleness after a fact edit unless
  the index version changes.
- **Continuity prompt audit.** Scans do not yet persist the prompt version/hash
  (the P5-4 requirement); `ContinuityScan` records revision and counts only.
