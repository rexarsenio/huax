#!/usr/bin/env bash
# Install and start launchd services for SPVX AIS monitoring.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
TPL_PATH="$ROOT/com.spvx.ais-ingest.plist.tpl"
TARGET_PATH="$LAUNCH_AGENTS_DIR/com.spvx.ais-ingest.plist"

echo "Installing SPVX AIS launchd service..."

mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$ROOT/logs"

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

PYTHON_DIR="$(dirname "$PYTHON")"
DEFAULT_PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
SERVICE_PATH="$PYTHON_DIR:$DEFAULT_PATH"

RENDER_PY="$(command -v python3)"
if [ -z "${RENDER_PY:-}" ]; then
  echo "Error: python3 is required to render plist template." >&2
  exit 1
fi

read_env_var() {
  local key="$1"
  local default="$2"
  "$RENDER_PY" <<'PY' "$ROOT/.env" "$key" "$default"
from pathlib import Path
import sys

env_path, key, default = sys.argv[1:]
value = default
path = Path(env_path)
if path.is_file():
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            value = v.strip().strip('"').strip("'")
            break
print(value)
PY
}

TZ_VALUE="$(read_env_var TZ UTC)"
AGG_INTERVAL="$(read_env_var AGGREGATION_INTERVAL_SECONDS 600)"
METRICS_PORT="$(read_env_var SPVX_METRICS_PORT 9108)"
HEALTH_PORT="$(read_env_var SPVX_HEALTH_PORT 9109)"

render_plist() {
  local template="$1"
  local destination="$2"
  local root="$3"
  local python_bin="$4"
  local path_value="$5"
  local tz_value="$6"
  local agg_interval="$7"
  local metrics_port="$8"
  local health_port="$9"

  "$RENDER_PY" <<'PY' "$template" "$destination" "$root" "$python_bin" "$path_value" "$tz_value" "$agg_interval" "$metrics_port" "$health_port"
import sys
from pathlib import Path

template, destination, root, python_bin, path_value, tz_value, agg_interval, metrics_port, health_port = sys.argv[1:]
content = Path(template).read_text(encoding="utf-8")
content = (
    content.replace("@@ROOT@@", root)
    .replace("@@PYTHON@@", python_bin)
    .replace("@@PATH@@", path_value)
    .replace("@@TZ@@", tz_value)
    .replace("@@AGG_INTERVAL@@", agg_interval)
    .replace("@@METRICS_PORT@@", metrics_port)
    .replace("@@HEALTH_PORT@@", health_port)
)
Path(destination).write_text(content, encoding="utf-8")
PY
}

echo "Stopping existing service..."
launchctl unload "$TARGET_PATH" 2>/dev/null || true

render_plist "$TPL_PATH" "$TARGET_PATH" "$ROOT" "$PYTHON" "$SERVICE_PATH" "$TZ_VALUE" "$AGG_INTERVAL" "$METRICS_PORT" "$HEALTH_PORT"

echo "Starting AIS ingestion service..."
launchctl load -w "$TARGET_PATH"

# Clean up legacy aggregation service if it exists.
LEGACY_AGG="$LAUNCH_AGENTS_DIR/com.spvx.ais-aggregate.plist"
if [ -f "$LEGACY_AGG" ]; then
  echo "Removing deprecated aggregation service definition..."
  launchctl unload "$LEGACY_AGG" 2>/dev/null || true
  rm -f "$LEGACY_AGG"
fi

echo ""
echo "✓ Service installed and started."
echo ""
echo "To check service status:"
echo "  launchctl list | grep com.spvx.ais-ingest"
echo ""
echo "To view logs:"
echo "  tail -f \"$ROOT/logs/ais-ingest.log\""
echo "  tail -f \"$ROOT/logs/ais-ingest.error.log\""
echo ""
echo "To stop the service:"
echo "  launchctl unload \"$TARGET_PATH\""
