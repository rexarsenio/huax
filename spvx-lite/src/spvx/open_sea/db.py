"""DuckDB persistence helpers for open-sea analytics."""

from __future__ import annotations

import logging
import time
from contextlib import suppress
from pathlib import Path
from typing import Iterable

import duckdb

from spvx.open_sea.engine import (
    FixRecord,
    GateCrossing,
    PolygonEvent,
    PresenceRecord,
    ProcessingResult,
    TrackletRecord,
)

LOG = logging.getLogger(__name__)


class DuckDBWriter:
    def __init__(self, path: Path, max_retries: int = 5, retry_delay: float = 2.0):
        """Initialize DuckDB writer with retry logic for lock contention.
        
        Args:
            path: Path to the DuckDB file
            max_retries: Maximum number of connection attempts
            retry_delay: Initial delay between retries (exponential backoff)
        """
        self.path = path
        self.con = None
        
        last_error = None
        for attempt in range(max_retries):
            try:
                LOG.info("Attempting to connect to DuckDB at %s (attempt %d/%d)", path, attempt + 1, max_retries)
                self.con = duckdb.connect(str(path))
                self.con.execute("PRAGMA threads=4")
                LOG.info("Successfully connected to DuckDB at %s", path)
                return
            except duckdb.IOException as exc:
                last_error = exc
                error_msg = str(exc).lower()
                if "lock" in error_msg or "could not set lock" in error_msg:
                    wait_time = retry_delay * (2 ** attempt)
                    LOG.warning(
                        "DuckDB file is locked (attempt %d/%d). Waiting %.1f seconds before retry. "
                        "Error: %s",
                        attempt + 1,
                        max_retries,
                        wait_time,
                        exc,
                    )
                    if attempt < max_retries - 1:
                        time.sleep(wait_time)
                        continue
                else:
                    # Non-lock error, fail immediately
                    raise
            except Exception as exc:
                last_error = exc
                LOG.error("Unexpected error connecting to DuckDB: %s", exc)
                raise
        
        # All retries exhausted
        LOG.error(
            "Failed to connect to DuckDB after %d attempts. "
            "The database file is likely locked by another process. "
            "Use 'lsof %s' to identify the process holding the lock.",
            max_retries,
            path,
        )
        raise RuntimeError(
            f"Could not acquire DuckDB lock on {path} after {max_retries} attempts. "
            f"Last error: {last_error}"
        ) from last_error

    def close(self) -> None:
        with suppress(Exception):  # pragma: no cover - cleanup guard
            self.con.commit()
            self.con.close()

    def apply(self, result: ProcessingResult) -> None:
        if result.empty():
            return
        if result.fixes:
            self._insert_fixes(result.fixes)
        if result.polygon_events:
            self._insert_polygon_events(result.polygon_events)
        if result.presence_upserts:
            self._upsert_presence(result.presence_upserts)
        if result.gate_crossings:
            self._insert_gate_crossings(result.gate_crossings)
        if result.tracklets:
            self._upsert_tracklets(result.tracklets)
        self.con.commit()

    def _insert_fixes(self, fixes: Iterable[FixRecord]) -> None:
        data = [
            (
                record.mmsi,
                record.ts,
                record.lat,
                record.lon,
                record.sog,
                record.cog,
                record.shiptype_num,
                record.is_tanker,
            )
            for record in fixes
        ]
        self.con.executemany(
            """
            INSERT OR REPLACE INTO open_sea_fixes
            (mmsi, ts, lat, lon, sog, cog, shiptype_num, is_tanker)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            data,
        )

    def _insert_polygon_events(self, events: Iterable[PolygonEvent]) -> None:
        data = [
            (
                event.mmsi,
                event.polygon_id,
                event.event,
                event.ts,
                event.lat,
                event.lon,
                event.sog,
                event.cog,
            )
            for event in events
        ]
        # Note: Using simple INSERT - duplicates are filtered upstream
        self.con.executemany(
            """
            INSERT INTO polygon_events
            (mmsi, polygon_id, event, ts, lat, lon, sog, cog)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            data,
        )

    def _upsert_presence(self, records: Iterable[PresenceRecord]) -> None:
        data = [
            (
                rec.mmsi,
                rec.polygon_id,
                rec.enter_ts,
                rec.exit_ts,
                rec.last_seen_ts,
                rec.inside,
                rec.samples_inside,
                rec.sog_min,
                rec.sog_max,
                rec.sog_avg,
            )
            for rec in records
        ]
        self.con.executemany(
            """
            INSERT OR REPLACE INTO tanker_presence
            (mmsi, polygon_id, enter_ts, exit_ts, last_seen_ts, inside, samples_inside, sog_min, sog_max, sog_avg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            data,
        )

    def _insert_gate_crossings(self, crossings: Iterable[GateCrossing]) -> None:
        data = [
            (
                cross.mmsi,
                cross.gate_id,
                cross.ts,
                cross.direction,
                cross.lat,
                cross.lon,
                cross.sog,
                cross.cog,
            )
            for cross in crossings
        ]
        # Note: Using simple INSERT - duplicates are filtered upstream
        self.con.executemany(
            """
            INSERT INTO gate_crossings
            (mmsi, gate_id, ts, direction, lat, lon, sog, cog)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            data,
        )

    def _upsert_tracklets(self, tracklets: Iterable[TrackletRecord]) -> None:
        data = []
        for rec in tracklets:
            tracklet_id_value: int
            raw_id = rec.tracklet_id
            try:
                mmsi_part, ts_part = raw_id.split("-", 1)
                tracklet_id_value = int(mmsi_part) * 10_000_000_000 + int(ts_part)
            except Exception:
                # Fallback: hash to 64-bit positive integer
                tracklet_id_value = abs(hash(raw_id)) % (1 << 63)

            data.append(
                (
                    tracklet_id_value,
                    rec.mmsi,
                    rec.poly_from_id,
                    rec.poly_to_id,
                    rec.start_ts,
                    rec.end_ts,
                    rec.mean_sog,
                    rec.mean_cog,
                    rec.n_points,
                    "completed",
                )
            )

        self.con.executemany(
            """
            INSERT OR REPLACE INTO tracklets
            (tracklet_id, mmsi, poly_from_id, poly_to_id, start_ts, end_ts, mean_sog, mean_cog, n_fixes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            data,
        )
