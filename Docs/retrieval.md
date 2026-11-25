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
   - exact vector scan, top 30;
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
The acceptance target is therefore only partially met (see
`Docs/phase-5-acceptance.md`). 50k was not run because a full embedding pass
would take roughly ten minutes and the 10k result already misses the
end-to-end budget.

Reproduce:

```bash
cd backend
uv run python -m app.eval.bench_retrieval --chunks 10000 --queries 1 --keep
uv run python -m app.eval.bench_retrieval --measure-only --keep \
  --chunks 10000 --queries 50 --out ../Docs/eval/latency-10k.json
```

### HNSW decision

A global HNSW index was built and measured, then removed. With a story filter
on a shared table it either returned too few rows or scanned nearly the whole
graph; on the benchmark corpora it did not beat the exact scan consistently.
An exact top-N scan over 10k rows is acceptable at the SQL layer, and a
story-scoped partial index is not expressible for arbitrary story ids in one
migration. Revisit if a single story exceeds ~50k chunks or a GPU moves the
embedding cost off the critical path.

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
