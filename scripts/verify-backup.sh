#!/usr/bin/env bash
# Restore a dump into a throwaway database and print row counts.
# The live database is never touched.
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 backups/stillroom-YYYY-MM-DD-HHMM.dump" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/_env.sh
source "$SCRIPT_DIR/_env.sh"

DUMP="$1"
if [ ! -f "$DUMP" ]; then
  echo "No such dump: $DUMP" >&2
  exit 1
fi
if ! pg_restore --list "$DUMP" >/dev/null; then
  echo "Not a readable PostgreSQL custom-format dump: $DUMP" >&2
  exit 1
fi

VERIFY_DB="stillroom_verify_$$"
createdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$VERIFY_DB"
cleanup() {
  dropdb -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" --if-exists "$VERIFY_DB" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Restoring $DUMP into $VERIFY_DB (live database untouched)..."
pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$VERIFY_DB" \
  --no-owner --no-privileges "$DUMP"

echo "Schema revision: $(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$VERIFY_DB" -Atc "select version_num from alembic_version")"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$VERIFY_DB" -Atc "
  select 'users=' || (select count(*) from users)
      || ' stories=' || (select count(*) from stories)
      || ' chapters=' || (select count(*) from story_chapters)
      || ' entities=' || (select count(*) from entities);"

echo "Backup verified. Throwaway database dropped."