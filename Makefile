.PHONY: dev-backend dev-frontend test lint typecheck migrate backup install

install:
	cd backend && uv sync
	cd frontend && npm ci

dev-backend:
	cd backend && uv run uvicorn app.app:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

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

backup:
	./scripts/backup.sh
