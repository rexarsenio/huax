#!/usr/bin/env bash
# Export DuckDB database into a Parquet-backed snapshot.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_PATH="${1:-$ROOT/db/spvx.duckdb}"
TIMESTAMP="$(date -u +%F)"
DEST_DIR="${ROOT}/backups"
DEST_PATH="${DEST_DIR}/spvx_${TIMESTAMP}"

mkdir -p "$DEST_DIR"

echo "Creating DuckDB checkpoint..."
duckdb "$DB_PATH" "CHECKPOINT"

echo "Exporting database to ${DEST_PATH}..."
duckdb "$DB_PATH" "EXPORT DATABASE '${DEST_PATH}' (FORMAT PARQUET);"

echo "Backup completed: ${DEST_PATH}"
