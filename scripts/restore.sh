#!/usr/bin/env bash
# Restore a dump produced by scripts/backup.sh.
#
# WARNING: pg_restore runs with --clean --if-exists, which DROPS the objects in
# the dump before recreating them. Everything written after the dump is lost.
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

pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
  --clean --if-exists --no-owner --no-privileges "$DUMP"

echo "Restored $DUMP"
