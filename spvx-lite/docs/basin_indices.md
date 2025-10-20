# SPVX-Lite Basin Suite (APAC · NAM · SAM)

## 1. Scope & Fix Policy

- **Objective:** extend SPVX-Lite with three basin-level stress indices for Asia-Pacific (APAC), North America (NAM) and South America (SAM).
- **Fix:** T+1 12:00 UTC. The snapshot writer freezes the prior day, sets `revision_flag=false` and publishes through API/CSV/UI.
- **Data latency:** AIS dwell windows roll every 10 minutes; PortWatch movements refresh daily. Missing inputs do not get zero-filled.
- **Revision SLO:** median absolute revision < 0.10 index points across a 30-day lookback.

## 2. Component Inputs

| Basin | Component | Source | Definition |
|-------|-----------|--------|------------|
| APAC  | `CQ_SG`   | AISStream → `dwell_10m` | Slow-moving (SOG < 0.5 kn) tanker counts inside `[95.0,0.0,106.0,6.5]` (Singapore/Malacca). |
| APAC  | `CQ_HRZ`  | AISStream | Same metric for `[54.0,24.0,58.5,28.2]` (Strait of Hormuz). |
| NAM   | `CQ_PAN`  | AISStream | Mean of z-scores for Panama North (`[-80.2,9.3,-79.3,9.7]`) and South (`[-80.0,8.5,-79.3,8.9]`). |
| NAM   | `PORT_US` | PortWatch `Daily_Trade_Data` | Sum of tanker movements for Houston, South Louisiana and New Orleans (`ISO3='USA'`). |
| SAM   | `CQ_PAN_S` | AISStream | South-side Panama z-score reused for SAM basin.
| SAM   | `PORT_BR` | PortWatch | Tanker movements for Santos + Rio de Janeiro (`ISO3='BRA'`). |

- **AIS cadence:** raw points canonicalised into `ais_canon`, aggregated into `dwell_10m` via `aggregate_dwell` (10-minute bucket, dedup by MMSI). Counts limited to tankers (`shiptype 80–89`).
- **PortWatch cadence:** REST pull (per port) populating `portwatch_daily (d, portname, port_code, iso3, movements, departures, arrivals)`.
- **Weather flags:** `python -m spvx.cli ingest-weather` uses OpenWeather to mark high-wind (>25 kn) or heavy sea (>3.5 m) episodes per chokepoint and stores them in `weather_observations`.
- **Sea state:** `python -m spvx.cli ingest-sea-state` loads RTOFS surface currents + WW3 significant wave height. Aggregated values feed the new components `SEA_CURR` (current speed anomaly) and `SEA_WAVE` (wave height anomaly), and also toggle the weather flag.

## 3. Seasonal Baselines & Z-Scores

1. Each input series writes an entry into `component_inputs_daily (d, key, raw_value, n_obs)` with `key = "{COMP}:{BASIN}"`. For NAM we duplicate the Panama South series with key `CQ_PAN_S:NAM` for aggregation.
2. `spvx.features.baseline_tables.refresh_doy_baselines` consumes >180 days history (default lookback 400) per key and stores `(key, doy, mean, std)` in `baselines_doy`.
3. Z-score computation:
   - `Z = winsor((raw - mean) / std, bounds=±5)` when baseline exists.
   - Port components invert the sign (`-Z`) because fewer departures imply higher stress.
   - `CQ_PAN` z-score = average of `CQ_PAN_N` and `CQ_PAN_S` z-scores.
4. Missing baseline/std yields `missing_reason` (`baseline_missing`, `no_data`, `baseline_std_zero`).

## 4. Daily ETL Pipeline (Typer `build-basins`)

1. **Ensure schema:** `spvx.db.ensure_core_tables` creates DuckDB tables (`dwell_10m`, `portwatch_daily`, `component_inputs_daily`, `components_daily`, `spvx_basin_daily`, `spvx_global_daily`).
2. **Rollup inputs:** `build_components_daily`
   - Aggregates `dwell_10m` → daily slow counts per region with window counters.
   - Groups `portwatch_daily` per canonical port.
   - Upserts raw metrics into `component_inputs_daily` (including NAM copy of Panama South).
   - Refreshes DoY baselines and writes final `components_daily` rows with `z_value`, `raw_value`, `n_obs`, `missing_reason`.
3. **Materialise indices:** `compute_basin_indices`
   - `spvx_basin_daily`: `100 * exp(AVG(z_value))` per basin/day; records `comps_present`.
   - `spvx_global_daily`: log-average of available basins (requires `comps_present >= 1`).
4. **Health snapshots:** `/ops/health` endpoint surfaces readiness, latest snapshot date, component coverage (30d) and `components_present` counts.

## 5. API Extensions

- `GET /api/index/global?range=90d` → global series.
- `GET /api/index/{basin}?range=90d` → basin series with `comps_present`.
- `GET /api/components/{basin}?range=30d` → component time series (`z_value`, `raw_value`, `n_obs`, `missing_reason`).
- `GET /download/{basin}.csv` → 90d CSV export.
- `GET /ops/health` → readiness JSON (coverage, component counts, revision flag).

## 6. Quality Gates & QC Dashboards

- **Coverage:** each basin must have ≥90% non-missing days over trailing 30-sample window (`coverage_30d` metric).
- **Component presence:** ready state requires `comps_present` to match expected counts (`APAC` 2, `NAM` 2, `SAM` 2).
- **Revision monitoring:** `ops_health.revision_flag` raises when `|Δ spvx_global| > 0.10` between latest two fixes.
- **Correlation sanity:** manual review when `corr(basin, global) > 0.9` (tracked offline via notebooks).
- **Weather mask (future work):** placeholder `weather_flag` logic defined; recomputation excluding flagged windows is optional V0.2.

## 7. Validation Checklist

1. Run `python3 -m spvx.cli ingest --mode mock` to seed synthetic data.
2. Execute `python3 -m spvx.cli build-basins` → populates `components_daily`, `spvx_basin_daily`, `spvx_global_daily`.
3. Inspect QC:
   - `duckdb` queries inside `tests/test_basin_pipeline.py` ensure basins/components appear.
   - `pytest tests/test_basin_pipeline.py` (requires DuckDB + FastAPI deps).
   - Manual histogram: `SELECT z_value FROM components_daily WHERE comp='CQ_PAN'` for distribution sanity.
4. Smoke API: use FastAPI `TestClient` (provided in tests) or `curl http://localhost:8080/api/index/APAC`.
5. Dashboard: run `pnpm dev` in `dashboard/` and toggle basin tabs; driver chips should show Z-values or `n/a`.

## 8. Deliverables Summary

- **DuckDB artifacts:** `component_inputs_daily`, `components_daily`, `spvx_basin_daily`, `spvx_global_daily`.
- **Docs:** this methodology note + `docs/release_checklist.md`.
- **Automation:** Typer command `build-basins`; `/download/{basin}.csv` for direct distribution.
- **Tests:** `tests/test_basin_pipeline.py` covering pipeline + API endpoints.
- **UI:** Dashboard tabs (Global/EUR/APAC/NAM/SAM), component chips, CSV export button, readiness badges fed from `/ops/health`.
