# Baseline

Recorded before hardening on `hardening/phase-0`; starting commit `01f0e17` (`pre-hardening`).

- Python: project uses Python 3.12.13 through uv (system Python 3.14.0)
- uv: 0.11.7
- Node: 24.14.1; npm: 11.11.0
- Native PostgreSQL client: 18.7; server accepts connections on 127.0.0.1:5432; pgvector extension files are installed
- Ollama: 0.30.8; `nomic-embed-text:latest` is installed
- Configured database: remote session pooler, not local

## Backend

- `uv sync`: pass
- `uv run python -c "import app.app"`: pass
- `uv run alembic current`: failed: remote database reports tenant/user not found
- Tests: no test suite tracked at baseline
- Local PostgreSQL: authentication with existing app credentials failed; no passwordless access

## Frontend

- `npm ci`: failed: repository has a pnpm lockfile, not a package-lock.json
- `npm run lint`: pass using existing node_modules
- `npx tsc --noEmit`: pass using existing node_modules
- `npm run build`: pass using existing node_modules

## Manual smoke test

Not run: configured database cannot be reached with its existing credentials. Register, login, story creation, chapter creation, autosave, import, and draft check remain unverified.

> Historical snapshot, kept for comparison. Phase 0 outcomes are in
> `Docs/build-log.md`, `Docs/database.md`, and `Docs/phase-0-acceptance.md`;
> current state and next tasks are in the root `AGENTS.md`.
