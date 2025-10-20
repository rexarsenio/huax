#!/usr/bin/env bash
# Manually trigger the chokepoint dwell aggregation using the repository setup.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [ -x "$ROOT/.venv312/bin/python3" ]; then
  PYTHON="$ROOT/.venv312/bin/python3"
elif [ -x "$ROOT/.venv/bin/python3" ]; then
  PYTHON="$ROOT/.venv/bin/python3"
elif [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python3" ]; then
  PYTHON="$VIRTUAL_ENV/bin/python3"
else
  PYTHON="$(command -v python3 || true)"
fi

if [ -z "${PYTHON:-}" ]; then
  echo "Error: could not locate python3 interpreter. Activate a virtualenv or install Python." >&2
  exit 1
fi

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

set -a
[ -f ".env" ] && source ".env"
set +a

exec "$PYTHON" "$ROOT/aggregate_dwell.py" "$@"
