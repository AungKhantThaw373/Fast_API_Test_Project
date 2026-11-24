#!/usr/bin/env bash
# Dump the local Stillroom database. Keeps 30 days of dumps.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/_env.sh
source "$SCRIPT_DIR/_env.sh"

cd "$REPO_ROOT"
mkdir -p backups

STAMP="$(date +%Y-%m-%d-%H%M)"
FILE="backups/stillroom-${STAMP}.dump"

pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" --format=custom --file="$FILE"

find backups -name 'stillroom-*.dump' -mtime +30 -delete

echo "Wrote $FILE"
