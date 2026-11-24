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
