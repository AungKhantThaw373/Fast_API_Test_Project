# Build log

## Phase 0 baseline

- Started on branch `hardening/phase-0`, tag `pre-hardening`.
- Recorded baseline checks in `docs/baseline.md`.
- Native PostgreSQL 18 and pgvector files are installed; local authentication failed with existing app credentials.
- Existing remote database credentials were rejected, so remote schema and data could not be verified or backed up. No database changes were made.
- The frontend has a pnpm lockfile, so `npm ci` fails until a deliberate package-manager conversion.

## Phase 0 dead-code cleanup

- Removed unused legacy RAG models, routes, schemas, storage client, and unused dependencies.
- Updated Alembic's model imports to include the Editing models.
- `uv sync`, backend import, metadata check, `alembic heads`, and offline SQL generation passed. Live migration remains unverified because the configured database rejects authentication.
- Ignored personal scratch files were left untouched.
- Next: configure and verify native PostgreSQL, and recover remote data only after obtaining working access.
