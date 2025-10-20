-- Aggregate slow-moving tankers inside chokepoint bounding boxes.
-- The Python helper `aggregate_dwell.run_aggregation` handles watermarking and
-- interval selection; this SQL can be used for ad-hoc refreshes or debugging.

CREATE TABLE IF NOT EXISTS chokepoint_dwell (
    ts TIMESTAMP,
    region TEXT,
    slow_count BIGINT,
    PRIMARY KEY (ts, region)
);

-- Insert or update aggregated dwell data within a chosen time window.
-- Replace the placeholders with the desired window bounds.
INSERT INTO chokepoint_dwell AS target
WITH windowed AS (
    SELECT *
    FROM ais_canon
    WHERE msg_time > TIMESTAMP '2024-01-01 00:00:00+00'
      AND msg_time <= TIMESTAMP '2024-01-02 00:00:00+00'
),
deduped AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY mmsi, date_trunc('minute', msg_time)
            ORDER BY msg_time DESC, rx_time DESC
        ) AS rn
    FROM windowed
)
SELECT
    time_bucket(INTERVAL '10 minutes', msg_time) AS ts,
    region,
    COUNT(DISTINCT mmsi) FILTER (WHERE is_tanker AND sog < 0.5) AS slow_count
FROM deduped
WHERE rn = 1
GROUP BY ts, region
ON CONFLICT (ts, region)
DO UPDATE SET slow_count = excluded.slow_count;
