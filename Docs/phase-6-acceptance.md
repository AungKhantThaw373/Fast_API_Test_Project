# Phase 6 acceptance

Phase 6 makes the writing app work with a free local model, keeps cloud
providers optional, and accounts for every AI call. Verification below was run
on the native PostgreSQL instance, one durable worker, and Ollama with
`qwen3:4b-instruct` + `nomic-embed-text`.

## Checklist

- [x] **The app works without a cloud key.**
  AI settings accept `provider=ollama`, a base URL, and a model name with no
  API key. `tests/test_ollama_structured.py` covers the settings path; the
  browser QA answers a question through Ollama.
- [x] **External providers stay optional.**
  Ollama is the default when no key is configured. Provider-backed checks
  require the per-story `external_analysis_enabled` toggle, which defaults to
  false; local calls do not require a key.
- [x] **Extraction is incremental.**
  `scene_meta.last_extracted_hash` stores a hash per scene; a rescan sends only
  changed scenes. `tests/test_extraction.py::test_incremental_extraction_skips_unchanged_scenes`
  asserts zero calls.
- [x] **Deterministic checks run before the model and cost nothing.**
  `app/services/deterministic.py` checks accepted ages, eye/hair colour,
  titles, and POV in complete sentences. Findings carry
  `source=deterministic` and a rule id; near misses stay silent.
  `tests/test_deterministic.py` covers both the findings and the quiet cases.
- [x] **Continuity is per scene, with evidence attached.**
  `scan_chapter` retrieves evidence once, embeds each scene, and sends one
  prompt per scene with the closest earlier evidence. A chapter with no earlier
  evidence never calls the model. Findings carry a scene index and the exact
  earlier evidence id. `tests/test_continuity_retrieval.py` checks three scenes
  produce three prompts and three progress updates.
- [x] **Scans are durable jobs with progress and cancel.**
  `POST /stories/chapters/{chapter_id}/scan-job`, `GET /jobs/{job_id}`, and
  `POST /jobs/{job_id}/cancel`; the worker runs the scan, reports scene counts,
  and records `cancelled` without saving a partial scan. The studio stores the
  job id in `sessionStorage` and resumes polling after a reload.
  `tests/test_jobs.py` covers queued/running cancellation.
- [x] **Every AI call is accounted for.**
  `ai_usage` records provider, model, purpose, tokens, duration, and estimated
  cost for Ollama and cloud calls. `GET /stories/{story_id}/ai-usage` returns
  the month grouped by purpose.
- [x] **The budget blocks cloud calls, not local ones.**
  `Story.monthly_ai_budget` defaults to 0. A cloud call with no budget returns
  402; Ollama remains free. `tests/test_ai_usage.py` covers both paths.
- [x] **Continuity scans are versioned.**
  Scans store prompt version `continuity-v2`, model, schema version, context
  hash, and scene totals/done/failed so two scans are comparable.
- [x] **Ask the story cites the manuscript or refuses.**
  `POST /stories/{story_id}/ask` returns an answer plus citations whose quotes
  are validated against the cited chunk. Empty retrieval refuses before
  embedding or calling a model. `tests/test_ask_story.py` covers citations,
  fabrication rejection, refusal, ownership, and provider failures.
- [x] **Provider failures are readable.**
  Timeouts return 504, an unreachable Ollama or cloud endpoint returns 503 with
  a start/check-base-URL message, and no raw traceback reaches the browser.
  `tests/test_ollama_structured.py` covers the unreachable case.
- [x] **Browser flows survive a refresh.**
  `frontend/scripts/phase6-qa.mjs` runs 8 checks against the production build:
  usage panel, cited answer, command-palette focus, scan job tracking, reload
  resume, scan completion, and no page errors.
- [x] **The suite is clean.**
  178 backend tests pass; ruff and pyright are clean. 31 frontend tests pass;
  eslint has one existing React Compiler warning (no errors), and
  `tsc --noEmit` and `next build` pass.

## What shipped

| Task | Where |
|---|---|
| P6-1 local model + structured output | `services/ai_service.py`, settings UI |
| P6-2 incremental extraction | `services/extraction.py`, migration `f4a1c9d2e6b7` |
| P6-3 deterministic + per-scene continuity | `services/deterministic.py`, `services/continuity.py` |
| P6-4 durable scans | `services/jobs.py`, `worker.py`, `routes/jobs.py` |
| P6-5 usage ledger + budget | `services/ai_usage.py`, `routes/ai_usage.py` |
| P6-6 ask the story | `services/ask_story.py`, `routes/ask.py` |
| P6-7 QA and documentation | `scripts/phase6-qa.mjs`, this file |

## Running the acceptance flows

1. Start PostgreSQL, then `uv run alembic upgrade head` in `backend/`.
2. Start Ollama and `ollama pull qwen3:4b-instruct` plus
   `ollama pull nomic-embed-text`.
3. `cd backend && uv run uvicorn app.app:app --port 8000` and, in a second
   terminal, `uv run python -m app.worker` (exactly one worker).
4. `cd frontend && npm run build && npx next start`.
5. `cd frontend && node scripts/phase6-qa.mjs` (or `make qa-phase6`).

The QA script creates its own user, story, and two chapters, then deletes
nothing; use a test database if the rows should not remain.

## Deliberately left out

- **Timeline arithmetic and duplicate-spelling rules.** The manual lists them
  as possible deterministic checks; only age, eye/hair colour, titles, and POV
  shipped. Date arithmetic needs a date model the manuscript does not yet
  provide, and spelling variants are noisy without an approved glossary.
- **A separate first-use confirmation dialog for cloud calls.** The existing
  per-story `external_analysis_enabled` toggle is the opt-in. Adding a second
  modal would duplicate the same decision.
- **Skipping a whole scene because a rule already found one conflict.** Rules
  cover four narrow categories; a scene can contain both a rule finding and a
  semantic contradiction, so the semantic pass still runs for every scene that
  has earlier evidence.
- **An automated "network cable unplugged" test.** Unit tests stub every
  provider and the browser run uses local Ollama; the 503 path is tested with a
  transport error rather than by disabling the host network.
- **Guaranteed recall from a 4B local model.** Schema bounds and retries stop
  malformed JSON from failing a scan, but a tiny model will miss subtle
  contradictions. The UI treats findings as suggestions, not canon.