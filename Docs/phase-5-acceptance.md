# Phase 5 acceptance

Phase 5 delivered retrieval v2, an evaluation harness, a chunk index, a
find-in-story UI, and an embedding bake-off. One acceptance target remains
open: end-to-end p95 at 10k chunks.

## Checklist

- [x] **Eval harness runs from a single command.**
  `cd backend && uv run python -m app.eval.run --mode hybrid` runs the
  labelled retrieval set; `--continuity --continuity-judge ollama` adds the
  30-case contradiction set.
- [x] **Baseline and final results are committed.**
  `Docs/eval/baseline.json` and `Docs/eval/hybrid.json`.
- [x] **Hybrid retrieval beats vector-only on the labelled set.**
  recall@5 0.9857 → 1.0, MRR 0.7667 → 0.7674, nDCG@10 0.8254 → 0.8259.
- [ ] **Retrieval p95 <300 ms at 10k chunks locally.**
  The retrieval SQL stage is p95 291 ms (vector; lexical adds ~4 ms), but the
  end-to-end request is p95 437 ms because query embedding adds ~110 ms. The
  exact scan is the bottleneck; a global HNSW experiment was slower and was
  removed. See `Docs/retrieval.md` for numbers and the reproduction command.
- [x] **Entity facts are retrieved without embedding the whole chapter.**
  `build_entity_context` reads facts/relationships by entity id and enforces
  the token budget; `backend/tests/test_retrieval.py` covers it.
- [x] **No query per scene.**
  One vector, one lexical, and one name query per search request.
- [x] **Context budget is enforced.**
  `approximate_tokens` trims fact context before prose.
- [x] **Embedding choice is documented.**
  `Docs/embedding-decision.md`; Nomic kept, migration path to 1024 dims.

## What shipped

| Task | Commit |
|---|---|
| P5-1 evaluation harness | `phase-5` history |
| P5-2 sentence-aware chunks | `90bb47e` |
| P5-3 FTS/trigram indexes | `bc22a5c` |
| P5-4 hybrid retrieval + entity context | `b37f1a4` |
| P5-5 embedding bake-off | `aa032a0` |
| P5-6 find-in-story UI | `60be11c` |
| P5-7 tuning and docs | this commit |

## Deliberately left out

- HNSW/IVFFlat: measured, not adopted (no stable gain at 10k; story filter
  makes a global graph awkward).
- Cross-encoder reranker: no measured gain worth the latency on this set.
- Persisting prompt version/hash on continuity scans: still open from P5-4.
- 50k/100k latency runs: 10k already misses the end-to-end budget; a 50k
  embedding pass costs roughly ten minutes and would not change the decision.
- Wiring `build_entity_context` into the continuity prompt: the service and
  tests exist, but the old `retrieve_evidence` path still feeds the judge.

`phase-5-complete` is **not** tagged while the p95 box is open.
