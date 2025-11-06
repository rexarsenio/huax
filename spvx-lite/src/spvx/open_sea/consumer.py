"""
Asynchronous AISStream consumer for the open-sea polygon/gate engine.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

import websockets
from prometheus_client import Counter, Gauge, start_http_server

# Try to import python-socks for proxy support
try:
    from python_socks.async_.asyncio import Proxy as AsyncProxy
    PROXY_SUPPORT = True
except ImportError:
    PROXY_SUPPORT = False

from spvx.config import AppSettings
from spvx.ingest.canonicalize import canonicalize
from spvx.open_sea.config import OpenSeaConfig
from spvx.open_sea.db import DuckDBWriter
from spvx.open_sea.engine import Observation, OpenSeaEngine, ProcessingResult
from spvx.open_sea.geo import GateFeature, GeoJSONLoadError, PolygonFeature, load_gates, load_polygons

LOG = logging.getLogger(__name__)

WS_URL = "wss://stream.aisstream.io/v0/stream"
METRICS_STARTED = False


def _get_proxy_url() -> Optional[str]:
    """Extract proxy URL from environment variables."""
    proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    if proxy:
        # Check if aisstream.io is in NO_PROXY
        no_proxy = os.getenv("NO_PROXY") or os.getenv("no_proxy") or ""
        no_proxy_list = [h.strip() for h in no_proxy.split(",")]
        if any(host in "aisstream.io" for host in no_proxy_list):
            LOG.info("aisstream.io is in NO_PROXY list, skipping proxy.")
            return None
        LOG.info("Using HTTP proxy for WebSocket connection: %s", proxy.split("@")[0] if "@" in proxy else proxy[:50])
    return proxy


async def _connect_websocket_via_proxy(url: str, proxy_url: str, ping_interval: int, ping_timeout: int):
    """Connect to WebSocket through HTTP CONNECT proxy using python-socks."""
    if not PROXY_SUPPORT:
        raise RuntimeError("python-socks not installed - cannot use proxy")

    parsed = urlparse(proxy_url)
    parsed_ws = urlparse(url)

    # Create proxy object
    proxy = AsyncProxy.from_url(proxy_url)

    # Connect through proxy to target host
    sock = await proxy.connect(
        dest_host=parsed_ws.hostname,
        dest_port=parsed_ws.port or (443 if parsed_ws.scheme == "wss" else 80)
    )

    # Now create WebSocket connection using this socket
    return await websockets.connect(
        url,
        ping_interval=ping_interval,
        ping_timeout=ping_timeout,
        sock=sock
    )

CONSUMER_UP = Gauge("open_sea_consumer_running", "Open-sea AIS consumer liveness indicator.")
INGEST_FIXES = Counter(
    "open_sea_fixes_total", "Count of canonical AIS fixes processed by the open-sea consumer.", ["source"]
)
INGEST_LAG_SECONDS = Gauge(
    "open_sea_ingest_lag_seconds", "Seconds between now and the latest AIS fix timestamp processed."
)
OCCUPANCY_NOW = Gauge(
    "open_sea_tanker_occupancy_now", "Current tanker count within polygon after hysteresis.", ["polygon"]
)
GATE_CROSSINGS_TOTAL = Counter(
    "open_sea_gate_crossings_total", "Total gate crossings detected by the open-sea consumer.", ["gate", "direction"]
)
DATA_GAP_RATIO = Gauge(
    "open_sea_data_gap_ratio", "Share of expected 60s buckets without any AIS fix in the recent window."
)
SPOOF_SCORE = Gauge(
    "open_sea_spoof_score", "Share of teleport-speed fixes (>40 kn) observed in the recent window."
)
SPOOF_EVENTS_TOTAL = Counter(
    "open_sea_spoof_events_total", "Count of teleport-speed (>40 kn) events detected.", ["reason"]
)


@dataclass
class ConsumerSettings:
    api_key: str
    duckdb_path: Path
    ttl_interval_secs: int = 60
    metrics_host: str = "0.0.0.0"
    metrics_port: Optional[int] = 9110


class OpenSeaConsumer:
    def __init__(
        self,
        config: OpenSeaConfig,
        polygons: Iterable[PolygonFeature],
        gates: Iterable[GateFeature],
        settings: ConsumerSettings,
    ):
        self.config = config
        self.engine = OpenSeaEngine(config, polygons, gates)
        self.settings = settings
        self.writer = DuckDBWriter(settings.duckdb_path)
        self.stop_event = asyncio.Event()
        self.ttl_task: Optional[asyncio.Task] = None
        self.bounding_boxes = _compute_bounding_boxes(polygons, gates)
        self.latest_obs_ts: Optional[datetime] = None
        self._fix_times: deque[datetime] = deque()
        self._teleport_times: deque[datetime] = deque()
        self._ensure_metrics_server()

    def _ensure_metrics_server(self) -> None:
        global METRICS_STARTED
        port = self.settings.metrics_port
        if port is None or port <= 0:
            LOG.info("Metrics server disabled (metrics_port=%s).", port)
            return
        if not METRICS_STARTED:
            start_http_server(self.settings.metrics_port, addr=self.settings.metrics_host)
            METRICS_STARTED = True
        CONSUMER_UP.set(1)

    async def run(self) -> None:
        if not self.settings.api_key:
            raise RuntimeError("AISSTREAM_API_KEY not provided.")
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, self.stop_event.set)

        self.ttl_task = asyncio.create_task(self._ttl_loop())

        subscription = {
            "APIKey": self.settings.api_key,
            "BoundingBoxes": self.bounding_boxes,
            "FiltersShipType": list(range(80, 90)),
            "FilterMessageTypes": ["PositionReport"],
        }

        retry_delay = 5
        max_retry = 60

        try:
            while not self.stop_event.is_set():
                try:
                    # Setup proxy if needed
                    proxy_url = _get_proxy_url()

                    if proxy_url and PROXY_SUPPORT:
                        # Connect via proxy
                        ws = await _connect_websocket_via_proxy(WS_URL, proxy_url, 20, 20)
                    else:
                        # Direct connection
                        if proxy_url and not PROXY_SUPPORT:
                            LOG.warning("Proxy configured but python-socks not available - attempting direct connection")
                        ws = await websockets.connect(WS_URL, ping_interval=20, ping_timeout=20)

                    async with ws:
                        LOG.info("Open-sea consumer connected to AISStream.")
                        await ws.send(json.dumps(subscription))
                        async for raw in ws:
                            if self.stop_event.is_set():
                                break
                            await self._handle_message(raw)
                        retry_delay = 5
                except (
                    websockets.exceptions.ConnectionClosedOK,
                    websockets.exceptions.ConnectionClosedError,
                    asyncio.TimeoutError,
                ) as exc:
                    if self.stop_event.is_set():
                        break
                    LOG.warning("Open-sea stream closed: %s. Retry in %s seconds.", exc, retry_delay)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry)
                except Exception as exc:  # pragma: no cover - defensive logging
                    if self.stop_event.is_set():
                        break
                    LOG.exception("Open-sea consumer failure: %s. Retry in %s seconds.", exc, retry_delay)
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, max_retry)
        finally:
            self.stop_event.set()
            CONSUMER_UP.set(0)
            if self.ttl_task:
                self.ttl_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self.ttl_task
            self.writer.close()

    async def _handle_message(self, raw: str) -> None:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            LOG.debug("Malformed payload skipped.")
            return

        canonical = canonicalize(payload, self.writer.con)
        if not canonical:
            return
        if not canonical.get("is_tanker"):
            # AISStream subscription already filters for tanker shiptype codes.
            # Treat unknown shiptypes as tankers to avoid dropping valid events.
            canonical["is_tanker"] = True

        mmsi = int(canonical["mmsi"])
        obs = Observation(
            ts=canonical["msg_time"],
            lat=canonical["lat"],
            lon=canonical["lon"],
            sog=canonical["sog"],
            cog=canonical.get("cog"),
            shiptype_num=canonical.get("shiptype_num"),
            is_tanker=canonical.get("is_tanker", False),
        )
        INGEST_FIXES.labels(source="aisstream").inc()
        self.latest_obs_ts = obs.ts
        age = (datetime.now(timezone.utc) - obs.ts).total_seconds()
        if age < 0:
            age = 0.0
        INGEST_LAG_SECONDS.set(age)
        result = self.engine.process_observation(mmsi, obs)
        if result.empty():
            self._update_health_metrics(obs.ts, teleport_events=0)
            return
        await asyncio.to_thread(self.writer.apply, result)
        self._update_health_metrics(obs.ts, teleport_events=len(result.teleport_events))
        self._record_metrics(result)

    async def _ttl_loop(self) -> None:
        try:
            while not self.stop_event.is_set():
                await asyncio.sleep(self.settings.ttl_interval_secs)
                now = datetime.now(timezone.utc)
                result = self.engine.expire_stale(now)
                if result.empty():
                    self._update_health_metrics(None, teleport_events=0)
                    continue
                await asyncio.to_thread(self.writer.apply, result)
                self._record_metrics(result)
                self._update_health_metrics(None, teleport_events=0)
        except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
            raise

    def _record_metrics(self, result: ProcessingResult) -> None:
        if result.gate_crossings:
            for crossing in result.gate_crossings:
                GATE_CROSSINGS_TOTAL.labels(gate=crossing.gate_id, direction=crossing.direction).inc()
        counts = self.engine.polygon_occupancy_snapshot()
        for polygon_id, count in counts.items():
            OCCUPANCY_NOW.labels(polygon=polygon_id).set(count)
        if result.teleport_events:
            for _ in result.teleport_events:
                SPOOF_EVENTS_TOTAL.labels(reason="speed_over_40_kn").inc()

    def _update_health_metrics(self, obs_ts: Optional[datetime], teleport_events: int) -> None:
        window = timedelta(minutes=10)
        now = datetime.now(timezone.utc)
        cutoff = now - window

        if obs_ts is not None:
            if obs_ts.tzinfo is None:
                obs_ts = obs_ts.replace(tzinfo=timezone.utc)
            self._fix_times.append(obs_ts)
            for _ in range(teleport_events):
                self._teleport_times.append(obs_ts)
        # prune
        while self._fix_times and self._fix_times[0] < cutoff:
            self._fix_times.popleft()
        while self._teleport_times and self._teleport_times[0] < cutoff:
            self._teleport_times.popleft()

        window_seconds = window.total_seconds()
        bucket_size = max(1, self.config.downsample_secs)
        expected_buckets = max(1, int(window_seconds // bucket_size))
        bucket_ids = {int(ts.timestamp() // bucket_size) for ts in self._fix_times}
        gap_ratio = 1.0 - min(len(bucket_ids), expected_buckets) / expected_buckets
        DATA_GAP_RATIO.set(max(0.0, min(1.0, gap_ratio)))

        spoof_score = 0.0
        if self._fix_times:
            spoof_score = len(self._teleport_times) / len(self._fix_times)
        SPOOF_SCORE.set(min(1.0, max(0.0, spoof_score)))


def load_geometries(polygons_path: Path, gates_path: Path) -> tuple[list[PolygonFeature], list[GateFeature]]:
    try:
        polygons = load_polygons(polygons_path)
        gates = load_gates(gates_path)
        return polygons, gates
    except GeoJSONLoadError as exc:
        raise RuntimeError(f"Failed to load geometry artefacts: {exc}") from exc


def _compute_bounding_boxes(
    polygons: Iterable[PolygonFeature], gates: Iterable[GateFeature]
) -> list[list[list[float]]]:
    seen: set[tuple[float, float, float, float]] = set()
    boxes: list[list[list[float]]] = []
    for bbox in [p.bbox_lonlat for p in polygons] + [g.bbox_lonlat for g in gates]:
        lon_min, lat_min, lon_max, lat_max = bbox
        key = (round(lon_min, 3), round(lat_min, 3), round(lon_max, 3), round(lat_max, 3))
        if key in seen:
            continue
        seen.add(key)
        boxes.append([[lat_min, lon_min], [lat_max, lon_max]])
    return boxes


def run_open_sea_consumer(
    config: OpenSeaConfig,
    polygons_path: Path,
    gates_path: Path,
    api_key: str | None = None,
    duckdb_path: Path | str | None = None,
    metrics_host: str | None = None,
    metrics_port: int | None = None,
) -> None:
    """Entrypoint used by the Typer CLI."""
    polygons, gates = load_geometries(polygons_path, gates_path)
    target_duckdb = Path(duckdb_path) if duckdb_path else Path(AppSettings().duckdb_path)
    settings = ConsumerSettings(
        api_key=api_key or os.getenv("AISSTREAM_API_KEY", ""),
        duckdb_path=target_duckdb,
        metrics_host=metrics_host or os.getenv("OPEN_SEA_METRICS_HOST", "0.0.0.0"),
        metrics_port=_resolve_metrics_port(metrics_port),
    )
    consumer = OpenSeaConsumer(config, polygons, gates, settings)
    asyncio.run(consumer.run())


import signal  # noqa: E402  # circular guard for signal usage above


def _resolve_metrics_port(explicit: int | None) -> Optional[int]:
    if explicit is not None:
        return int(explicit)
    raw = os.getenv("OPEN_SEA_METRICS_PORT", "").strip().lower()
    if not raw:
        return 9110
    if raw in {"0", "off", "disable", "disabled", "none"}:
        return 0
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid OPEN_SEA_METRICS_PORT value: {raw}") from exc
