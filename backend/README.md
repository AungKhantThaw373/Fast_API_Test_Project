# Stillroom API

FastAPI backend for Stillroom's Writing studio and Editing file library. It stores accounts, chapters, reviewable Story Bible suggestions, scene embeddings, continuity scans, intentional flags, and uploaded draft files organized into private folders.

## Local setup

1. Create a PostgreSQL database with the pgvector extension available, then copy `.env.example` to `.env` and fill in the PostgreSQL and JWT values.
2. Install Ollama and pull the embedding model: `ollama pull nomic-embed-text`. To compare retrieval quality, also pull `qwen3-embedding:0.6b` and set `EMBEDDING_MODEL=qwen3-embedding:0.6b` in `.env`.
3. Install Python dependencies with `uv sync`.
4. Apply the schema: `uv run alembic upgrade head`.
5. Start the API with `uv run uvicorn main:app --reload --host 127.0.0.1 --port 8000`.

The migrations create the pgvector extension, a cosine HNSW index, the story tables, and the Editing file-library tables. Draft uploads are stored in PostgreSQL, with a 25 MB per-file limit. The configured embedding model must return 768 dimensions to match the database column. Changing embedding models or dimensions later requires a deliberate reindex and migration.

## AI provider settings and privacy

Local story memory uses Ollama embeddings. The default `nomic-embed-text` model is small and runs locally; Ollama selects GPU acceleration when available. Chapter indexing runs locally after edits and reuses embeddings for unchanged scenes. For a quality comparison, `qwen3-embedding:0.6b` is also supported and requested at 768 dimensions to match pgvector; Nomic stays the speed-oriented default. If `EMBEDDING_MODEL` changes, startup queues chapters for a full reindex and continuity retrieval ignores vectors made by another model until that work finishes. Let that reindex finish before running a continuity scan.

Continuity scans stay off until the writer enables analysis in a story. Story Bible suggestions are a separate, manual operation: use **Scan range** in the Story Bible pane. Only chapters whose latest revision has not been scanned are queued, and **Re-scan unchanged chapters** explicitly overrides this. Editing and local indexing never call the text-generation provider for Bible suggestions. The range scan page reports completion and provider errors.

### Scan speed

A range scan handles chapters in parallel, up to `AI_MAX_CONCURRENT_REQUESTS` provider requests at once (default 3), because extraction runs in the background instead of inside the browser request. Each extraction uses `STORY_BIBLE_TIMEOUT_SECONDS` (default 180) rather than the 90 second interactive limit, so a slow model finishes instead of being abandoned mid-chapter. Five chapters therefore take about two waves instead of five serial waits.

The provider is usually the limit. A model can take 25-45 seconds to answer even a 200-character chapter, and `[AI] latency` in the log reports that cost separately from everything the app does. If scans stay slow, choose a faster model in Settings → AI; the manuscript is unaffected by the choice.

Database connections are pooled (`pool_size=5`). This matters with a hosted database: one fresh connection per session cost about a second against a remote region and dominated scan time before the provider was even contacted.

A chapter that hits a rate limit (`429`) or a malformed tool call (`tool_use_failed`) is retried once — after the provider's `Retry-After` for a rate limit — before the scan records an error. Other 4xx responses are not retried; the provider's own message is stored on the chapter and shown in the scan status, so a rejected model can be diagnosed without guessing.

Provider throughput still sets the floor. Groq's free tier, for example, is limited by tokens per minute: one 16k-character chapter is roughly 4k input tokens, so several full chapters at once can exhaust the minute's budget. On that tier use `AI_MAX_CONCURRENT_REQUESTS=2` (or `1`), or let the automatic retry spread the work out.

Writers can configure their own API key and model from **AI settings**. Supported hosts include OpenRouter, OpenAI, Anthropic, Google Gemini, Cohere (native and OpenAI-compatible), DeepSeek, Groq, Mistral, Together AI, Fireworks AI, and Cerebras. The custom option accepts an OpenAI-compatible API base URL. Model IDs can be entered manually so newly released models can be used without an app update.

Personal API keys are encrypted in PostgreSQL and are never returned to the browser after saving. Set `AI_SETTINGS_ENCRYPTION_KEY` to a long, private, stable secret for key encryption; if omitted, the backend derives an encryption key from `JWT_SECRET`. Keep the encryption key stable: changing it makes saved provider keys unreadable and users will need to enter them again. `OPENROUTER_API_KEY` remains an optional workspace default for accounts that have not saved a personal provider.

When analysis runs, the selected provider receives the current chapter text and retrieved earlier passages. Review that provider's data-retention policy before enabling analysis for confidential manuscripts. The scan endpoint compares a chapter only with indexed chapters whose number is lower and waits until every earlier chapter is indexed.

The analysis prompts request factual review and structured flags only. They do not return replacement paragraphs or generated manuscript prose. A reported conflict must quote at least 10 characters from the draft line and at least 15 characters from the earlier passage, so single words and bare names cannot become findings; repeats of the same claim collapse to one, and at most three findings per line are kept. Only one continuity check runs per chapter at a time, so a second press while a slow model is still answering returns `409` instead of starting a duplicate request.

Keep `.env` private. For deployment, set `COOKIE_SECURE=true` behind HTTPS and use strong, private JWT and AI encryption secrets.

## Reading the AI logs

Every model and embedding step writes one line per event through the `stillroom.*` loggers, so `stillroom` is a useful filter. Fields are `key=value` for scanning and grepping:

```
22:02:31 INFO  stillroom.ai          [32b42f] start     purpose=story_bible chapter=23546809 rev=1 provider=openrouter model=... protocol=openai schema=entries system_chars=678 prompt_chars=108 timeout=90s
22:02:31 INFO  stillroom.ai          [32b42f] done      purpose=story_bible chapter=23546809 rev=1 status=200 latency=0.03s total=1.30s keys=entries
22:02:31 INFO  stillroom.ai          [32b42f] usage     in_tokens=123 out_tokens=45 total_tokens=168 cached_tokens=64
22:02:31 INFO  stillroom.index       [bible] parsed    chapter=23546809 revision=1 candidates=2 provider_elapsed=2.55s
22:02:33 INFO  stillroom.index       [bible] done      chapter=23546809 revision=1 candidates=2 added=1 updated=0 skipped_invalid=1 elapsed=4.09s
```

How to read it:

- `latency` is only the provider request; `queue` is time spent waiting for a free provider slot (`AI_MAX_CONCURRENT_REQUESTS`) and, on OpenRouter, the 4 second minimum interval. A slow scan is almost always `latency`, which depends on the selected model and its provider queue.
- `total` is the whole call including queueing and response parsing.
- `schema=entries` / `schema=findings` shows which structured output was requested. Bible extraction asks only for `entries` and continuity only for `findings`, so the model is never paid to fill an unused array.
- `[bible] candidates` is what the model returned, and `added` / `updated` / `skipped_invalid` (quote not found in the chapter) / `skipped_reviewed` / `skipped_duplicate` show what was kept, which is the quickest quality signal.
- `[continuity] evidence` reports how many earlier passages were retrieved and how many were actually sent.
- `[continuity] done` reports `valid` (after quote and confidence checks), `kept`, and why the rest were dropped: `dropped_short_quote`, `dropped_low_confidence`, `dropped_duplicate`, `dropped_per_line`. A run with no findings is normal; a run with many `dropped_short_quote` means the model tried to cite fragments instead of real evidence.
- `[continuity] busy` means a check for that chapter was already running; the request returned `409` without contacting the provider.
- `[index] done` reports `reused` versus `embedded` scenes; that is local Ollama work and costs no provider tokens. Its elapsed time includes the ~2.5 second autosave debounce.
- `[continuity] reuse` means a stored scan was returned without a provider request. `[continuity] rerun reason=earlier_chapters_edited` means the cache was deliberately bypassed because the evidence changed.
- Timeouts log `timeout` with the wait and limit, and the request fails with `504` and a readable message instead of a traceback. Provider rejections log `rejected` with status, rate-limit source, the provider's own `code` and `provider_message`, and retry-after, so a `400` is explainable rather than just a number.
- `[bible] retry` means a chapter was retried after a rate limit or a malformed tool call; `[bible] failed` is the final outcome after any retry.
- If `[continuity] stored` appears in this log but the browser still reported a failure, the frontend's rewrite proxy cut the response off. Raise `BACKEND_PROXY_TIMEOUT_MS` in the frontend so it exceeds `OPENROUTER_TIMEOUT_SECONDS`.

Full prompts and raw responses are not logged at `INFO` because they contain manuscript text. Set the `stillroom` logger to `DEBUG` to include raw provider responses.
