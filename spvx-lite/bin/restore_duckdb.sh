#!/usr/bin/env bash
# Restore DuckDB database from a Parquet snapshot.

set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: restore_duckdb.sh <snapshot_dir> [target_db]" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SNAPSHOT_DIR="$1"
TARGET_DB="${2:-$ROOT/db/spvx.duckdb}"

if [ ! -d "$SNAPSHOT_DIR" ]; then
  echo "Snapshot directory not found: $SNAPSHOT_DIR" >&2
  exit 1
fi

BACKUP_PATH="${TARGET_DB}.bak.$(date -u +%s)"
if [ -f "$TARGET_DB" ]; then
  mv "$TARGET_DB" "$BACKUP_PATH"
  echo "Existing database moved to $BACKUP_PATH"
fi

duckdb "$TARGET_DB" "IMPORT DATABASE '${SNAPSHOT_DIR}' (FORMAT PARQUET);"
echo "Restore completed from ${SNAPSHOT_DIR}"
