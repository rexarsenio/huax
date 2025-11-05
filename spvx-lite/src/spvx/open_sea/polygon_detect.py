"""Polygon detection engine for streaming AIS fixes.

Detects when vessels enter/exit polygons (oil terminals, STS zones) and
generates polygon_events with dwell times.

Features:
- Shapely STRtree for fast point-in-polygon queries
- State machine per (mmsi, polygon_id) with hysteresis
- TTL for temporary signal loss
- Crash-safe with open sessions table
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb
from shapely import STRtree
from shapely.geometry import Point, Polygon, shape

LOG = logging.getLogger(__name__)


@dataclass
class PolygonConfig:
    """Configuration for polygon detection."""
    hysteresis_nm: float = 0.5  # Stay "inside" if within this distance
    ttl_out_min: int = 15  # Minutes before considering vessel truly exited
    min_dwell_terminal_min: int = 120  # Minimum dwell for terminals
    min_dwell_sts_min: int = 360  # Minimum dwell for STS zones


@dataclass
class PolygonFeature:
    """A polygon feature from GeoJSON."""
    polygon_id: str
    kind: str  # OIL_TERMINAL or STS_ZONE
    name: str
    geometry: Polygon
    min_dwell_min: int


@dataclass
class OpenSession:
    """An open vessel-polygon session."""
    mmsi: int
    polygon_id: str
    kind: str
    enter_ts: datetime
    last_ts: datetime
    last_lon: float
    last_lat: float


@dataclass
class PolygonEvent:
    """A completed polygon dwell event."""
    mmsi: int
    polygon_id: str
    kind: str
    ts_in: datetime
    ts_out: datetime
    dwell_min: int
    centroid_lon: float
    centroid_lat: float


class PolygonDetector:
    """Streaming polygon detection engine.

    Maintains state for all active vessel-polygon sessions and emits
    events when vessels complete dwells meeting minimum thresholds.
    """

    def __init__(
        self,
        con: duckdb.DuckDBPyConnection,
        terminal_geojson: str,
        sts_geojson: str,
        config: Optional[PolygonConfig] = None
    ):
        """Initialize polygon detector.

        Args:
            con: DuckDB connection for persisting sessions/events
            terminal_geojson: Path to oil terminals GeoJSON
            sts_geojson: Path to STS zones GeoJSON
            config: Detection configuration
        """
        self.con = con
        self.config = config or PolygonConfig()

        # Load polygons
        self.polygons = self._load_polygons(terminal_geojson, sts_geojson)

        # Build spatial index
        self.tree = STRtree([p.geometry for p in self.polygons])

        # In-memory state: (mmsi, polygon_id) -> OpenSession
        self.open_sessions: Dict[Tuple[int, str], OpenSession] = {}

        # Ensure tables exist
        self._ensure_tables()

        # Load any existing open sessions (crash recovery)
        self._load_open_sessions()

        LOG.info(
            f"PolygonDetector initialized: {len(self.polygons)} polygons, "
            f"{len(self.open_sessions)} open sessions"
        )

    def _load_polygons(self, terminal_path: str, sts_path: str) -> List[PolygonFeature]:
        """Load polygon features from GeoJSON files."""
        polygons = []

        # Load terminals
        if Path(terminal_path).exists():
            with open(terminal_path) as f:
                data = json.load(f)
                for feature in data.get('features', []):
                    props = feature.get('properties', {})
                    geom = shape(feature['geometry'])

                    polygons.append(PolygonFeature(
                        polygon_id=props['id'],
                        kind='OIL_TERMINAL',
                        name=props.get('name', props['id']),
                        geometry=geom,
                        min_dwell_min=self.config.min_dwell_terminal_min
                    ))
            LOG.info(f"Loaded {len(polygons)} oil terminals from {terminal_path}")

        # Load STS zones
        sts_count = 0
        if Path(sts_path).exists():
            with open(sts_path) as f:
                data = json.load(f)
                for feature in data.get('features', []):
                    props = feature.get('properties', {})
                    geom = shape(feature['geometry'])

                    polygons.append(PolygonFeature(
                        polygon_id=props['id'],
                        kind='STS_ZONE',
                        name=props.get('name', props['id']),
                        geometry=geom,
                        min_dwell_min=self.config.min_dwell_sts_min
                    ))
                    sts_count += 1
            LOG.info(f"Loaded {sts_count} STS zones from {sts_path}")

        return polygons

    def _ensure_tables(self):
        """Create polygon_events and polygon_sessions_open tables."""

        # Events table
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS polygon_events (
                mmsi BIGINT,
                polygon_id VARCHAR,
                kind VARCHAR,
                ts_in TIMESTAMP,
                ts_out TIMESTAMP,
                dwell_min INTEGER,
                centroid_lon DOUBLE,
                centroid_lat DOUBLE,
                PRIMARY KEY (mmsi, polygon_id, ts_in)
            )
        """)

        # Open sessions table (for crash recovery)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS polygon_sessions_open (
                mmsi BIGINT,
                polygon_id VARCHAR,
                kind VARCHAR,
                enter_ts TIMESTAMP,
                last_ts TIMESTAMP,
                last_lon DOUBLE,
                last_lat DOUBLE,
                PRIMARY KEY (mmsi, polygon_id)
            )
        """)

        # Create indexes
        try:
            self.con.execute("CREATE INDEX IF NOT EXISTS idx_polygon_events_mmsi ON polygon_events(mmsi)")
            self.con.execute("CREATE INDEX IF NOT EXISTS idx_polygon_events_ts ON polygon_events(ts_in)")
            self.con.execute("CREATE INDEX IF NOT EXISTS idx_polygon_events_polygon ON polygon_events(polygon_id)")
        except Exception as e:
            LOG.warning(f"Failed to create some indexes: {e}")

    def _load_open_sessions(self):
        """Load open sessions from database (crash recovery)."""
        result = self.con.execute("""
            SELECT mmsi, polygon_id, kind, enter_ts, last_ts, last_lon, last_lat
            FROM polygon_sessions_open
        """).fetchall()

        for row in result:
            mmsi, polygon_id, kind, enter_ts, last_ts, last_lon, last_lat = row
            key = (mmsi, polygon_id)
            self.open_sessions[key] = OpenSession(
                mmsi=mmsi,
                polygon_id=polygon_id,
                kind=kind,
                enter_ts=enter_ts,
                last_ts=last_ts,
                last_lon=last_lon,
                last_lat=last_lat
            )

    def handle_fix(
        self,
        mmsi: int,
        ts: datetime,
        lon: float,
        lat: float,
        sog: float = 0.0
    ) -> List[PolygonEvent]:
        """Process a single AIS fix and return any completed events.

        Args:
            mmsi: Vessel MMSI
            ts: Fix timestamp
            lon: Longitude
            lat: Latitude
            sog: Speed over ground (knots)

        Returns:
            List of completed PolygonEvents (may be empty)
        """
        point = Point(lon, lat)
        events = []

        # Find which polygons contain this point
        intersecting_indices = self.tree.query(point, predicate='intersects')
        current_polygons = {self.polygons[i].polygon_id for i in intersecting_indices}

        # Get all polygons this vessel currently has open sessions for
        vessel_sessions = {
            poly_id: session
            for (m, poly_id), session in self.open_sessions.items()
            if m == mmsi
        }

        # Handle entries (new polygons)
        for poly_id in current_polygons:
            key = (mmsi, poly_id)
            if key not in self.open_sessions:
                # New entry
                polygon = next(p for p in self.polygons if p.polygon_id == poly_id)
                self.open_sessions[key] = OpenSession(
                    mmsi=mmsi,
                    polygon_id=poly_id,
                    kind=polygon.kind,
                    enter_ts=ts,
                    last_ts=ts,
                    last_lon=lon,
                    last_lat=lat
                )
                LOG.debug(f"[ENTER] MMSI {mmsi} entered {poly_id} at {ts}")
            else:
                # Update existing session
                self.open_sessions[key].last_ts = ts
                self.open_sessions[key].last_lon = lon
                self.open_sessions[key].last_lat = lat

        # Handle exits (check sessions not in current polygons)
        for poly_id, session in list(vessel_sessions.items()):
            if poly_id not in current_polygons:
                # Vessel no longer in this polygon
                key = (mmsi, poly_id)

                # Check hysteresis: if close enough or SOG low, keep session open
                distance_nm = self._distance_nm(
                    lon, lat,
                    session.last_lon, session.last_lat
                )

                # Check TTL: if too long since last fix, close session
                time_since_last = (ts - session.last_ts).total_seconds() / 60

                if distance_nm <= self.config.hysteresis_nm and sog < 1.0:
                    # Hysteresis: still consider "inside"
                    self.open_sessions[key].last_ts = ts
                    self.open_sessions[key].last_lon = lon
                    self.open_sessions[key].last_lat = lat
                elif time_since_last > self.config.ttl_out_min:
                    # TTL expired, close session
                    event = self._close_session(session, session.last_ts)
                    if event:
                        events.append(event)
                    del self.open_sessions[key]
                    LOG.debug(f"[EXIT/TTL] MMSI {mmsi} exited {poly_id} (TTL expired)")
                else:
                    # True exit
                    event = self._close_session(session, ts)
                    if event:
                        events.append(event)
                    del self.open_sessions[key]
                    LOG.debug(f"[EXIT] MMSI {mmsi} exited {poly_id} at {ts}")

        return events

    def _close_session(self, session: OpenSession, exit_ts: datetime) -> Optional[PolygonEvent]:
        """Close a session and return event if dwell meets minimum."""
        dwell_seconds = (exit_ts - session.enter_ts).total_seconds()
        dwell_min = int(dwell_seconds / 60)

        # Find polygon config
        polygon = next(p for p in self.polygons if p.polygon_id == session.polygon_id)

        if dwell_min >= polygon.min_dwell_min:
            # Compute centroid (average of enter/exit positions)
            centroid_lon = session.last_lon
            centroid_lat = session.last_lat

            event = PolygonEvent(
                mmsi=session.mmsi,
                polygon_id=session.polygon_id,
                kind=session.kind,
                ts_in=session.enter_ts,
                ts_out=exit_ts,
                dwell_min=dwell_min,
                centroid_lon=centroid_lon,
                centroid_lat=centroid_lat
            )

            # Write to database
            self._write_event(event)

            LOG.info(
                f"[EVENT] MMSI {session.mmsi} dwelled at {session.polygon_id} "
                f"for {dwell_min} min ({session.kind})"
            )
            return event
        else:
            LOG.debug(
                f"[DISCARD] MMSI {session.mmsi} at {session.polygon_id}: "
                f"dwell {dwell_min} min < {polygon.min_dwell_min} min threshold"
            )
            return None

    def _write_event(self, event: PolygonEvent):
        """Write completed event to database."""
        self.con.execute("""
            INSERT INTO polygon_events (mmsi, polygon_id, kind, ts_in, ts_out, dwell_min, centroid_lon, centroid_lat)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (mmsi, polygon_id, ts_in) DO NOTHING
        """, [
            event.mmsi,
            event.polygon_id,
            event.kind,
            event.ts_in,
            event.ts_out,
            event.dwell_min,
            event.centroid_lon,
            event.centroid_lat
        ])

    def flush(self):
        """Flush all open sessions to database for crash recovery."""
        # Clear existing
        self.con.execute("DELETE FROM polygon_sessions_open")

        # Write current open sessions
        for session in self.open_sessions.values():
            self.con.execute("""
                INSERT INTO polygon_sessions_open (mmsi, polygon_id, kind, enter_ts, last_ts, last_lon, last_lat)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (mmsi, polygon_id) DO UPDATE SET
                    last_ts = EXCLUDED.last_ts,
                    last_lon = EXCLUDED.last_lon,
                    last_lat = EXCLUDED.last_lat
            """, [
                session.mmsi,
                session.polygon_id,
                session.kind,
                session.enter_ts,
                session.last_ts,
                session.last_lon,
                session.last_lat
            ])

        self.con.commit()
        LOG.debug(f"Flushed {len(self.open_sessions)} open sessions to database")

    def finalize(self, current_ts: datetime) -> List[PolygonEvent]:
        """Close all open sessions (for shutdown). Returns list of events."""
        events = []
        for session in list(self.open_sessions.values()):
            event = self._close_session(session, current_ts)
            if event:
                events.append(event)

        # Clear open sessions
        self.open_sessions.clear()
        self.con.execute("DELETE FROM polygon_sessions_open")
        self.con.commit()

        LOG.info(f"Finalized detector: {len(events)} events generated")
        return events

    @staticmethod
    def _distance_nm(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
        """Calculate distance in nautical miles using haversine formula."""
        from math import radians, sin, cos, sqrt, atan2

        R = 3440.065  # Earth radius in nautical miles

        lat1_rad, lon1_rad = radians(lat1), radians(lon1)
        lat2_rad, lon2_rad = radians(lat2), radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))

        return R * c
