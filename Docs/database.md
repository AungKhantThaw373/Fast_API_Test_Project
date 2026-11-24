# Local database

Stillroom runs against a local PostgreSQL instance with the `pgvector`
extension. Docker is not used on this machine; the database is the native
Windows PostgreSQL 18 install.

## One-time setup

`psql` is not on `PATH` by default. Add it for the current shell:

```bash
export PATH="/c/Program Files/PostgreSQL/18/bin:$PATH"
```

Create the databases and extensions:

```bash
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE stillroom;"
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE stillroom_test;"
psql -U postgres -h 127.0.0.1 -d stillroom      -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;"
psql -U postgres -h 127.0.0.1 -d stillroom_test -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;"
```

`backend/.env` must point at it:

```dotenv
user=postgres
password=death373
host=127.0.0.1
port=5432
dbname=stillroom
DATABASE_SSL=disable
```

Then create the schema:

```bash
cd backend
uv run alembic upgrade head
```

## Migrating from the old Supabase project

The dump was taken with `pg_dump --data-only` after the local schema was
created by Alembic. It is kept at `backups/supabase-data.sql`.

```bash
pg_dump "postgresql://<user>:<password>@<host>:5432/postgres?sslmode=require" \
  --no-owner --no-privileges --data-only \
  --table=users --table=user_ai_settings \
  --table=stories --table=story_chapters --table=story_chapter_revisions \
  --table=story_scene_embeddings --table=story_bible_entries \
  --table=continuity_scans --table=continuity_findings \
  --table=editing_folders --table=editing_draft_files \
  -f backups/supabase-data.sql

psql -U postgres -h 127.0.0.1 -d stillroom -v ON_ERROR_STOP=1 \
  -f backups/supabase-data.sql
```

Row counts must match the source. All primary keys are UUIDs, so there are no
sequence resets to worry about.

## Slow query visibility

Optional, for local profiling:

```sql
ALTER DATABASE stillroom SET log_min_duration_statement = 200;
```

## Runtime settings (Phase 2)

Statement timeouts protect the request path. They are set per *connection* by
SQLAlchemy (`backend/app/db.py`, `connect_args.server_settings`), so they survive
a `COMMIT` and apply to every pooled connection:

| Caller | `statement_timeout` |
|---|---|
| API requests | 15 s |
| Durable worker (`app/worker.py`) | 5 min |

Verify from the app side:

```bash
cd backend
DBNAME=stillroom_test uv run python -c "
import asyncio
from sqlalchemy import text
from app.db import async_session, engine
async def main():
    async with async_session() as s:
        print(await s.scalar(text('SHOW statement_timeout')))
    await engine.dispose()
asyncio.run(main())"
```

Slow queries are logged at the database level, not in the app. Applied once per
database on this machine:

```sql
ALTER DATABASE stillroom      SET log_min_duration_statement = '200ms';
ALTER DATABASE stillroom_test SET log_min_duration_statement = '200ms';
```

New connections pick it up; find the lines in the PostgreSQL log
(`%ProgramData%\PostgreSQL\18\data\log`). `ANALYZE` runs inside the index
migration, so fresh databases and CI get planner statistics without a manual step.
