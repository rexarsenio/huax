#!/usr/bin/env bash
# Download surface ocean currents (uo/vo) and 10 m wind (u10/v10)
# for key chokepoint regions using Copernicus Marine subsets.
#
# Requires:
#   - copernicusmarine CLI (`pip install copernicusmarine`)
#   - CMEMS_USERNAME / CMEMS_PASSWORD or interactive login
#
# Usage:
#   ./scripts/fetch_cmems_currents_wind.sh [--hours 48] [--regions all|REG1,REG2] [--skip-wind]
#
# Example:
#   ./scripts/fetch_cmems_currents_wind.sh --hours 36 --regions MALACCA,SUEZ

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_BASE="${OUTPUT_BASE:-$PROJECT_ROOT/data/external/cmems}"

HOURS_BACK=48
REGIONS="MALACCA,SINGAPORE,GIBRALTAR,SUEZ,BOSPORUS"
FETCH_WIND=1

# Parse simple flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --hours)
      HOURS_BACK="$2"
      shift 2
      ;;
    --regions)
      REGIONS="$2"
      shift 2
      ;;
    --skip-wind)
      FETCH_WIND=0
      shift
      ;;
    --help|-h)
      grep '^#' "$0" | sed 's/^#//'
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

IFS=',' read -r -a REGION_LIST <<< "$REGIONS"

# Region bounding boxes (lat_min lat_max lon_min lon_max)
REGIONS_ALL=(
  "MALACCA:1:4:100:104"
  "SINGAPORE:1:2:103:104"
  "GIBRALTAR:35:37:-6:-5"
  "SUEZ:29:32:32:34"
  "BOSPORUS:41:41.8:28.5:29.5"
)

get_region_bbox() {
  local region="$1"
  for entry in "${REGIONS_ALL[@]}"; do
    IFS=':' read -r name lat_min lat_max lon_min lon_max <<< "$entry"
    if [[ "$name" == "$region" ]]; then
      echo "$lat_min $lat_max $lon_min $lon_max"
      return 0
    fi
  done
  return 1
}

for region in "${REGION_LIST[@]}"; do
  if ! get_region_bbox "$region" >/dev/null; then
    echo "❌ Unknown region: $region" >&2
    exit 1
  fi
done

check_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "❌ Missing command '$1'. Install it first." >&2
    exit 1
  fi
}

check_cmd copernicusmarine
check_cmd python
check_cmd date

# Prepare time window (UTC)
read -r START_UTC END_UTC <<EOF
$(python - <<PY
from datetime import datetime, timedelta, timezone
hours = $HOURS_BACK
end_time = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
start_time = end_time - timedelta(hours=hours)
print(start_time.isoformat(timespec="seconds"), end_time.isoformat(timespec="seconds"))
PY
)
EOF

echo "📅 Time window: $START_UTC → $END_UTC (UTC)"
echo "🌍 Regions: ${REGION_LIST[*]}"
echo "💾 Output base: $OUTPUT_BASE"
echo ""

# Ensure CMEMS credentials are present if non-interactive
if [[ -n "${CMEMS_USERNAME:-}" && -n "${CMEMS_PASSWORD:-}" ]]; then
  echo "🔐 Using CMEMS credentials from environment."
else
  echo "⚠️  CMEMS_USERNAME / CMEMS_PASSWORD not set. CLI will prompt if needed."
fi

mkdir -p "$OUTPUT_BASE/currents" "$OUTPUT_BASE/wind"

download_subset() {
  local dataset_id="$1"
  local vars=("${!2}")
  local out_path="$3"
  local lat_min="$4" lat_max="$5" lon_min="$6" lon_max="$7"
  local depth_min="${8:-}"
  local depth_max="${9:-}"

  mkdir -p "$(dirname "$out_path")"
  local cmd=(copernicusmarine subset
    --dataset-id "$dataset_id"
    --start-datetime "$START_UTC"
    --end-datetime "$END_UTC"
    --minimum-latitude "$lat_min"
    --maximum-latitude "$lat_max"
    --minimum-longitude "$lon_min"
    --maximum-longitude "$lon_max"
    --output-filename "$out_path"
  )

  for v in "${vars[@]}"; do
    cmd+=(--variable "$v")
  done

  if [[ -n "$depth_min" && -n "$depth_max" ]]; then
    cmd+=(--minimum-depth "$depth_min" --maximum-depth "$depth_max")
  fi

  echo "→ Downloading ${dataset_id} (${vars[*]}) to $out_path"
  if ! "${cmd[@]}"; then
    echo "⚠️  Download failed for $out_path" >&2
    return 1
  fi
}

for region in "${REGION_LIST[@]}"; do
  read lat_min lat_max lon_min lon_max <<< "$(get_region_bbox "$region")"

  REGION_SLUG=$(echo "$region" | tr '[:upper:]' '[:lower:]')
  TS_STUB="${START_UTC%%T*}_to_${END_UTC%%T*}"

  # Currents dataset (surface subset of global hydrodynamic model)
  CURR_DATASET="${CMEMS_CURRENTS_DATASET:-cmems_mod_glo_phy-cur_anfc_0.083deg_PT6H-i}"
  CURR_VARS=("uo" "vo")
  CURR_OUT="$OUTPUT_BASE/currents/${REGION_SLUG}/currents_${REGION_SLUG}_${TS_STUB}.nc"

  download_subset "$CURR_DATASET" CURR_VARS[@] "$CURR_OUT" "$lat_min" "$lat_max" "$lon_min" "$lon_max" 0.4 0.6 || continue

  if [[ "$FETCH_WIND" -eq 1 ]]; then
    WIND_DATASET="${CMEMS_WIND_DATASET:-cmems_mod_glo_wind_anfc_0.083deg_PT1H-i}"
    WIND_VARS=("u10" "v10")
    WIND_OUT="$OUTPUT_BASE/wind/${REGION_SLUG}/wind_${REGION_SLUG}_${TS_STUB}.nc"
    download_subset "$WIND_DATASET" WIND_VARS[@] "$WIND_OUT" "$lat_min" "$lat_max" "$lon_min" "$lon_max" || {
      echo "⚠️  Wind download failed for $region (continuing)."
    }
  fi

  echo ""
done

echo "✅ Downloads complete."
echo ""
echo "Next steps:"
echo "  python -m spvx.cli ingest-sea-state --provider cmems --what currents --lookback-hours $HOURS_BACK"
if [[ "$FETCH_WIND" -eq 1 ]]; then
  echo "  python -m spvx.cli ingest-sea-state --provider cmems --what wind --lookback-hours $HOURS_BACK"
else
  echo "  # Wind downloads skipped."
fi
