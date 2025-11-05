"""
State machine for open-sea polygon occupancy, gate crossings, and tracklets.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from shapely.geometry import LineString, Point

from spvx.open_sea.config import OpenSeaConfig
from spvx.open_sea.geo import GateFeature, PolygonFeature, point_from_latlon


@dataclass(frozen=True)
class Observation:
    ts: dt.datetime
    lat: float
    lon: float
    sog: float
    cog: Optional[float]
    shiptype_num: Optional[int]
    is_tanker: bool


@dataclass
class Fix:
    observation: Observation
    point_mercator: Point


@dataclass
class PolygonPresence:
    inside: bool = False
    hits_inside: int = 0
    hits_outside: int = 0
    enter_ts: Optional[dt.datetime] = None
    exit_ts: Optional[dt.datetime] = None
    last_seen_ts: Optional[dt.datetime] = None
    samples_inside: int = 0
    sog_min: Optional[float] = None
    sog_max: Optional[float] = None
    sog_sum: float = 0.0
    sog_samples: int = 0

    def register_inside(self, obs: Observation) -> None:
        self.hits_inside += 1
        self.hits_outside = 0
        self.last_seen_ts = obs.ts
        self.samples_inside += 1
        self.sog_sum += obs.sog
        self.sog_samples += 1
        if self.sog_min is None or obs.sog < self.sog_min:
            self.sog_min = obs.sog
        if self.sog_max is None or obs.sog > self.sog_max:
            self.sog_max = obs.sog

    def register_outside(self, obs: Observation) -> None:
        self.hits_inside = 0
        self.hits_outside += 1
        self.last_seen_ts = obs.ts

    def reset_stats(self) -> None:
        self.samples_inside = 0
        self.sog_min = None
        self.sog_max = None
        self.sog_sum = 0.0
        self.sog_samples = 0

    @property
    def sog_avg(self) -> Optional[float]:
        if self.sog_samples == 0:
            return None
        return self.sog_sum / self.sog_samples


@dataclass
class VesselState:
    last_bucket: Optional[dt.datetime] = None
    last_fix: Optional[Fix] = None
    polygon_states: Dict[str, PolygonPresence] = field(default_factory=dict)
    gate_last_cross: Dict[Tuple[str, str], dt.datetime] = field(default_factory=dict)
    track_buffer: deque = field(default_factory=deque)
    last_tracklet_end: Optional[dt.datetime] = None
    is_tanker: bool = False
    shiptype_num: Optional[int] = None


@dataclass
class FixRecord:
    mmsi: int
    ts: dt.datetime
    lat: float
    lon: float
    sog: float
    cog: Optional[float]
    shiptype_num: Optional[int]
    is_tanker: bool


@dataclass
class PolygonEvent:
    mmsi: int
    polygon_id: str
    event: str
    ts: dt.datetime
    lat: float
    lon: float
    sog: float
    cog: Optional[float]


@dataclass
class PresenceRecord:
    mmsi: int
    polygon_id: str
    enter_ts: Optional[dt.datetime]
    exit_ts: Optional[dt.datetime]
    last_seen_ts: Optional[dt.datetime]
    inside: bool
    samples_inside: int
    sog_min: Optional[float]
    sog_max: Optional[float]
    sog_avg: Optional[float]


@dataclass
class GateCrossing:
    mmsi: int
    gate_id: str
    ts: dt.datetime
    direction: str
    lat: float
    lon: float
    sog: float
    cog: Optional[float]


@dataclass
class TrackletRecord:
    tracklet_id: str
    mmsi: int
    start_ts: dt.datetime
    end_ts: dt.datetime
    n_points: int
    mean_cog: float
    mean_sog: float
    poly_from_id: Optional[str]
    poly_to_id: Optional[str]


@dataclass
class ProcessingResult:
    fixes: List[FixRecord] = field(default_factory=list)
    polygon_events: List[PolygonEvent] = field(default_factory=list)
    presence_upserts: List[PresenceRecord] = field(default_factory=list)
    gate_crossings: List[GateCrossing] = field(default_factory=list)
    tracklets: List[TrackletRecord] = field(default_factory=list)
    teleport_events: List[int] = field(default_factory=list)

    def extend(self, other: "ProcessingResult") -> None:
        self.fixes.extend(other.fixes)
        self.polygon_events.extend(other.polygon_events)
        self.presence_upserts.extend(other.presence_upserts)
        self.gate_crossings.extend(other.gate_crossings)
        self.tracklets.extend(other.tracklets)
        self.teleport_events.extend(other.teleport_events)

    def empty(self) -> bool:
        return (
            not self.fixes
            and not self.polygon_events
            and not self.presence_upserts
            and not self.gate_crossings
            and not self.tracklets
            and not self.teleport_events
        )


class OpenSeaEngine:
    """Core state machine for open-sea analytics."""

    TRACKLET_MIN = dt.timedelta(minutes=5)
    TRACKLET_MAX = dt.timedelta(minutes=15)
    GATE_DEDUP = dt.timedelta(minutes=5)

    def __init__(self, config: OpenSeaConfig, polygons: Iterable[PolygonFeature], gates: Iterable[GateFeature]):
        self.config = config
        self.polygons: Dict[str, PolygonFeature] = {p.feature_id: p for p in polygons}
        self.gates: Dict[str, GateFeature] = {g.feature_id: g for g in gates}
        self.vessels: Dict[int, VesselState] = {}

    def _ensure_vessel(self, mmsi: int) -> VesselState:
        if mmsi not in self.vessels:
            self.vessels[mmsi] = VesselState()
        return self.vessels[mmsi]

    def process_observation(self, mmsi: int, obs: Observation) -> ProcessingResult:
        state = self._ensure_vessel(mmsi)
        if obs.shiptype_num is not None:
            state.shiptype_num = obs.shiptype_num
            if 80 <= obs.shiptype_num <= 89:
                state.is_tanker = True
        if obs.is_tanker:
            state.is_tanker = True
        if not state.is_tanker:
            return ProcessingResult()

        if obs.ts.tzinfo is None:
            obs = Observation(
                ts=obs.ts.replace(tzinfo=dt.timezone.utc),
                lat=obs.lat,
                lon=obs.lon,
                sog=obs.sog,
                cog=obs.cog,
                shiptype_num=obs.shiptype_num,
                is_tanker=obs.is_tanker,
            )

        bucket = self._bucket_timestamp(obs.ts)
        if state.last_bucket and bucket <= state.last_bucket:
            # Skip duplicate or out-of-order observations after downsampling.
            return ProcessingResult()
        state.last_bucket = bucket

        if state.last_fix and obs.ts <= state.last_fix.observation.ts:
            return ProcessingResult()

        teleport = False
        if state.last_fix:
            prev_obs = state.last_fix.observation
            delta = (obs.ts - prev_obs.ts).total_seconds() if obs.ts and prev_obs.ts else 0.0
            if delta > 0:
                dist_nm = _distance_nm(prev_obs.lat, prev_obs.lon, obs.lat, obs.lon)
                speed_knots = dist_nm / (delta / 3600.0)
                if speed_knots > 40.0:
                    teleport = True

        fix_point = point_from_latlon(obs.lat, obs.lon)
        fix = Fix(observation=obs, point_mercator=fix_point)
        prev_fix = state.last_fix
        state.last_fix = fix

        result = ProcessingResult()
        result.fixes.append(
            FixRecord(
                mmsi=mmsi,
                ts=obs.ts,
                lat=obs.lat,
                lon=obs.lon,
                sog=obs.sog,
                cog=obs.cog,
                shiptype_num=obs.shiptype_num,
                is_tanker=state.is_tanker,
            )
        )

        result.extend(self._update_polygons(mmsi, state, fix))
        result.extend(self._detect_gate_crossings(mmsi, state, prev_fix, fix))
        result.extend(self._maybe_emit_tracklet(mmsi, state))
        if teleport:
            result.teleport_events.append(mmsi)

        return result

    def expire_stale(self, now: dt.datetime) -> ProcessingResult:
        if now.tzinfo is None:
            now = now.replace(tzinfo=dt.timezone.utc)
        result = ProcessingResult()
        ttl_moving = dt.timedelta(minutes=self.config.ttl_min.moving)
        ttl_anchorage = dt.timedelta(minutes=self.config.ttl_min.anchorage)

        for mmsi, state in list(self.vessels.items()):
            if not state.polygon_states:
                continue
            for poly_id, presence in state.polygon_states.items():
                if not presence.inside:
                    continue
                last_seen = presence.last_seen_ts
                if last_seen is None:
                    continue
                feature = self.polygons.get(poly_id)
                ttl = ttl_anchorage if feature and feature.kind.upper() == "ANCHORAGE" else ttl_moving
                if now - last_seen > ttl:
                    fix = state.last_fix
                    lat = fix.observation.lat if fix else float("nan")
                    lon = fix.observation.lon if fix else float("nan")
                    sog = fix.observation.sog if fix else float("nan")
                    cog = fix.observation.cog if fix else None
                    presence.inside = False
                    presence.exit_ts = last_seen
                    result.polygon_events.append(
                        PolygonEvent(
                            mmsi=mmsi,
                            polygon_id=poly_id,
                            event="exit",
                            ts=last_seen,
                            lat=lat,
                            lon=lon,
                            sog=sog,
                            cog=cog,
                        )
                    )
                    result.presence_upserts.append(
                        PresenceRecord(
                            mmsi=mmsi,
                            polygon_id=poly_id,
                            enter_ts=presence.enter_ts,
                            exit_ts=presence.exit_ts,
                            last_seen_ts=presence.last_seen_ts,
                            inside=False,
                            samples_inside=presence.samples_inside,
                            sog_min=presence.sog_min,
                            sog_max=presence.sog_max,
                            sog_avg=presence.sog_avg,
                        )
                    )
                    presence.enter_ts = None
                    presence.reset_stats()
        return result

    def _bucket_timestamp(self, ts: dt.datetime) -> dt.datetime:
        epoch = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
        total_seconds = int((ts - epoch).total_seconds())
        bucket_seconds = (total_seconds // self.config.downsample_secs) * self.config.downsample_secs
        return epoch + dt.timedelta(seconds=bucket_seconds)

    def _update_polygons(self, mmsi: int, state: VesselState, fix: Fix) -> ProcessingResult:
        result = ProcessingResult()
        obs = fix.observation
        for polygon_id, feature in self.polygons.items():
            presence = state.polygon_states.setdefault(polygon_id, PolygonPresence())
            inside = feature.contains_point(fix.point_mercator)
            if inside:
                presence.register_inside(obs)
                if not presence.inside and presence.hits_inside >= self.config.hysteresis_hits:
                    presence.inside = True
                    presence.enter_ts = obs.ts
                    result.polygon_events.append(
                        PolygonEvent(
                            mmsi=mmsi,
                            polygon_id=polygon_id,
                            event="enter",
                            ts=obs.ts,
                            lat=obs.lat,
                            lon=obs.lon,
                            sog=obs.sog,
                            cog=obs.cog,
                        )
                    )
                result.presence_upserts.append(
                    PresenceRecord(
                        mmsi=mmsi,
                        polygon_id=polygon_id,
                        enter_ts=presence.enter_ts,
                        exit_ts=presence.exit_ts,
                        last_seen_ts=presence.last_seen_ts,
                        inside=presence.inside,
                        samples_inside=presence.samples_inside,
                        sog_min=presence.sog_min,
                        sog_max=presence.sog_max,
                        sog_avg=presence.sog_avg,
                    )
                )
            else:
                presence.register_outside(obs)
                if presence.inside and presence.hits_outside >= self.config.hysteresis_hits:
                    presence.inside = False
                    presence.exit_ts = obs.ts
                    result.polygon_events.append(
                        PolygonEvent(
                            mmsi=mmsi,
                            polygon_id=polygon_id,
                            event="exit",
                            ts=obs.ts,
                            lat=obs.lat,
                            lon=obs.lon,
                            sog=obs.sog,
                            cog=obs.cog,
                        )
                    )
                    result.presence_upserts.append(
                        PresenceRecord(
                            mmsi=mmsi,
                            polygon_id=polygon_id,
                            enter_ts=presence.enter_ts,
                            exit_ts=presence.exit_ts,
                            last_seen_ts=presence.last_seen_ts,
                            inside=False,
                            samples_inside=presence.samples_inside,
                            sog_min=presence.sog_min,
                            sog_max=presence.sog_max,
                            sog_avg=presence.sog_avg,
                        )
                    )
                    presence.enter_ts = None
                    presence.reset_stats()
        return result

    def _detect_gate_crossings(
        self,
        mmsi: int,
        state: VesselState,
        prev_fix: Optional[Fix],
        curr_fix: Fix,
    ) -> ProcessingResult:
        result = ProcessingResult()
        if prev_fix is None:
            return result
        prev_point = prev_fix.point_mercator
        curr_point = curr_fix.point_mercator
        segment = LineString([prev_point, curr_point])
        for gate_id, gate in self.gates.items():
            if not gate.prepared_buffer.intersects(segment):
                continue
            direction = self._resolve_direction(gate, prev_point, curr_point, curr_fix.observation)
            if direction is None:
                continue
            last_cross = state.gate_last_cross.get((gate_id, direction))
            if last_cross and curr_fix.observation.ts - last_cross < self.GATE_DEDUP:
                continue
            state.gate_last_cross[(gate_id, direction)] = curr_fix.observation.ts
            result.gate_crossings.append(
                GateCrossing(
                    mmsi=mmsi,
                    gate_id=gate_id,
                    ts=curr_fix.observation.ts,
                    direction=direction,
                    lat=curr_fix.observation.lat,
                    lon=curr_fix.observation.lon,
                    sog=curr_fix.observation.sog,
                    cog=curr_fix.observation.cog,
                )
            )
        return result

    def _resolve_direction(
        self,
        gate: GateFeature,
        prev_point: Point,
        curr_point: Point,
        obs: Observation,
    ) -> Optional[str]:
        dx = curr_point.x - prev_point.x
        dy = curr_point.y - prev_point.y
        mag = math.hypot(dx, dy)
        nx, ny = gate.normal_unit
        if mag > 0:
            dot = dx * nx + dy * ny
        elif obs.cog is not None:
            radians = math.radians(obs.cog)
            vx = math.cos(radians)
            vy = math.sin(radians)
            dot = vx * nx + vy * ny
        else:
            return None
        return "AtoB" if dot >= 0 else "BtoA"

    def _maybe_emit_tracklet(self, mmsi: int, state: VesselState) -> ProcessingResult:
        result = ProcessingResult()
        fix = state.last_fix
        if fix is None:
            return result
        buffer = state.track_buffer
        buffer.append(fix)
        min_ts = fix.observation.ts - self.TRACKLET_MAX
        while buffer and buffer[0].observation.ts < min_ts:
            buffer.popleft()
        if len(buffer) < 2:
            return result
        span = buffer[-1].observation.ts - buffer[0].observation.ts
        if span < self.TRACKLET_MIN:
            return result
        if span > self.TRACKLET_MAX:
            while buffer and (buffer[-1].observation.ts - buffer[0].observation.ts) > self.TRACKLET_MAX:
                buffer.popleft()
            if len(buffer) < 2:
                return result
        start_ts = buffer[0].observation.ts
        end_ts = buffer[-1].observation.ts
        if state.last_tracklet_end and start_ts <= state.last_tracklet_end:
            return result
        mean_sog = sum(item.observation.sog for item in buffer) / len(buffer)
        sin_sum = sum(math.sin(math.radians(item.observation.cog or 0.0)) for item in buffer)
        cos_sum = sum(math.cos(math.radians(item.observation.cog or 0.0)) for item in buffer)
        mean_cog = (math.degrees(math.atan2(sin_sum, cos_sum)) + 360.0) % 360.0
        tracklet_id = f"{mmsi}-{int(end_ts.timestamp())}"
        result.tracklets.append(
            TrackletRecord(
                tracklet_id=tracklet_id,
                mmsi=mmsi,
                start_ts=start_ts,
                end_ts=end_ts,
                n_points=len(buffer),
                mean_cog=mean_cog,
                mean_sog=mean_sog,
                poly_from_id=None,
                poly_to_id=None,
            )
        )
        state.last_tracklet_end = end_ts
        return result

    def polygon_occupancy_snapshot(self) -> Dict[str, int]:
        counts: Dict[str, int] = {polygon_id: 0 for polygon_id in self.polygons}
        for vessel_state in self.vessels.values():
            for polygon_id, presence in vessel_state.polygon_states.items():
                if presence.inside:
                    counts[polygon_id] = counts.get(polygon_id, 0) + 1
        return counts
def _distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_nm = 3440.065
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_nm * c
