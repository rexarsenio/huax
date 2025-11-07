#!/usr/bin/env python3
"""
Populate ML Feature Store

Aggregates data from all sources into ml_features_daily table for ML training.
"""

import duckdb
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = "db/spvx.duckdb"


def main():
    if not Path(DB_PATH).exists():
        print(f"❌ Database not found: {DB_PATH}")
        return

    con = duckdb.connect(DB_PATH)

    print("🔄 Populating ML Feature Store")
    print("=" * 70)
    print()

    # Get date range from anchorage_daily
    date_range = con.execute("""
        SELECT MIN(ds), MAX(ds)
        FROM anchorage_daily
    """).fetchone()

    if not date_range[0]:
        print("❌ No data in anchorage_daily. Run TH-3 first!")
        con.close()
        return

    start_date, end_date = date_range
    print(f"📅 Date range: {start_date} to {end_date}")
    print()

    print("1️⃣  Building comprehensive feature matrix...")

    # Complex SQL query to join all features
    con.execute("""
        INSERT OR REPLACE INTO ml_features_daily
        SELECT
            d.ds,
            d.anchorage_id,

            -- Target variable
            d.median_dwell_h,
            (d.anomaly_detected OR d.z_dwell > 2.0) as is_congested,

            -- Anchorage features
            d.episode_count,
            COALESCE(d.coverage_ratio, 0.0) as avg_confidence,

            -- Temporal features
            DAYOFWEEK(d.ds) as day_of_week,
            WEEKOFYEAR(d.ds) as week_of_year,
            MONTH(d.ds) as month,
            (DAYOFWEEK(d.ds) IN (6, 7)) as is_weekend,
            FALSE as is_holiday,  -- TODO: Add holiday calendar

            -- Lagged features
            LAG(d.median_dwell_h, 1) OVER (PARTITION BY d.anchorage_id ORDER BY d.ds) as dwell_lag_1d,
            LAG(d.median_dwell_h, 7) OVER (PARTITION BY d.anchorage_id ORDER BY d.ds) as dwell_lag_7d,
            LAG(d.median_dwell_h, 30) OVER (PARTITION BY d.anchorage_id ORDER BY d.ds) as dwell_lag_30d,

            -- Rolling averages
            AVG(d.median_dwell_h) OVER (
                PARTITION BY d.anchorage_id
                ORDER BY d.ds
                ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ) as dwell_rolling_7d,

            AVG(d.median_dwell_h) OVER (
                PARTITION BY d.anchorage_id
                ORDER BY d.ds
                ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
            ) as dwell_rolling_30d,

            -- Statistical features
            d.z_dwell as z_score,
            d.baseline_median_h as baseline_median,
            d.baseline_std_h as baseline_std,

            -- Corridor features (SIS from Malacca)
            sis.sis_mean as malacca_sis_mean,
            sis.sis_p90 as malacca_sis_p90,

            -- External data
            oil.brent_usd as brent_price,
            pmi.value as china_pmi,
            NULL as singapore_bunker_price,  -- TODO: Add bunker prices

            -- Supply chain features
            flux.crossings_24h as malacca_flux_24h,
            shandong.total_vessels as shandong_total_vessels,

            -- Weather features
            FALSE as typhoon_active,  -- TODO: Join with weather_events
            (MONTH(d.ds) IN (6, 7, 8, 9)) as monsoon_season,  -- June-September

            CURRENT_TIMESTAMP as created_at

        FROM anchorage_daily d

        -- Join SIS data for Malacca corridor
        LEFT JOIN sis_daily sis
            ON sis.ds = d.ds
            AND sis.corridor_id LIKE '%MALACCA%'

        -- Join oil prices
        LEFT JOIN oil_prices oil
            ON oil.ds = d.ds

        -- Join China PMI
        LEFT JOIN (
            SELECT ds, value
            FROM economic_indicators
            WHERE indicator_name = 'PMI_Manufacturing'
              AND country = 'China'
        ) pmi ON pmi.ds = d.ds

        -- Join Malacca gate flux (24h)
        LEFT JOIN (
            SELECT
                DATE(ts) as ds,
                COUNT(*) as crossings_24h
            FROM gate_crossings
            WHERE gate_id LIKE 'GATE_MALACCA%'
            GROUP BY DATE(ts)
        ) flux ON flux.ds = d.ds

        -- Join Shandong aggregate metrics
        LEFT JOIN (
            SELECT
                ds,
                SUM(episode_count) as total_vessels
            FROM anchorage_daily
            WHERE anchorage_id LIKE 'ANCH_%'
              AND anchorage_id NOT LIKE 'ANCH_OPL%'
            GROUP BY ds
        ) shandong ON shandong.ds = d.ds

        WHERE d.median_dwell_h IS NOT NULL
        ORDER BY d.ds, d.anchorage_id
    """)

    rows = con.execute("SELECT COUNT(*) FROM ml_features_daily").fetchone()[0]
    print(f"   ✅ Created {rows:,} feature rows")
    print()

    # Show feature completeness
    print("2️⃣  Checking feature completeness...")

    completeness = con.execute("""
        SELECT
            COUNT(*) as total_rows,
            COUNT(brent_price) as has_oil_price,
            COUNT(china_pmi) as has_pmi,
            COUNT(malacca_sis_mean) as has_sis,
            COUNT(malacca_flux_24h) as has_flux,
            COUNT(dwell_lag_7d) as has_lag_7d,
            COUNT(dwell_rolling_7d) as has_rolling_7d
        FROM ml_features_daily
    """).fetchone()

    total, oil, pmi, sis, flux, lag7, roll7 = completeness

    print(f"   Total rows:         {total:,}")
    print(f"   With oil price:     {oil:,} ({100*oil/total:.1f}%)")
    print(f"   With China PMI:     {pmi:,} ({100*pmi/total:.1f}%)")
    print(f"   With Malacca SIS:   {sis:,} ({100*sis/total:.1f}%)")
    print(f"   With gate flux:     {flux:,} ({100*flux/total:.1f}%)")
    print(f"   With 7-day lag:     {lag7:,} ({100*lag7/total:.1f}%)")
    print(f"   With 7-day roll:    {roll7:,} ({100*roll7/total:.1f}%)")
    print()

    # Show sample features for inspection
    print("3️⃣  Sample features (OPL Singapore, recent):")
    samples = con.execute("""
        SELECT
            ds,
            median_dwell_h,
            is_congested,
            dwell_lag_1d,
            dwell_rolling_7d,
            z_score,
            brent_price,
            malacca_sis_mean
        FROM ml_features_daily
        WHERE anchorage_id = 'ANCH_OPL_SIN'
        ORDER BY ds DESC
        LIMIT 5
    """).fetchall()

    if samples:
        print(f"   {'Date':<12} {'Dwell':>7} {'Cong':>5} {'Lag1d':>7} {'Roll7d':>7} {'Z':>6} {'Brent':>7} {'SIS':>6}")
        print(f"   {'-'*12} {'-'*7} {'-'*5} {'-'*7} {'-'*7} {'-'*6} {'-'*7} {'-'*6}")
        for ds, dwell, cong, lag1, roll7, z, brent, sis in samples:
            cong_str = "YES" if cong else "NO"
            print(f"   {str(ds):<12} {dwell:7.1f} {cong_str:>5} "
                  f"{lag1 or 0:7.1f} {roll7 or 0:7.1f} {z or 0:6.2f} "
                  f"{brent or 0:7.2f} {sis or 0:6.3f}")
    print()

    # Show congestion distribution
    print("4️⃣  Congestion distribution:")
    dist = con.execute("""
        SELECT
            anchorage_id,
            COUNT(*) as total_days,
            SUM(CASE WHEN is_congested THEN 1 ELSE 0 END) as congested_days,
            AVG(median_dwell_h) as avg_dwell,
            MAX(median_dwell_h) as max_dwell
        FROM ml_features_daily
        GROUP BY anchorage_id
        ORDER BY congested_days DESC
    """).fetchall()

    if dist:
        print(f"   {'Anchorage':<30} {'Days':>6} {'Cong':>6} {'%':>6} {'Avg':>7} {'Max':>7}")
        print(f"   {'-'*30} {'-'*6} {'-'*6} {'-'*6} {'-'*7} {'-'*7}")
        for anch, total, cong, avg, max_d in dist[:10]:
            pct = 100 * cong / total if total > 0 else 0
            print(f"   {anch:<30} {total:6d} {cong:6d} {pct:5.1f}% {avg:7.1f} {max_d:7.1f}")
    print()

    con.commit()
    con.close()

    print("=" * 70)
    print("✅ ML Feature Store Populated!")
    print()
    print("📊 Feature Categories:")
    print("   • Target: median_dwell_h, is_congested")
    print("   • Temporal: day_of_week, week_of_year, month, is_weekend")
    print("   • Lagged: dwell_lag_{1,7,30}d")
    print("   • Rolling: dwell_rolling_{7,30}d")
    print("   • Statistical: z_score, baseline_median, baseline_std")
    print("   • External: brent_price, china_pmi")
    print("   • Supply Chain: malacca_sis, malacca_flux, shandong_vessels")
    print("   • Weather: typhoon_active, monsoon_season")
    print()
    print("🚀 Next Steps:")
    print("   1. Train XGBoost model:")
    print("      python3 train_xgboost_model.py")
    print()
    print("   2. Or start collecting more external data:")
    print("      python3 collect_oil_prices.py")
    print("      python3 collect_economic_data.py")


if __name__ == "__main__":
    main()
