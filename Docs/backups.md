# Backups

Three scripts, all pointed at the database described by `backend/.env`:

```bash
./scripts/backup.sh                              # writes backups/stillroom-<stamp>.dump
./scripts/verify-backup.sh backups/<dump>       # restores into a throwaway DB
./scripts/restore.sh backups/<dump>             # DESTRUCTIVE: replaces the live DB
```

`backup.sh` writes a custom-format dump and deletes `stillroom-*.dump` files
older than 30 days. `verify-backup.sh` creates a temporary database, restores
the dump there, prints schema revision and row counts, then drops the temporary
database. `restore.sh` runs `pg_restore --clean --if-exists` against the live
database.

> **Warning:** `restore.sh` DROPS every object contained in the dump before
> recreating it. Anything written after the dump is lost. Take a fresh backup
> before restoring an old one.

Both scripts find the PostgreSQL client on Windows automatically and read
credentials from `backend/.env`; they never use Docker. The Compose equivalent
is in [deployment.md](deployment.md#backups-with-compose).

## Verify before you need it

A file existing is not a backup. Verification restores it somewhere harmless:

```bash
./scripts/backup.sh
./scripts/verify-backup.sh backups/stillroom-2026-11-25-2206.dump
```

Expected output names the schema revision and counts, for example:

```text
Restoring backups/stillroom-2026-11-25-2206.dump into stillroom_verify_744 (live database untouched)...
Schema revision: e5a9c3d7b2f4
users=121 stories=121 chapters=228 entities=1230
Backup verified. Throwaway database dropped.
```

The command fails if the dump is unreadable, `pg_restore` reports an error, the
schema revision is empty, or a core table is missing. It never touches the live
database.

### Restore drill (run after any change to the scripts)

1. `./scripts/backup.sh`
2. Create a throwaway story in the app (or with `psql`).
3. `./scripts/verify-backup.sh <that-dump>` and confirm the counts include the
   throwaway story.
4. `./scripts/restore.sh <that-dump>`
5. Confirm the throwaway row is gone, the pre-existing data is intact, and
   `cd backend && uv run alembic current` reports the expected revision.
6. Sign in and open one story. A count alone does not prove relationships,
   chapters, or the login path survived.

Verified on 2026-11-25 against the local PostgreSQL 18 database using
`verify-backup.sh`: schema `e5a9c3d7b2f4`, 121 users, 121 stories, 228
chapters, and 1,230 entities restored into a throwaway database. The earlier
destructive restore drill on 2026-11-24 removed a throwaway story and left the
pre-existing story, chapters, and bible entries intact.

## What is and is not in the dump

Included: users, password hashes, stories, chapters, revisions, the wiki,
embeddings, jobs, audit events, sessions, and uploaded draft files.

Not included: `backend/.env` (including `JWT_SECRET` and
`AI_SETTINGS_ENCRYPTION_KEY`), Ollama models, and the repository itself. Store
the secret key separately from the dump. Without the same
`AI_SETTINGS_ENCRYPTION_KEY`, encrypted per-user provider keys cannot be read
after a restore; users can re-enter them.

## Before a migration you do not trust

```bash
./scripts/backup.sh
cd backend && uv run alembic upgrade head
```

If a migration fails halfway, restore the dump and add a new migration. Never
edit a migration that has already run in another database.

## Retention is not off-site storage

`backup.sh` keeps 30 days on the same disk. A disk failure or ransomware takes
the dumps with the database. Once a week, copy the newest dump somewhere else
(an encrypted external disk or a trusted machine) and run the verification
there. A backup that has never been restored is a hypothesis, not a backup.
