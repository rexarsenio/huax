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
    min_confidence: float = 0.5  # Minimum confidence for episode (0-1)


def compute_dwell_confidence(sog_values: List[float], position_deltas: List[float],
                            time_deltas: List[float], config: AnchorageConfig) -> float:
    """
    Compute confidence score for dwell episode (research-grade).

    Uses multi-factor scoring with:
    - Speed stability (low SOG with spike filtering)
    - Position stability (minimal movement)
    - Time consistency (sufficient duration)

    Args:
        sog_values: List of SOG measurements (knots)
        position_deltas: List of position movements between fixes (nautical miles)
        time_deltas: List of time gaps between fixes (hours)
        config: Detection configuration

    Returns:
        Confidence score (0-1), where 1.0 = highest confidence
    """
    import numpy as np

    if len(sog_values) < 2:
        return 0.0

    # Convert to numpy arrays
    sog_arr = np.array(sog_values)
    pos_arr = np.array(position_deltas) if position_deltas else np.array([])
    time_arr = np.array(time_deltas) if time_deltas else np.array([])

    # === Factor 1: Speed Confidence (with spike filtering) ===
    # Use rolling median to remove GPS spikes
    window_size = min(5, len(sog_arr))
    if window_size >= 3:
        # Simple moving median (numpy doesn't have built-in rolling median)
        sog_smoothed = np.array([
            np.median(sog_arr[max(0, i-window_size//2):min(len(sog_arr), i+window_size//2+1)])
            for i in range(len(sog_arr))
        ])
    else:
        sog_smoothed = sog_arr

    # Fraction of time with low SOG
    low_sog_fraction = np.mean(sog_smoothed < config.sog_threshold_kn)

    # Stability (inverse of variance)
    sog_variance = np.var(sog_smoothed)
    sog_stability = np.exp(-sog_variance / 2.0)  # Exponential decay

    speed_conf = 0.7 * low_sog_fraction + 0.3 * sog_stability

    # === Factor 2: Position Confidence ===
    if len(pos_arr) > 0:
        # Median movement (robust to outliers)
        median_movement = np.median(pos_arr)

        # Exponential decay: high confidence if movement < 0.1 nm
        pos_threshold = 0.1  # nautical miles
        pos_conf = np.exp(-median_movement / pos_threshold)
    else:
        pos_conf = 0.5  # Neutral if no position data

    # === Factor 3: Time Consistency ===
    if len(time_arr) > 0:
        total_time_hours = np.sum(time_arr)

        # Sigmoid: confidence increases with duration
        # 50% confidence at 1 hour, 95% at 4 hours
        time_conf = 1.0 / (1.0 + np.exp(-(total_time_hours - 1.0)))
    else:
        time_conf = 0.5

    # === Weighted Geometric Mean ===
    # Geometric mean is more conservative than arithmetic mean
    weights = np.array([0.5, 0.3, 0.2])  # Speed > Position > Time
    factors = np.array([speed_conf, pos_conf, time_conf])

    # Weighted geometric mean: prod(factor^weight)
    confidence = np.prod(factors ** weights)

    return float(confidence)


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
    # Confidence tracking
    sog_values: list = None  # Track SOG over time
    position_deltas: list = None  # Track position movements (nm)
    time_deltas: list = None  # Track time between fixes (hours)

    def __post_init__(self):
        if self.sog_values is None:
            self.sog_values = []
        if self.position_deltas is None:
            self.position_deltas = []
        if self.time_deltas is None:
            self.time_deltas = []


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

                        # Track position delta
                        from math import radians, cos, sin, asin, sqrt
                        # Haversine distance in nautical miles
                        lon1, lat1 = radians(session.last_lon), radians(session.last_lat)
                        lon2, lat2 = radians(lon), radians(lat)
                        dlon = lon2 - lon1
                        dlat = lat2 - lat1
                        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
                        c = 2 * asin(sqrt(a))
                        distance_nm = 3440.065 * c  # Earth radius in nm

                        # Track time delta
                        time_delta_h = (ts - session.last_ts).total_seconds() / 3600

                        session.sog_values.append(sog if sog is not None else 0.0)
                        session.position_deltas.append(distance_nm)
                        session.time_deltas.append(time_delta_h)

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
                        # Initialize with first SOG
                        self.open_sessions[key].sog_values.append(sog if sog is not None else 0.0)

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
                                # RESEARCH-GRADE: Compute confidence score
                                confidence = compute_dwell_confidence(
                                    sog_values=session.sog_values,
                                    position_deltas=session.position_deltas,
                                    time_deltas=session.time_deltas,
                                    config=self.config
                                )

                                # Only create episode if confidence meets threshold
                                if confidence >= self.config.min_confidence:
                                    episode = AnchorageEpisode(
                                        mmsi=mmsi,
                                        anchorage_id=sess_anch,
                                        ts_entry=session.enter_ts,
                                        ts_exit=session.last_ts,
                                        dwell_h=dwell_h,
                                        fixes_n=session.fix_count
                                    )
                                    self._save_episode(episode, confidence=confidence)
                                    episodes_created += 1
                                else:
                                    LOG.debug(
                                        f"Rejected episode for {mmsi} at {sess_anch}: "
                                        f"confidence {confidence:.2f} < {self.config.min_confidence:.2f}"
                                    )

                            # Remove session
                            del self.open_sessions[key]

        # Persist open sessions
        self._save_open_sessions()

        LOG.info(f"Created {episodes_created} new episodes, {len(self.open_sessions)} sessions remain open")

    def _save_episode(self, episode: AnchorageEpisode, confidence: float = 1.0):
        """Save episode to database with confidence score."""
        episode_id = f"EP_{episode.anchorage_id}_{episode.mmsi}_{int(episode.ts_entry.timestamp())}"

        # Add confidence column if it doesn't exist
        try:
            self.con.execute("ALTER TABLE anchorage_episodes ADD COLUMN IF NOT EXISTS confidence DOUBLE DEFAULT 1.0")
        except:
            pass

        self.con.execute("""
            INSERT OR REPLACE INTO anchorage_episodes
            (episode_id, anchorage_id, mmsi, ts_entry, ts_exit, dwell_hours, t_in, t_out, dwell_h, fixes_n, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            episode.fixes_n,
            confidence
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
