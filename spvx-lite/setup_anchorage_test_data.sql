-- Quick setup SQL for anchorage test data (TH-4 API)
-- Usage: duckdb db/spvx.duckdb < setup_anchorage_test_data.sql

-- 1. Create anchorage_polygons table
CREATE TABLE IF NOT EXISTS anchorage_polygons (
    anchorage_id VARCHAR PRIMARY KEY,
    anchorage_name VARCHAR,
    kind VARCHAR DEFAULT 'ANCHORAGE',
    centroid_lat DOUBLE,
    centroid_lon DOUBLE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert Shandong + OPL anchorages
INSERT OR REPLACE INTO anchorage_polygons (anchorage_id, anchorage_name, centroid_lat, centroid_lon) VALUES
('ANCH_QINGDAO', 'Qingdao Anchorage', 36.07, 120.33),
('ANCH_RIZHAO', 'Rizhao Anchorage', 35.43, 119.53),
('ANCH_YANTAI', 'Yantai Anchorage', 37.53, 121.39),
('ANCH_LONGKOU', 'Longkou Anchorage', 37.65, 120.33),
('ANCH_LANSHAN', 'Lanshan Anchorage', 35.07, 119.35),
('ANCH_OPL_SIN', 'OPL Singapore', 1.20, 103.75);

-- 2. Create anchorage_episodes table
CREATE TABLE IF NOT EXISTS anchorage_episodes (
    episode_id VARCHAR PRIMARY KEY,
    anchorage_id VARCHAR,
    mmsi BIGINT,
    vessel_name VARCHAR,
    ts_entry TIMESTAMP,
    ts_exit TIMESTAMP,
    dwell_hours DOUBLE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert sample episodes for ANCH_QINGDAO (last 14 days)
INSERT OR REPLACE INTO anchorage_episodes (episode_id, anchorage_id, mmsi, vessel_name, ts_entry, ts_exit, dwell_hours) VALUES
('EP_QD_001', 'ANCH_QINGDAO', 412000001, 'QINGDAO_EXPRESS', current_timestamp - interval '1 day', current_timestamp - interval '12 hours', 12),
('EP_QD_002', 'ANCH_QINGDAO', 412000002, 'EASTERN_GLORY', current_timestamp - interval '2 days', current_timestamp - interval '1 day', 24),
('EP_QD_003', 'ANCH_QINGDAO', 412000003, 'PACIFIC_STAR', current_timestamp - interval '3 days', current_timestamp - interval '2 days', 30),
('EP_QD_004', 'ANCH_QINGDAO', 412000004, 'BLUE_WHALE', current_timestamp - interval '4 days', current_timestamp - interval '3 days', 18),
('EP_QD_005', 'ANCH_QINGDAO', 412000005, 'PEARL_RIVER', current_timestamp - interval '5 days', current_timestamp - interval '4 days', 36),
('EP_QD_006', 'ANCH_QINGDAO', 412000006, 'GOLDEN_DRAGON', current_timestamp - interval '6 days', current_timestamp - interval '5 days', 24),
('EP_QD_007', 'ANCH_QINGDAO', 412000007, 'OCEAN_PRINCE', current_timestamp - interval '7 days', current_timestamp - interval '6 days', 20),
('EP_QD_008', 'ANCH_QINGDAO', 412000008, 'SEA_FORTUNE', current_timestamp - interval '8 days', current_timestamp - interval '7 days', 28),
('EP_QD_009', 'ANCH_QINGDAO', 412000009, 'CHINA_HOPE', current_timestamp - interval '9 days', current_timestamp - interval '8 days', 16),
('EP_QD_010', 'ANCH_QINGDAO', 412000010, 'LUCKY_STAR', current_timestamp - interval '10 days', current_timestamp - interval '9 days', 32),
-- Rizhao episodes
('EP_RZ_001', 'ANCH_RIZHAO', 412001001, 'RIZHAO_TRADER', current_timestamp - interval '1 day', current_timestamp - interval '14 hours', 10),
('EP_RZ_002', 'ANCH_RIZHAO', 412001002, 'SUN_EAGLE', current_timestamp - interval '2 days', current_timestamp - interval '1 day', 22),
('EP_RZ_003', 'ANCH_RIZHAO', 412001003, 'MORNING_LIGHT', current_timestamp - interval '3 days', current_timestamp - interval '2 days', 26),
('EP_RZ_004', 'ANCH_RIZHAO', 412001004, 'HARBOR_KING', current_timestamp - interval '4 days', current_timestamp - interval '3 days', 18),
('EP_RZ_005', 'ANCH_RIZHAO', 412001005, 'YELLOW_SEA', current_timestamp - interval '5 days', current_timestamp - interval '4 days', 30),
-- OPL Singapore episodes
('EP_OPL_001', 'ANCH_OPL_SIN', 563000001, 'SINGAPORE_SPIRIT', current_timestamp - interval '1 day', current_timestamp - interval '8 hours', 16),
('EP_OPL_002', 'ANCH_OPL_SIN', 563000002, 'MERLION_PRIDE', current_timestamp - interval '2 days', current_timestamp - interval '1 day', 20),
('EP_OPL_003', 'ANCH_OPL_SIN', 563000003, 'STRAITS_RUNNER', current_timestamp - interval '3 days', current_timestamp - interval '2 days', 24),
('EP_OPL_004', 'ANCH_OPL_SIN', 563000004, 'LION_CITY', current_timestamp - interval '4 days', current_timestamp - interval '3 days', 14),
('EP_OPL_005', 'ANCH_OPL_SIN', 563000005, 'SENTOSA_QUEEN', current_timestamp - interval '5 days', current_timestamp - interval '4 days', 28);

-- 3. Create anchorage_daily_dwell table
CREATE TABLE IF NOT EXISTS anchorage_daily_dwell (
    ds DATE,
    anchorage_id VARCHAR,
    episode_count INTEGER,
    median_dwell_h DOUBLE,
    p90_dwell_h DOUBLE,
    coverage_ratio DOUBLE,
    baseline_median_h DOUBLE,
    baseline_std_h DOUBLE,
    z_dwell DOUBLE,
    anomaly_detected BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ds, anchorage_id)
);

-- Insert daily aggregations with Z-scores (last 7 days)
INSERT OR REPLACE INTO anchorage_daily_dwell (ds, anchorage_id, episode_count, median_dwell_h, p90_dwell_h, coverage_ratio, baseline_median_h, baseline_std_h, z_dwell, anomaly_detected) VALUES
-- Qingdao (normal days)
(current_date, 'ANCH_QINGDAO', 18, 24.5, 36.0, 0.92, 24.0, 8.0, 0.06, false),
(current_date - interval '1 day', 'ANCH_QINGDAO', 16, 22.0, 32.0, 0.88, 24.0, 8.0, -0.25, false),
(current_date - interval '2 days', 'ANCH_QINGDAO', 20, 26.0, 38.0, 0.95, 24.0, 8.0, 0.25, false),
-- Qingdao (ANOMALY on day 3 - high congestion)
(current_date - interval '3 days', 'ANCH_QINGDAO', 35, 48.0, 72.0, 0.98, 24.0, 8.0, 3.0, true),
(current_date - interval '4 days', 'ANCH_QINGDAO', 17, 23.0, 34.0, 0.90, 24.0, 8.0, -0.13, false),
(current_date - interval '5 days', 'ANCH_QINGDAO', 19, 25.0, 37.0, 0.91, 24.0, 8.0, 0.13, false),
(current_date - interval '6 days', 'ANCH_QINGDAO', 15, 21.0, 31.0, 0.85, 24.0, 8.0, -0.38, false),
-- Rizhao
(current_date, 'ANCH_RIZHAO', 14, 22.0, 32.0, 0.87, 22.0, 7.0, 0.00, false),
(current_date - interval '1 day', 'ANCH_RIZHAO', 13, 20.0, 30.0, 0.84, 22.0, 7.0, -0.29, false),
(current_date - interval '2 days', 'ANCH_RIZHAO', 16, 24.0, 36.0, 0.91, 22.0, 7.0, 0.29, false),
(current_date - interval '3 days', 'ANCH_RIZHAO', 15, 23.0, 34.0, 0.88, 22.0, 7.0, 0.14, false),
(current_date - interval '4 days', 'ANCH_RIZHAO', 12, 19.0, 28.0, 0.82, 22.0, 7.0, -0.43, false),
(current_date - interval '5 days', 'ANCH_RIZHAO', 14, 22.0, 32.0, 0.86, 22.0, 7.0, 0.00, false),
(current_date - interval '6 days', 'ANCH_RIZHAO', 15, 23.0, 34.0, 0.89, 22.0, 7.0, 0.14, false),
-- OPL Singapore
(current_date, 'ANCH_OPL_SIN', 22, 18.0, 28.0, 0.93, 18.0, 6.0, 0.00, false),
(current_date - interval '1 day', 'ANCH_OPL_SIN', 20, 16.0, 24.0, 0.90, 18.0, 6.0, -0.33, false),
(current_date - interval '2 days', 'ANCH_OPL_SIN', 24, 20.0, 30.0, 0.95, 18.0, 6.0, 0.33, false),
(current_date - interval '3 days', 'ANCH_OPL_SIN', 21, 17.0, 26.0, 0.92, 18.0, 6.0, -0.17, false),
(current_date - interval '4 days', 'ANCH_OPL_SIN', 23, 19.0, 29.0, 0.94, 18.0, 6.0, 0.17, false),
(current_date - interval '5 days', 'ANCH_OPL_SIN', 22, 18.0, 28.0, 0.91, 18.0, 6.0, 0.00, false),
(current_date - interval '6 days', 'ANCH_OPL_SIN', 20, 16.0, 24.0, 0.88, 18.0, 6.0, -0.33, false);

-- Show summary
SELECT '✅ Setup complete!' as status;
SELECT 'Anchorages created:' as info, COUNT(*) as count FROM anchorage_polygons;
SELECT 'Episodes created:' as info, COUNT(*) as count FROM anchorage_episodes;
SELECT 'Daily records created:' as info, COUNT(*) as count FROM anchorage_daily_dwell;

-- Show latest data
SELECT '📊 Latest daily data:' as info;
SELECT
    ds,
    anchorage_id,
    episode_count,
    median_dwell_h,
    z_dwell,
    CASE WHEN anomaly_detected THEN '🔴 ANOMALY' ELSE '✅ Normal' END as status
FROM anchorage_daily_dwell
ORDER BY ds DESC, anchorage_id
LIMIT 10;
