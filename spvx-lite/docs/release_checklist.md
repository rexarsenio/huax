# SPVX-Lite Basin Release Checklist

1. **Data freshness**
   - `python3 -m spvx.cli ingest --mode live` (or confirm live service healthy).
   - `python3 -m spvx.cli build-basins` to regenerate `components_daily` and basin/global indices.
   - Verify DuckDB timestamps (`SELECT max(d) FROM spvx_global_daily`). Latest fix must be T-1.

2. **Quality gates**
   - Coverage ≥ 90%: `SELECT basin, ROUND(AVG(CASE WHEN z_value IS NOT NULL THEN 1 ELSE 0 END),3) FROM components_daily WHERE d >= current_date - 29 GROUP BY basin`.
   - Component counts: `/ops/health` → `components_present` should match `APAC 2/2 | NAM 2/2 | SAM 2/2`.
   - Revisions: ensure `/ops/health.revision_flag == false` or document anomaly.
   - Spot-check `missing_reason`—no `baseline_missing` on last 14 days.

3. **Regression tests**
   - `pytest tests/test_basin_pipeline.py`.
   - Optional: `python3 -m compileall src/spvx` (ensures syntax).

4. **API / UI smoke**
   - `curl http://localhost:8080/api/index/APAC?range=30d` → non-empty JSON.
   - `curl -OJ http://localhost:8080/download/NAM.csv?range=90d` → CSV file ~90 rows.
   - Dashboard tabs render APAC/NAM/SAM, driver chips show values or `n/a`.

5. **Documentation**
   - Update change log / release notes referencing `docs/basin_indices.md`.
   - Confirm `.env` (if required) excludes secrets.

6. **Publish**
   - Promote DuckDB snapshot, refresh API containers, deploy dashboard build.
   - Post-release: monitor coverage metrics and ops health for 24h.
