"""
Anchorage Episode Detection (TH-2)

Detects when vessels enter/exit anchorage areas and computes dwell times.
Similar to polygon_detect.py but optimized for anchorage monitoring.
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
class AnchorageConfig:
    """Configuration for anchorage detection."""
    hysteresis_nm: float = 0.5  # Stay "inside" if within this distance
    ttl_out_min: int = 30  # Minutes before considering vessel truly exited
    min_dwell_min: int = 60  # Minimum dwell time to record (1 hour)
    sog_threshold_kn: float = 1.0  # Consider anchored if SOG < 1 knot


@dataclass
class AnchorageFeature:
    """An anchorage feature from polygons."""
    anchorage_id: str
    name: str
    geometry: Polygon


@dataclass
class OpenSession:
    """An open vessel-anchorage session."""
    mmsi: int
    anchorage_id: str
    enter_ts: datetime
    last_ts: datetime
    last_lon: float
    last_lat: float
    fix_count: int


@dataclass
class AnchorageEpisode:
    """A completed anchorage dwell episode."""
    mmsi: int
    anchorage_id: str
    ts_entry: datetime
    ts_exit: datetime
    dwell_h: float
    fixes_n: int


class AnchorageDetector:
    """
    Streaming anchorage detection engine.

    Maintains state for all active vessel-anchorage sessions and emits
    episodes when vessels complete dwells meeting minimum thresholds.
    """

    def __init__(
        self,
        con: duckdb.DuckDBPyConnection,
        polygons_geojson: str,
        config: Optional[AnchorageConfig] = None
    ):
        """Initialize anchorage detector.

        Args:
            con: DuckDB connection for persisting sessions/episodes
            polygons_geojson: Path to anchorages GeoJSON
            config: Detection configuration
        """
        self.con = con
        self.config = config or AnchorageConfig()

        # Load polygons
        self.anchorages = self._load_anchorages(polygons_geojson)

        # Build spatial index
        self.tree = STRtree([a.geometry for a in self.anchorages])

        # In-memory state: (mmsi, anchorage_id) -> OpenSession
        self.open_sessions: Dict[Tuple[int, str], OpenSession] = {}

        # Ensure tables exist
        self._ensure_tables()

        # Load any existing open sessions (crash recovery)
        self._load_open_sessions()

        LOG.info(
            f"AnchorageDetector initialized: {len(self.anchorages)} anchorages, "
            f"{len(self.open_sessions)} open sessions"
        )

    def _load_anchorages(self, path: str) -> List[AnchorageFeature]:
        """Load anchorage features from GeoJSON."""
        anchorages = []

        geojson_path = Path(path)
        if not geojson_path.exists():
            LOG.warning(f"Anchorage file not found: {path}")
            return anchorages

        with open(geojson_path) as f:
            data = json.load(f)

        for feature in data.get('features', []):
            props = feature.get('properties', {})
            geom = shape(feature['geometry'])

            # Only use ANCHORAGE polygons
            kind = props.get('kind', '')
            if 'ANCHORAGE' not in kind.upper() and 'ANCH' not in props.get('id', '').upper():
                continue

            anchorages.append(AnchorageFeature(
                anchorage_id=props.get('id', f'ANCH_{len(anchorages)}'),
                name=props.get('name', 'Unknown Anchorage'),
                geometry=geom if isinstance(geom, Polygon) else geom.convex_hull
            ))

        LOG.info(f"Loaded {len(anchorages)} anchorage polygons from {path}")
        return anchorages

    def _ensure_tables(self):
        """Create tables for sessions and episodes."""
        # Open sessions table (for crash recovery)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS anchorage_open_sessions (
                mmsi BIGINT,
                anchorage_id VARCHAR,
                enter_ts TIMESTAMP,
                last_ts TIMESTAMP,
                last_lon DOUBLE,
                last_lat DOUBLE,
                fix_count INTEGER,
                PRIMARY KEY (mmsi, anchorage_id)
            )
        """)

        # Episodes table
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS anchorage_episodes (
                episode_id VARCHAR PRIMARY KEY,
                anchorage_id VARCHAR,
                mmsi BIGINT,
                vessel_name VARCHAR,
                ts_entry TIMESTAMP,
                ts_exit TIMESTAMP,
                dwell_hours DOUBLE,
                t_in TIMESTAMP,
                t_out TIMESTAMP,
                dwell_h DOUBLE,
                fixes_n INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def _load_open_sessions(self):
        """Load open sessions from database (crash recovery)."""
        try:
            rows = self.con.execute("""
                SELECT mmsi, anchorage_id, enter_ts, last_ts, last_lon, last_lat, fix_count
                FROM anchorage_open_sessions
            """).fetchall()

            for row in rows:
                mmsi, anch_id, enter_ts, last_ts, lon, lat, fixes = row
                self.open_sessions[(mmsi, anch_id)] = OpenSession(
                    mmsi=mmsi,
                    anchorage_id=anch_id,
                    enter_ts=enter_ts,
                    last_ts=last_ts,
                    last_lon=lon,
                    last_lat=lat,
                    fix_count=fixes
                )

        except Exception as e:
            LOG.warning(f"Could not load open sessions: {e}")

    def process_fixes(self, start_ts: Optional[datetime] = None, end_ts: Optional[datetime] = None):
        """
        Process AIS fixes and detect anchorage episodes.

        Args:
            start_ts: Process fixes from this timestamp (default: last processed)
            end_ts: Process fixes until this timestamp (default: now)
        """
        if not self.anchorages:
            LOG.warning("No anchorages defined, skipping detection")
            return

        # Get watermark
        if start_ts is None:
            try:
                watermark = self.con.execute("""
                    SELECT MAX(ts_exit) FROM anchorage_episodes
                """).fetchone()[0]
                start_ts = watermark if watermark else datetime(2020, 1, 1)
            except:
                start_ts = datetime(2020, 1, 1)

        if end_ts is None:
            end_ts = datetime.utcnow()

        LOG.info(f"Processing AIS fixes from {start_ts} to {end_ts}")

        # Query AIS fixes
        query = """
            SELECT
                mmsi,
                ts,
                lon,
                lat,
                sog,
                is_tanker
            FROM open_sea_fixes
            WHERE ts >= ? AND ts <= ?
              AND lon IS NOT NULL
              AND lat IS NOT NULL
            ORDER BY mmsi, ts
        """

        fixes = self.con.execute(query, [start_ts, end_ts]).fetchall()
        LOG.info(f"Processing {len(fixes):,} AIS fixes")

        episodes_created = 0

        # Group by vessel
        from itertools import groupby
        for mmsi, vessel_fixes in groupby(fixes, key=lambda x: x[0]):
            vessel_fixes = list(vessel_fixes)

            for fix in vessel_fixes:
                mmsi, ts, lon, lat, sog, is_tanker = fix
                point = Point(lon, lat)

                # Check which anchorages contain this point
                indices = self.tree.query(point)
                containing_anchorages = [
                    self.anchorages[i] for i in indices
                    if self.anchorages[i].geometry.contains(point)
                ]

                # Process each anchorage
                for anch in containing_anchorages:
                    key = (mmsi, anch.anchorage_id)

                    if key in self.open_sessions:
                        # Update existing session
                        session = self.open_sessions[key]
                        session.last_ts = ts
                        session.last_lon = lon
                        session.last_lat = lat
                        session.fix_count += 1
                    else:
                        # Start new session
                        self.open_sessions[key] = OpenSession(
                            mmsi=mmsi,
                            anchorage_id=anch.anchorage_id,
                            enter_ts=ts,
                            last_ts=ts,
                            last_lon=lon,
                            last_lat=lat,
                            fix_count=1
                        )

                # Close sessions for anchorages vessel has left
                for (sess_mmsi, sess_anch), session in list(self.open_sessions.items()):
                    if sess_mmsi != mmsi:
                        continue

                    # Check if vessel is still in this anchorage
                    if sess_anch not in [a.anchorage_id for a in containing_anchorages]:
                        # Vessel has left
                        time_since_last = (ts - session.last_ts).total_seconds() / 60

                        if time_since_last > self.config.ttl_out_min:
                            # Close session
                            dwell_h = (session.last_ts - session.enter_ts).total_seconds() / 3600

                            if dwell_h * 60 >= self.config.min_dwell_min:
                                # Create episode
                                episode = AnchorageEpisode(
                                    mmsi=mmsi,
                                    anchorage_id=sess_anch,
                                    ts_entry=session.enter_ts,
                                    ts_exit=session.last_ts,
                                    dwell_h=dwell_h,
                                    fixes_n=session.fix_count
                                )
                                self._save_episode(episode)
                                episodes_created += 1

                            # Remove session
                            del self.open_sessions[key]

        # Persist open sessions
        self._save_open_sessions()

        LOG.info(f"Created {episodes_created} new episodes, {len(self.open_sessions)} sessions remain open")

    def _save_episode(self, episode: AnchorageEpisode):
        """Save episode to database."""
        episode_id = f"EP_{episode.anchorage_id}_{episode.mmsi}_{int(episode.ts_entry.timestamp())}"

        self.con.execute("""
            INSERT OR REPLACE INTO anchorage_episodes
            (episode_id, anchorage_id, mmsi, ts_entry, ts_exit, dwell_hours, t_in, t_out, dwell_h, fixes_n)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            episode_id,
            episode.anchorage_id,
            episode.mmsi,
            episode.ts_entry,
            episode.ts_exit,
            episode.dwell_h,
            episode.ts_entry,
            episode.ts_exit,
            episode.dwell_h,
            episode.fixes_n
        ])

    def _save_open_sessions(self):
        """Persist open sessions to database."""
        self.con.execute("DELETE FROM anchorage_open_sessions")

        for (mmsi, anch_id), session in self.open_sessions.items():
            self.con.execute("""
                INSERT INTO anchorage_open_sessions
                (mmsi, anchorage_id, enter_ts, last_ts, last_lon, last_lat, fix_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                mmsi,
                anch_id,
                session.enter_ts,
                session.last_ts,
                session.last_lon,
                session.last_lat,
                session.fix_count
            ])

        self.con.commit()
