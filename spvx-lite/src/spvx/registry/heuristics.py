"""Heuristic rules for tanker classification based on behavior."""
import duckdb
import json
import logging
from typing import List, Dict, Any

LOG = logging.getLogger(__name__)


class HeuristicRule:
    """Base class for heuristic classification rules."""

    def __init__(self, rule_id: str, type_code: int, confidence: float, type_source: str):
        self.rule_id = rule_id
        self.type_code = type_code
        self.confidence = confidence
        self.type_source = type_source

    def apply(self, con: duckdb.DuckDBPyConnection, horizon_days: int = 90) -> int:
        """Apply this rule and return number of vessels classified."""
        raise NotImplementedError


class H1_TerminalDwell(HeuristicRule):
    """H1: Classify vessels that dwell at oil terminals.

    If MMSI has ≥1 dwell of ≥120 min at oil_terminals in last N days
    → TANKER, PORT_BEHAVIOR, confidence=0.90
    """

    def __init__(self):
        super().__init__(
            rule_id='H1_TERMINAL_DWELL',
            type_code=80,  # Tanker
            confidence=0.90,
            type_source='PORT_BEHAVIOR'
        )

    def apply(self, con: duckdb.DuckDBPyConnection, horizon_days: int = 90) -> int:
        """Apply terminal dwell heuristic.

        Requires:
        - polygon_events table with kind='OIL_TERMINAL'
        - dwell_min column

        Args:
            con: DuckDB connection
            horizon_days: Look back this many days

        Returns:
            Number of vessels classified
        """
        # Check if polygon_events table exists
        try:
            con.execute("SELECT 1 FROM polygon_events LIMIT 1")
        except Exception:
            LOG.warning("polygon_events table not found, skipping H1")
            return 0

        # Insert audit records for vessels meeting criteria
        con.execute(f"""
            INSERT INTO ship_registry_audit (mmsi, rule_id, detail, proposed_type_code, proposed_confidence)
            SELECT
                e.mmsi,
                '{self.rule_id}' AS rule_id,
                json_object(
                    'polygon', e.polygon_id,
                    'dwell_min', CAST(e.dwell_min AS INTEGER),
                    'ts_in', CAST(e.ts_in AS VARCHAR)
                ) AS detail,
                {self.type_code} AS proposed_type_code,
                {self.confidence} AS proposed_confidence
            FROM polygon_events e
            LEFT JOIN ship_registry r ON r.mmsi = e.mmsi
            WHERE e.kind = 'OIL_TERMINAL'
              AND e.dwell_min >= 120
              AND e.ts_in >= NOW() - INTERVAL '{horizon_days} days'
              AND (r.mmsi IS NULL OR r.confidence IS NULL OR r.confidence < {self.confidence})
        """)

        # Consolidate into registry (max confidence wins)
        result = con.execute(f"""
            INSERT INTO ship_registry (mmsi, imo, ship_type_code, type_source, length_m, beam_m, confidence, first_seen, last_seen, updated_at)
            SELECT
                a.mmsi,
                r.imo,
                {self.type_code} AS ship_type_code,
                '{self.type_source}' AS type_source,
                r.length_m,
                r.beam_m,
                MAX(a.proposed_confidence) AS confidence,
                COALESCE(r.first_seen, (SELECT MIN(msg_time) FROM ais_canon f WHERE f.mmsi = a.mmsi)) AS first_seen,
                COALESCE(r.last_seen, (SELECT MAX(msg_time) FROM ais_canon f WHERE f.mmsi = a.mmsi)) AS last_seen,
                NOW() AS updated_at
            FROM ship_registry_audit a
            LEFT JOIN ship_registry r ON r.mmsi = a.mmsi
            WHERE a.rule_id = '{self.rule_id}'
              AND a.ts >= NOW() - INTERVAL '1 hour'  -- Only recent audit entries
            GROUP BY a.mmsi, r.imo, r.length_m, r.beam_m, r.first_seen, r.last_seen
            ON CONFLICT (mmsi) DO UPDATE SET
                ship_type_code = EXCLUDED.ship_type_code,
                type_source = EXCLUDED.type_source,
                confidence = EXCLUDED.confidence,
                last_seen = EXCLUDED.last_seen,
                updated_at = EXCLUDED.updated_at
            WHERE ship_registry.confidence IS NULL OR EXCLUDED.confidence > ship_registry.confidence
            RETURNING mmsi
        """)

        count = len(result.fetchall())
        con.commit()
        LOG.info(f"H1_TERMINAL_DWELL: Classified {count} vessels (horizon={horizon_days}d)")
        return count


class H2_STSZone(HeuristicRule):
    """H2: Classify vessels that dwell in STS (ship-to-ship transfer) zones.

    If MMSI has dwell ≥360 min in sts_zones in last N days
    → TANKER, STS_BEHAVIOR, confidence=0.80
    """

    def __init__(self):
        super().__init__(
            rule_id='H2_STS_DWELL',
            type_code=80,  # Tanker
            confidence=0.80,
            type_source='STS_BEHAVIOR'
        )

    def apply(self, con: duckdb.DuckDBPyConnection, horizon_days: int = 90) -> int:
        """Apply STS zone dwell heuristic.

        Requires:
        - polygon_events table with kind='STS_ZONE'
        - dwell_min column

        Args:
            con: DuckDB connection
            horizon_days: Look back this many days

        Returns:
            Number of vessels classified
        """
        try:
            con.execute("SELECT 1 FROM polygon_events LIMIT 1")
        except Exception:
            LOG.warning("polygon_events table not found, skipping H2")
            return 0

        # Insert audit records
        con.execute(f"""
            INSERT INTO ship_registry_audit (mmsi, rule_id, detail, proposed_type_code, proposed_confidence)
            SELECT
                e.mmsi,
                '{self.rule_id}' AS rule_id,
                json_object(
                    'polygon', e.polygon_id,
                    'dwell_min', CAST(e.dwell_min AS INTEGER),
                    'ts_in', CAST(e.ts_in AS VARCHAR)
                ) AS detail,
                {self.type_code} AS proposed_type_code,
                {self.confidence} AS proposed_confidence
            FROM polygon_events e
            LEFT JOIN ship_registry r ON r.mmsi = e.mmsi
            WHERE e.kind = 'STS_ZONE'
              AND e.dwell_min >= 360
              AND e.ts_in >= NOW() - INTERVAL '{horizon_days} days'
              AND (r.mmsi IS NULL OR r.confidence IS NULL OR r.confidence < {self.confidence})
        """)

        # Consolidate into registry
        result = con.execute(f"""
            INSERT INTO ship_registry (mmsi, ship_type_code, type_source, confidence, first_seen, last_seen, updated_at)
            SELECT
                a.mmsi,
                {self.type_code} AS ship_type_code,
                '{self.type_source}' AS type_source,
                MAX(a.proposed_confidence) AS confidence,
                COALESCE(r.first_seen, (SELECT MIN(msg_time) FROM ais_canon f WHERE f.mmsi = a.mmsi)) AS first_seen,
                COALESCE(r.last_seen, (SELECT MAX(msg_time) FROM ais_canon f WHERE f.mmsi = a.mmsi)) AS last_seen,
                NOW() AS updated_at
            FROM ship_registry_audit a
            LEFT JOIN ship_registry r ON r.mmsi = a.mmsi
            WHERE a.rule_id = '{self.rule_id}'
              AND a.ts >= NOW() - INTERVAL '1 hour'
            GROUP BY a.mmsi, r.first_seen, r.last_seen
            ON CONFLICT (mmsi) DO UPDATE SET
                ship_type_code = EXCLUDED.ship_type_code,
                type_source = EXCLUDED.type_source,
                confidence = EXCLUDED.confidence,
                last_seen = EXCLUDED.last_seen,
                updated_at = EXCLUDED.updated_at
            WHERE ship_registry.confidence IS NULL OR EXCLUDED.confidence > ship_registry.confidence
            RETURNING mmsi
        """)

        count = len(result.fetchall())
        con.commit()
        LOG.info(f"H2_STS_DWELL: Classified {count} vessels (horizon={horizon_days}d)")
        return count


class H3_CorridorPattern(HeuristicRule):
    """H3: Classify vessels with frequent oil corridor/chokepoint crossings.

    If MMSI has ≥8 gate crossings in oil corridors in last N days
    → TANKER, CORRIDOR, confidence=0.70
    """

    def __init__(self):
        super().__init__(
            rule_id='H3_CORRIDOR_FREQ',
            type_code=80,  # Tanker
            confidence=0.70,
            type_source='CORRIDOR'
        )

        # Oil-related gates/chokepoints
        self.oil_gates = [
            'HORMUZ_MAIN',
            'FUJAIRAH_N',
            'SUEZ_S_OIL',
            'SUEZ_N_OIL',
            'USG_LIGHTERING_W',
            'USG_LIGHTERING_E',
            'BOSPORUS_S',
            'BOSPORUS_N',
        ]

    def apply(self, con: duckdb.DuckDBPyConnection, horizon_days: int = 90, min_crossings: int = 8) -> int:
        """Apply corridor pattern heuristic.

        Requires:
        - gate_crossings table

        Args:
            con: DuckDB connection
            horizon_days: Look back this many days
            min_crossings: Minimum number of crossings required

        Returns:
            Number of vessels classified
        """
        try:
            con.execute("SELECT 1 FROM gate_crossings LIMIT 1")
        except Exception:
            LOG.warning("gate_crossings table not found, skipping H3")
            return 0

        gate_list = "'" + "','".join(self.oil_gates) + "'"

        # Insert audit records
        con.execute(f"""
            WITH recent AS (
                SELECT
                    mmsi,
                    COUNT(*) AS n_cross,
                    COUNT(DISTINCT gate_id) AS n_unique_gates
                FROM gate_crossings
                WHERE ts >= NOW() - INTERVAL '{horizon_days} days'
                  AND gate_id IN ({gate_list})
                GROUP BY mmsi
                HAVING n_cross >= {min_crossings}
            )
            INSERT INTO ship_registry_audit (mmsi, rule_id, detail, proposed_type_code, proposed_confidence)
            SELECT
                r.mmsi,
                '{self.rule_id}' AS rule_id,
                json_object('n_cross', r.n_cross, 'n_unique_gates', r.n_unique_gates) AS detail,
                {self.type_code} AS proposed_type_code,
                {self.confidence} AS proposed_confidence
            FROM recent r
            LEFT JOIN ship_registry s ON s.mmsi = r.mmsi
            WHERE s.mmsi IS NULL OR s.confidence < {self.confidence}
        """)

        # Consolidate into registry
        result = con.execute(f"""
            INSERT INTO ship_registry (mmsi, ship_type_code, type_source, confidence, first_seen, last_seen, updated_at)
            SELECT
                a.mmsi,
                {self.type_code} AS ship_type_code,
                '{self.type_source}' AS type_source,
                MAX(a.proposed_confidence) AS confidence,
                COALESCE(r.first_seen, (SELECT MIN(msg_time) FROM ais_canon f WHERE f.mmsi = a.mmsi)) AS first_seen,
                COALESCE(r.last_seen, (SELECT MAX(msg_time) FROM ais_canon f WHERE f.mmsi = a.mmsi)) AS last_seen,
                NOW() AS updated_at
            FROM ship_registry_audit a
            LEFT JOIN ship_registry r ON r.mmsi = a.mmsi
            WHERE a.rule_id = '{self.rule_id}'
              AND a.ts >= NOW() - INTERVAL '1 hour'
            GROUP BY a.mmsi, r.first_seen, r.last_seen
            ON CONFLICT (mmsi) DO UPDATE SET
                ship_type_code = EXCLUDED.ship_type_code,
                type_source = EXCLUDED.type_source,
                confidence = EXCLUDED.confidence,
                last_seen = EXCLUDED.last_seen,
                updated_at = EXCLUDED.updated_at
            WHERE ship_registry.confidence IS NULL OR EXCLUDED.confidence > ship_registry.confidence
            RETURNING mmsi
        """)

        count = len(result.fetchall())
        con.commit()
        LOG.info(f"H3_CORRIDOR_FREQ: Classified {count} vessels (horizon={horizon_days}d, min_crossings={min_crossings})")
        return count


def apply_all_heuristics(
    con: duckdb.DuckDBPyConnection,
    horizon_days: int = 90,
    skip_rules: List[str] = None
) -> Dict[str, int]:
    """Apply all heuristic rules and return classification counts.

    Args:
        con: DuckDB connection
        horizon_days: Look back this many days
        skip_rules: Optional list of rule IDs to skip

    Returns:
        Dict mapping rule_id to number of vessels classified
    """
    skip_rules = skip_rules or []
    results = {}

    rules = [
        H1_TerminalDwell(),
        H2_STSZone(),
        H3_CorridorPattern(),
    ]

    for rule in rules:
        if rule.rule_id in skip_rules:
            LOG.info(f"Skipping {rule.rule_id}")
            continue

        try:
            count = rule.apply(con, horizon_days)
            results[rule.rule_id] = count
        except Exception as e:
            LOG.error(f"Failed to apply {rule.rule_id}: {e}", exc_info=True)
            results[rule.rule_id] = 0

    return results
