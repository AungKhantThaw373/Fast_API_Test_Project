#!/usr/bin/env bash
# Shared helper: read the database settings the backend uses.
# Sourced by backup.sh and restore.sh.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/backend/.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE. Copy backend/.env.example and fill it in." >&2
  exit 1
fi

read_env() {
  local key="$1" fallback="$2"
  local value
  value="$(sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1 | tr -d '\r')"
  if [ -z "$value" ]; then
    printf '%s' "$fallback"
  else
    printf '%s' "$value"
  fi
}

DB_HOST="$(read_env host 127.0.0.1)"
DB_PORT="$(read_env port 5432)"
DB_NAME="$(read_env dbname stillroom)"
DB_USER="$(read_env user postgres)"
DB_PASSWORD="$(read_env password "")"

# Windows installs do not put the PostgreSQL client on PATH by default.
if ! command -v pg_dump >/dev/null 2>&1; then
  for candidate in "/c/Program Files/PostgreSQL"/*/bin; do
    if [ -x "$candidate/pg_dump" ]; then
      export PATH="$candidate:$PATH"
      break
    fi
  done
fi

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "pg_dump not found. Add your PostgreSQL bin directory to PATH." >&2
  exit 1
fi

export PGPASSWORD="$DB_PASSWORD"
