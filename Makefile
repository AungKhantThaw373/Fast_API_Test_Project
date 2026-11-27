.PHONY: dev-backend dev-frontend worker worker-once perf test test-frontend qa-wiki qa-phase6 qa-phase7 qa-phase8 qa-storage seed-wiki lint typecheck migrate backup install

install:
	cd backend && uv sync
	cd frontend && npm ci

dev-backend:
	cd backend && uv run uvicorn app.app:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

# Long AI work (chapter reindex, Story Bible scans) runs here, not in the API.
# One worker with concurrency 1 is the right default for a single GPU.
worker:
	cd backend && uv run python -m app.worker

worker-once:
	cd backend && uv run python -m app.worker --once

test:
	cd backend && uv run pytest -q

lint:
	cd backend && uv run ruff check .
	cd frontend && npm run lint

test-frontend:
	cd frontend && npm test

# End-to-end wiki flows. Needs the API on :8000 and `next start` on :3000.
qa-wiki:
	cd frontend && node scripts/wiki-qa.mjs

# Phase 6 local-AI flows. Needs API :8000, `next start` :3000, and Ollama.
qa-phase6:
	cd frontend && node scripts/phase6-qa.mjs

# Phase 7 editor, canon, recap, thread, export, and accessibility flows.
# Needs API :8000 and `next start` :3000 against a production build.
qa-phase7:
	cd frontend && node scripts/phase7-qa.mjs

# Phase 8 diagnostics and account-data surfaces. Needs API :8000 and `next start` :3000.
qa-phase8:
	cd frontend && node scripts/phase8-qa.mjs

# Phase 9 storage/retention card. Needs API :8000 and `next start` :3000.
qa-storage:
	cd frontend && node scripts/storage-qa.mjs

# 1,000 entities for the Phase 4 performance budget: make seed-wiki EMAIL=you@example.com
seed-wiki:
	cd backend && uv run python -m scripts.seed_wiki --email "$(EMAIL)" --title "$(or $(TITLE),Perf)" --count $(or $(COUNT),1000)

typecheck:
	cd backend && uv run pyright
	cd frontend && npx tsc --noEmit

migrate:
	cd backend && uv run alembic upgrade head

# Phase 2 budget: writes Docs/perf.md-style numbers to stdout (test database).
perf:
	cd backend && uv run python scripts/perf.py

backup:
	./scripts/backup.sh
