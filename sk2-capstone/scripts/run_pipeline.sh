#!/usr/bin/env bash
# MedInsure pipeline orchestrator
#
# Creates the database if missing, wipes project schemas/data, recreates schemas,
# then runs sql/00 → sql/07 in order with ON_ERROR_STOP.
#
# Usage:
#   ./scripts/run_pipeline.sh              # wipe schemas + full rebuild
#   ./scripts/run_pipeline.sh --reset      # DROP + CREATE database, then rebuild
#   ./scripts/run_pipeline.sh --reset -y   # same, skip confirmation
#
# Env overrides: PGHOST PGPORT PGUSER PGDATABASE (default medinsure) PGPASSWORD

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
DB_NAME="${PGDATABASE:-medinsure}"

RESET_DB=0
YES=0

usage() {
  cat <<EOF
Usage: $(basename "$0") [--reset] [-y|--yes] [-h|--help]

  (default)   Ensure DB exists; DROP schemas dw/staging/etl + reset public;
              then run sql/00–07 (full project rebuild).
  --reset     DROP and CREATE database ${DB_NAME}, then run sql/00–07.
  -y, --yes   Skip confirmation prompts for destructive actions.
  -h, --help  Show this help.

Environment: PGHOST PGPORT PGUSER PGDATABASE PGPASSWORD
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reset) RESET_DB=1; shift ;;
    -y|--yes) YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

PSQL_BASE=(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -v ON_ERROR_STOP=1 -X)

db_exists() {
  "${PSQL_BASE[@]}" -d postgres -Atc \
    "SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}'" | grep -qx 1
}

create_db() {
  echo ">>> Creating database ${DB_NAME}"
  "${PSQL_BASE[@]}" -d postgres -c "CREATE DATABASE ${DB_NAME};"
}

drop_db() {
  echo ">>> Terminating connections to ${DB_NAME}"
  "${PSQL_BASE[@]}" -d postgres -c \
    "SELECT pg_terminate_backend(pid)
     FROM pg_stat_activity
     WHERE datname = '${DB_NAME}'
       AND pid <> pg_backend_pid();" >/dev/null || true

  echo ">>> DROP DATABASE ${DB_NAME}"
  "${PSQL_BASE[@]}" -d postgres -c "DROP DATABASE IF EXISTS ${DB_NAME};"
}

# Wipe warehouse schemas and public (OLTP seed lives in public)
wipe_schemas() {
  echo ">>> Dropping schemas dw, staging, etl and resetting public"
  "${PSQL_BASE[@]}" -d "$DB_NAME" <<'SQL'
DROP SCHEMA IF EXISTS dw CASCADE;
DROP SCHEMA IF EXISTS staging CASCADE;
DROP SCHEMA IF EXISTS etl CASCADE;
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;
COMMENT ON SCHEMA public IS 'OLTP source tables for MedInsure claims';
SQL
}

run_sql() {
  local file="$1"
  echo ""
  echo "========================================"
  echo ">>> ${file}"
  echo "========================================"
  "${PSQL_BASE[@]}" -d "$DB_NAME" -f "$ROOT/${file}"
}

confirm_or_exit() {
  local msg="$1"
  if [[ "$YES" -eq 1 ]]; then
    return 0
  fi
  echo "WARNING: ${msg}"
  read -r -p "Type 'yes' to continue: " confirm
  if [[ "$confirm" != "yes" ]]; then
    echo "Aborted."
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Database + clean slate
# ---------------------------------------------------------------------------
if [[ "$RESET_DB" -eq 1 ]]; then
  confirm_or_exit "This will DROP database '${DB_NAME}' and delete all data."
  if db_exists; then
    drop_db
  fi
  create_db
else
  if ! db_exists; then
    create_db
  else
    confirm_or_exit "This will wipe schemas/data in '${DB_NAME}' (dw, staging, etl, public) then rebuild."
  fi
  wipe_schemas
fi

# ---------------------------------------------------------------------------
# Run pipeline steps in order
# ---------------------------------------------------------------------------
STEPS=(
  sql/00_schemas.sql
  sql/01_oltp.sql
  sql/02_dw_ddl.sql
  sql/03_etl_dims.sql
  sql/04_etl_facts.sql
  sql/05_analytics.sql
  sql/06_tuning.sql
  sql/07_quality.sql
)

STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo ""
echo "Pipeline started at ${STARTED_AT}"
echo "Target: ${PGUSER}@${PGHOST}:${PGPORT}/${DB_NAME}"

for step in "${STEPS[@]}"; do
  if [[ ! -f "$ROOT/${step}" ]]; then
    echo "ERROR: missing file ${ROOT}/${step}" >&2
    exit 1
  fi
  run_sql "$step"
done

echo ""
echo "========================================"
echo "Pipeline finished successfully."
echo "Started:  ${STARTED_AT}"
echo "Finished: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "========================================"
