# Backups

Two scripts, both pointed at the database described by `backend/.env`:

```bash
./scripts/backup.sh                              # writes backups/stillroom-<stamp>.dump
./scripts/restore.sh backups/stillroom-<stamp>.dump
```

`backup.sh` writes a custom-format dump and deletes `stillroom-*.dump` files
older than 30 days. `restore.sh` runs `pg_restore --clean --if-exists`.

> **Warning:** `--clean` DROPS every object contained in the dump before
> recreating it. Anything written after the dump is lost. Take a fresh backup
> before restoring an old one.

Both scripts find the PostgreSQL client on Windows automatically and read
credentials from `backend/.env`; they never use Docker.

## Restore drill (run after any change to the scripts)

1. `./scripts/backup.sh`
2. Create a throwaway story in the app (or with `psql`).
3. `./scripts/restore.sh backups/<that-dump>.dump`
4. Confirm the throwaway row is gone and the original data is intact.

Verified on 2026-11-24 against the local database: the throwaway story was
removed and the pre-existing story, chapters, and bible entries were restored.

## Before a migration you do not trust

```bash
./scripts/backup.sh
cd backend && uv run alembic upgrade head
```

If a migration fails halfway, restore the dump and add a new migration. Never
edit a migration that has already run in another database.
