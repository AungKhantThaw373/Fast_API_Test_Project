# Runbook

Operational steps for the native Windows install. Commands assume the repository
is at `C:\Users\ACER\OneDrive\Desktop\AI`; use Git Bash for the shell scripts
and PowerShell for the process commands.

## Prerequisites

- PostgreSQL 18 with `psql` at `C:\Program Files\PostgreSQL\18\bin`.
- `uv` and Python 3.12+ for the backend, Node 22+ and npm for the frontend.
- Optional: Ollama on `127.0.0.1:11434` with an embedding model and a chat model.
- A `backend/.env` with the database, auth secret, cookie settings, frontend
  origins, and any provider keys. Do not commit it.

```powershell
$env:PGPASSWORD = "death373"
$env:Path += ";C:\Program Files\PostgreSQL\18\bin"
```

## First start

```powershell
cd C:\Users\ACER\OneDrive\Desktop\AI\backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.app:app --host 127.0.0.1 --port 8000

cd ..\frontend
npm ci
npm run build
npx next start -H 127.0.0.1 -p 3000

cd ..
uv run --project backend python -m app.worker
```

Open `http://127.0.0.1:3000`. The API is on `:8000`; the browser normally talks
to it through the Next.js `/api` proxy.

`next dev` is fine for editing, but Playwright and browser QA must use a
production build: HMR does not hydrate in this environment.

## Health checks

| Check | Command / URL | Expected |
|---|---|---|
| API liveness | `GET http://127.0.0.1:8000/health` | Process-only `200`; does not check the DB |
| API readiness | `GET http://127.0.0.1:8000/ready` | `200` when DB, worker heartbeat, and required services are ready |
| Worker | `GET /system/status` or Diagnostics | Heartbeat fresh; queue counts visible |
| Storage | `GET /system/storage` or Diagnostics → Storage | DB size, counts, expired rows |
| Schema | `uv run alembic current` | `f1b7c3d9e5a2 (head)` |
| HNSW index | `\d story_chunks` in `psql` | `ix_story_chunks_embedding_hnsw` present |

A `503` from `/ready` is actionable: check the `detail`, the worker heartbeat,
and the API log. Do not restart the worker repeatedly; it may be in a legitimate
long model call.

## Migrations

```powershell
cd backend
uv run alembic current
uv run alembic upgrade head
```

Take a backup before a migration that builds an index or rewrites rows. The HNSW
migration (`f1b7c3d9e5a2`) builds a global index and blocks writes while it runs;
the 100k-row benchmark took about 112 seconds to build. On a large existing
database, schedule it during a quiet window.

Never edit a migration that has already run. Add a new revision instead. The API
refuses to start when the database is not at head.

## Backups and restore

```bash
./scripts/backup.sh
./scripts/verify-backup.sh backups/<dump>
```

The scripts use native `pg_dump`/`pg_restore`, not Docker. The verified restore
drill and the destructive restore path are in [backups.md](backups.md). Keep at
least one copy outside this machine; a backup on the same disk is not disaster
recovery.

## Worker and queue

Run exactly one worker unless you have measured the GPU/memory to support more:

```powershell
cd backend
uv run python -m app.worker          # serve
uv run python -m app.worker --once   # drain and exit
```

If jobs stay `queued`, check that the worker is alive, that `run_at` is in the
past, and that no `dead` job is blocking the same `dedupe_key`. The diagnostics
page exposes counts; SQL is the fallback:

```sql
SELECT status, count(*) FROM jobs GROUP BY status ORDER BY status;
SELECT type, status, attempts, left(last_error, 200) FROM jobs
 WHERE status IN ('failed', 'dead') ORDER BY updated_at DESC LIMIT 20;
```

Cancel a running continuity scan from the UI. A cancelled job is recorded as
`cancelled`; retry by creating a new scan, not by editing the row.

## Storage and retention

Diagnostics shows database size, the largest relations, and account counts.
**Clean up expired** deletes only the signed-in account's trashed stories and
chapters older than 30 days, plus finished jobs last updated more than 30 days
ago. It does not run `VACUUM`, so disk usage may stay flat until autovacuum
reuses the pages. On a quiet database, `VACUUM (ANALYZE);` is the manual
reclamation step. Full policy: [data-retention.md](data-retention.md).

## Scale fixture

Measurements use an isolated database, never `stillroom`:

```powershell
$env:DBNAME = "stillroom_scale_test"
cd backend
uv run alembic upgrade head
uv run python ../scripts/import_fixture.py --migrate
```

Point a second API instance at `DBNAME=stillroom_scale_test` for endpoint
measurements, then stop it. The fixture account is local-only and must never be
deployed. See [scale-import.md](scale-import.md) and [scale-report.md](scale-report.md).

## Common failures

| Symptom | Check |
|---|---|
| API exits at startup with schema error | `alembic current`; run `upgrade head` |
| `401` after login | Auth cookie blocked, clock skew, or session revoked; check `/health` and cookies |
| `403 Missing security token` | Write request lacks `X-CSRF-Token`; the browser client handles it, scripts must too |
| Search `500` / connection error | Ollama or the configured embedding provider is down |
| Search is slow with a `Seq Scan` on `story_chunks` | Check `EXPLAIN (ANALYZE, BUFFERS)`; ensure HNSW exists and `ef_search` is set by the service, not forced globally |
| `pg_database_size` is slow | Filesystem/antivirus contention; storage reports are diagnostic, not a hot path |
| Registration `429` | In-process 3/hour limit; restarting the API clears it. Do not loop registrations in QA |
| Port 8000 answers old code | More than one uvicorn process is listening; kill all and start one |
| Windows file-lock errors during build | OneDrive sync or a running `.next`/venv process; stop the server and retry |

## Verification before a release

```powershell
cd backend
uv run pytest -q
uv run ruff check .
uv run pyright app

cd ..\frontend
npx tsc --noEmit
npm run lint -- --quiet
npm run test
npm run build
```

Then run the browser suites against `next start`, including `make qa-storage`
and the Phase 7/8 suites. The release checklist and honest unexecuted items are
recorded in the Phase 9 acceptance report.