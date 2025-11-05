"""Ship registry database schema and migration functions."""
import duckdb
from typing import Optional
import logging

LOG = logging.getLogger(__name__)


def create_ship_registry_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Create ship_registry tables and views if they don't exist.

    Tables:
    - ship_registry: Main vessel classification table
    - ship_registry_audit: Audit trail for classification decisions

    Views:
    - ship_registry_unknown_last_7d: Unknown vessels in last 7 days
    """

    # Create sequence first (before audit table)
    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS ship_registry_audit_seq START 1
    """)

    # Main registry table
    con.execute("""
        CREATE TABLE IF NOT EXISTS ship_registry (
            mmsi BIGINT PRIMARY KEY,
            imo BIGINT,
            ship_type_code INTEGER,           -- AIS type code, 80-89 = Tanker
            type_source VARCHAR,               -- 'TYPE5' | 'PORT_BEHAVIOR' | 'STS_BEHAVIOR' | 'CORRIDOR' | 'MANUAL'
            length_m DOUBLE,
            beam_m DOUBLE,
            confidence DOUBLE,                 -- 0..1
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            updated_at TIMESTAMP DEFAULT now()
        )
    """)
    LOG.info("Ship registry table created/verified")

    # Audit/explainability table
    con.execute("""
        CREATE TABLE IF NOT EXISTS ship_registry_audit (
            id INTEGER PRIMARY KEY DEFAULT nextval('ship_registry_audit_seq'),
            mmsi BIGINT,
            ts TIMESTAMP DEFAULT now(),
            rule_id VARCHAR,                   -- e.g. 'H1_TERMINAL_DWELL'
            detail VARCHAR,                    -- JSON with matching info
            proposed_type_code INTEGER,
            proposed_confidence DOUBLE
        )
    """)
    LOG.info("Ship registry audit table created/verified")

    # View for unknown vessels in last 7 days
    con.execute("""
        CREATE OR REPLACE VIEW ship_registry_unknown_last_7d AS
        SELECT
            f.mmsi,
            MIN(f.msg_time) AS first_seen,
            MAX(f.msg_time) AS last_seen,
            COUNT(*) AS fixes
        FROM ais_canon f
        LEFT JOIN ship_registry r ON r.mmsi = f.mmsi
        WHERE r.mmsi IS NULL
          AND f.msg_time >= NOW() - INTERVAL '7 days'
        GROUP BY f.mmsi
    """)
    LOG.info("Ship registry views created/verified")

    # Create indexes for performance
    try:
        con.execute("CREATE INDEX IF NOT EXISTS idx_registry_audit_mmsi ON ship_registry_audit(mmsi)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_registry_audit_rule ON ship_registry_audit(rule_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_registry_type_source ON ship_registry(type_source)")
        LOG.info("Ship registry indexes created/verified")
    except Exception as e:
        LOG.warning(f"Failed to create some indexes (may already exist): {e}")


def get_registry_stats(con: duckdb.DuckDBPyConnection) -> dict:
    """Get current ship registry statistics.

    Returns:
        dict with keys: total, tankers, unknown_24h, avg_confidence
    """
    stats = {}

    # Total registered vessels
    result = con.execute("SELECT COUNT(*) FROM ship_registry").fetchone()
    stats['total'] = result[0] if result else 0

    # Tankers (type code 80-89)
    result = con.execute("""
        SELECT COUNT(*) FROM ship_registry
        WHERE ship_type_code >= 80 AND ship_type_code < 90
    """).fetchone()
    stats['tankers'] = result[0] if result else 0

    # Unknown vessels in last 24h
    result = con.execute("""
        SELECT COUNT(DISTINCT f.mmsi)
        FROM ais_canon f
        LEFT JOIN ship_registry r ON r.mmsi = f.mmsi
        WHERE r.mmsi IS NULL
          AND f.msg_time >= NOW() - INTERVAL '24 hours'
    """).fetchone()
    stats['unknown_24h'] = result[0] if result else 0

    # Average confidence
    result = con.execute("""
        SELECT AVG(confidence) FROM ship_registry
        WHERE confidence IS NOT NULL
    """).fetchone()
    stats['avg_confidence'] = result[0] if result else 0.0

    return stats


def bootstrap_unknown_mmsi(
    con: duckdb.DuckDBPyConnection,
    since_days: int = 7
) -> int:
    """Bootstrap ship_registry with skeleton entries for unknown MMSIs.

    Creates entries with NULL type but valid first_seen/last_seen timestamps.

    Args:
        con: DuckDB connection
        since_days: Look back this many days for unknown vessels

    Returns:
        Number of new MMSIs added
    """
    result = con.execute(f"""
        INSERT INTO ship_registry (mmsi, first_seen, last_seen, updated_at)
        SELECT
            f.mmsi,
            MIN(f.msg_time) AS first_seen,
            MAX(f.msg_time) AS last_seen,
            NOW() AS updated_at
        FROM ais_canon f
        LEFT JOIN ship_registry r ON r.mmsi = f.mmsi
        WHERE r.mmsi IS NULL
          AND f.msg_time >= NOW() - INTERVAL '{since_days} days'
        GROUP BY f.mmsi
        ON CONFLICT (mmsi) DO NOTHING
        RETURNING mmsi
    """)

    count = len(result.fetchall())
    con.commit()
    LOG.info(f"Bootstrapped {count} new MMSIs from last {since_days} days")
    return count


def apply_confidence_decay(con: duckdb.DuckDBPyConnection, days_threshold: int = 180) -> int:
    """Apply confidence decay to heuristic classifications without recent evidence.

    Reduces confidence by 0.2 (min 0.5) for vessels not seen in last N days.
    TYPE5 classifications are never decayed.

    Args:
        con: DuckDB connection
        days_threshold: Apply decay if last_seen older than this

    Returns:
        Number of records updated
    """
    result = con.execute(f"""
        UPDATE ship_registry
        SET
            confidence = GREATEST(0.5, confidence - 0.2),
            updated_at = NOW()
        WHERE type_source IN ('PORT_BEHAVIOR', 'STS_BEHAVIOR', 'CORRIDOR')
          AND last_seen < NOW() - INTERVAL '{days_threshold} days'
          AND confidence > 0.5
        RETURNING mmsi
    """)

    count = len(result.fetchall())
    con.commit()
    LOG.info(f"Applied confidence decay to {count} vessels (>{days_threshold}d without evidence)")
    return count
