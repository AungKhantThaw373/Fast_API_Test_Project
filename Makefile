.PHONY: dev-backend dev-frontend worker worker-once perf test test-frontend lint typecheck migrate backup install

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
