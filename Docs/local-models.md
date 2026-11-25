# Local models

Phase 6 runs local AI by default. Ollama is the provider, the extraction and
continuity checks use a small quantised chat model, and a larger model is
reserved for explicit deep checks. Nothing in this path sends manuscript text
to a remote service.

## Models

| Role | Model | Disk | Why |
| --- | --- | --- | --- |
| Extraction, continuity, Ask Story | `qwen3:4b-instruct` | 2.5 GB | Fits beside the embedding model in 6 GB VRAM; 38 tok/s on this machine. |
| Deep check (explicit only) | `qwen2.5-coder:7b-instruct-q4_K_M` | 4.7 GB | Stronger instruction following and JSON, but slower and does not fit with the 4B model loaded. |
| Embeddings | `nomic-embed-text:latest` | 274 MB | 768 dimensions, already used by retrieval v2. |

`OLLAMA_CHAT_MODEL` selects the default. `OLLAMA_DEEP_MODEL` is available for a
user-requested deep pass; it is never loaded automatically while the chat model
is resident. `OLLAMA_KEEP_ALIVE=30m` lets Ollama unload the chat model when idle.

## Extraction benchmark

Ten chapters of the sample manuscript, structured output against the Story Bible
schema, temperature 0.1, `num_ctx=8192`. Full records:
`Docs/eval/local-models.json`.

| Model | Cold start | p50 | p95 | Tokens/s (p50) | Schema valid | Exact-quote entries | Peak VRAM |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `qwen3:4b-instruct` | 21.4 s | 16.0 s | 21.4 s | 38.3 | 10/10 | 41/64 (64%) | 3.7 GB |
| `qwen2.5-coder:7b-instruct-q4_K_M` | 47.3 s | 21.0 s* | — | 17.7 | 2/2 | 12/13 (92%) | 4.1 GB |

\* The 7B figures are a two-chapter smoke run, not a full benchmark. They are
kept here because they explain the model split: the 7B is roughly twice as slow
and uses more VRAM, while the 4B is the better default for per-scene extraction.

### What the numbers mean

- **Latency per chapter is not latency per scene.** The benchmark sends a whole
  short chapter in one call. Incremental extraction sends one scene at a time, so
  a long chapter becomes several smaller calls; the per-call prompt is smaller and
  a failed call loses one scene instead of the chapter.
- **Schema validity was perfect.** Ollama structured outputs plus `jsonschema`
  validation held for every call. Quote fidelity is the real quality limit: the 4B
  model paraphrased or joined lines in about a third of its entries. The extractor
  rejects every quote that is not an exact substring, so those entries never reach
  canon. Do not relax that check to raise the entry count.
- **The 7B is more precise but slower.** Use it for a deliberate deep pass, not the
  default save/scan path.

## Running a benchmark

```bash
cd backend
uv run python -m app.eval.local_models --model qwen3:4b-instruct --chapters 10
```

Output goes to `Docs/eval/local-models.json`. The script reports schema validity,
exact-quote usability, latency, tokens per second, and VRAM from `/api/ps`.

## VRAM discipline

- One chat model at a time. The default 4B and the embedding model fit together
  (about 3.7 GB + 0.3 GB on a 6 GB card); the 7B does not fit beside them.
- `structured_ai_json` sends `keep_alive` on every call, so a finished scan does not
  pin the model forever.
- The deep model is opt-in. A continuity or extraction pass must not silently
  upgrade itself to the 7B model.
- If Ollama has to evict the embedding model to load a chat model, retrieval and
  extraction thrash. Keep the default model small enough to avoid that.

## Configuration

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CHAT_MODEL=qwen3:4b-instruct
OLLAMA_DEEP_MODEL=qwen2.5-coder:7b-instruct-q4_K_M
OLLAMA_KEEP_ALIVE=30m
OLLAMA_NUM_CTX=8192
OLLAMA_NUM_PREDICT=1200
```

The readiness check requires both the embedding model and `OLLAMA_CHAT_MODEL` to
be present in `/api/tags`. A missing chat model is a configuration error, not a
silent fallback to another provider.
