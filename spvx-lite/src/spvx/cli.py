"""
Typer CLI entrypoint for SPVX-Lite pipeline.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import typer
from rich import print as rprint

from spvx.config import AppSettings, load_config
from spvx.geo.derive_anchorage import DeriveParams, build_anchorage
from spvx.db import ensure_core_tables
from spvx.etl import build_components_daily, compute_basin_indices
from spvx.features.baseline_tables import refresh_doy_baselines
from spvx.features.components import build_components
from spvx.index.spvx_lite import compute_spvx_lite
from spvx.models.spread_direction import ScoreResult, score_spread, train_spread
from spvx.models.throughput_72h import score_throughput, train_throughput
from spvx.open_market.ingest import ensure_tables as ensure_market_tables, ingest_oil
from spvx.open_sea.aggregate import compute_aggregates
from spvx.open_sea.config import get_open_sea_config
from spvx.open_sea.consumer import run_open_sea_consumer
from spvx.open_sea.detect import detect_floating_storage, detect_route_deviation, detect_transit_anomalies
from spvx.open_sea.sis import SISConfig, compute_sis_daily
from spvx.sources import mock, mpa_sg, rotterdam, turkish_straits
from spvx.sources.portstays import run as run_portstays
from spvx.utils.publish import atomic_write_json
from spvx.utils.runtime import log_step, make_run_meta, update_run_meta
from spvx.validation.signals import validate_signals
from spvx.weather import run_openweather, run_sea_state

app = typer.Typer(help="SPVX-Lite chokepoint analytics pipeline")


@app.callback()
def main(ctx: typer.Context):
    ctx.obj = AppSettings()


@app.command("ingest")
def ingest(mode: str = typer.Option("mock", help="mock | live")):
    """
    Ingest data into DuckDB.
    """
    with log_step("Ingestion"):
        if mode == "mock":
            mock.run()
            rprint("[green]Mock data generated in DuckDB and CSV fixtures.[/green]")
        elif mode == "live":
            rprint("[yellow]Attempting live ingestion...[/yellow]")
            try:
                turkish_straits.run()
            except NotImplementedError as exc:
                rprint(f"[yellow]Turkish straits ingestion skipped: {exc}[/yellow]")
            try:
                mpa_sg.run()
            except NotImplementedError as exc:
                rprint(f"[yellow]MPA Singapore ingestion skipped: {exc}[/yellow]")
            except RuntimeError as exc:
                rprint(f"[yellow]MPA Singapore ingestion failed: {exc}[/yellow]")
            try:
                rotterdam.run()
            except NotImplementedError as exc:
                rprint(f"[yellow]Rotterdam ingestion skipped: {exc}[/yellow]")
            except RuntimeError as exc:
                rprint(f"[yellow]Rotterdam ingestion failed: {exc}[/yellow]")
            try:
                rows = run_portstays()
            except Exception as exc:  # pragma: no cover - live dependency
                rprint(f"[yellow]PortStays ingestion failed: {exc}[/yellow]")
            else:
                if rows is None:
                    rprint("[yellow]PortStays credentials missing; skipped.[/yellow]")
                else:
                    rprint(f"[green]PortStays snapshot stored ({rows} tanker-day rows).[/green]")
        else:
            raise typer.BadParameter("mode must be 'mock' or 'live'")


@app.command("compute-index")
def compute_index(
    with_sea_state: bool = typer.Option(True, help="Include sea-state features when building components.")
):
    """
    Compute basin indices with optional sea-state enrichment.
    """
    with log_step("Building component features"):
        build_components(include_sea_state=with_sea_state)
    with log_step("Computing SPVX-Lite index"):
        output = compute_spvx_lite()
    rprint(f"[green]SPVX-Lite index written to {output}[/green]")


@app.command("train")
def train_models():
    with log_step("Training spread-direction model"):
        spread_metrics = train_spread()
    rprint(
        "[bold]Spread model metrics (TS-CV):[/bold] "
        f"AUC={spread_metrics.auc:.3f}±{spread_metrics.auc_std:.3f}, "
        f"PR-AUC={spread_metrics.pr_auc:.3f}±{spread_metrics.pr_auc_std:.3f}, "
        f"Brier={spread_metrics.brier:.3f}±{spread_metrics.brier_std:.3f}, "
        f"SignFlipAUC={spread_metrics.sign_flip_auc:.3f}"
    )

    with log_step("Training throughput model"):
        throughput_metrics = train_throughput()
    aucs = ", ".join(f"{h * 24}h={throughput_metrics.auc_by_horizon[h]:.3f}" for h in throughput_metrics.auc_by_horizon)
    rprint(
        "[bold]Throughput model metrics:[/bold] "
        f"{aucs} | MAE improvement vs persistence: {throughput_metrics.mae_improvement:.2f}"
    )


@app.command("score")
def score_models(
    simulate_degradation: bool = typer.Option(False, help="Simulate a degraded run (missed fix scenario).")
):
    with log_step("Scoring spread-direction model"):
        spread_result: ScoreResult = score_spread()
    with log_step("Scoring throughput model"):
        throughput_path = score_throughput()

    spread_report = spread_result.report.copy()
    if simulate_degradation:
        spread_report["degraded"] = True
        spread_report["mode"] = "fallback"
        reasons = set(spread_report.get("reasons", []) or [])
        reasons.add("simulated_missed_fix")
        spread_report["reasons"] = sorted(reasons)

    _write_signal_snapshot(spread_report=spread_report)
    meta = make_run_meta(
        extra={
            "spread_scores": str(spread_result.scores_path),
            "spread_report": str(spread_result.report_path),
            "throughput_scores": str(throughput_path),
            "degraded": bool(spread_report.get("degraded", False)),
        }
    )
    update_run_meta("score_models", meta)
    rprint("[green]Scores written to " f"{spread_result.scores_path} and {throughput_path}[/green]")


@app.command("serve")
def serve_api(host: str = "0.0.0.0", port: int = 8080):
    """
    Launch FastAPI app with Uvicorn.
    """
    import uvicorn

    uvicorn.run("spvx.api_app:app", host=host, port=port, reload=False)


@app.command("build-basins")
def build_basins():
    """
    Generate basin/component tables and aggregate basin/global indices.
    """
    settings = AppSettings()
    path = Path(settings.duckdb_path)
    if not path.exists():
        raise typer.BadParameter(f"DuckDB not found at {path}. Run ingest first.")
    con = duckdb.connect(str(path))
    try:
        with log_step("Building basin components"):
            component_rows = build_components_daily(con)
        with log_step("Computing basin/global indices"):
            basin_rows, global_rows = compute_basin_indices(con)
    finally:
        con.close()
    rprint(
        "[green]Basin pipeline completed:[/green] "
        f"{component_rows} component rows, {basin_rows} basin rows, {global_rows} global rows updated."
    )


def _parse_since(token: str) -> int:
    token = token.strip().lower()
    if token.endswith("d"):
        token = token[:-1]
    days = int(token)
    if days <= 0:
        raise typer.BadParameter("since must be > 0")
    return days


@app.command("ingest-market")
def ingest_market(
    since: str = typer.Option("365d", help="Lookback window (e.g. 365d)."),
    mode: str = typer.Option("live", help="live | mock"),
):
    """
    Ingest market context series (Brent/WTI) from EIA/FRED or mock generator.
    """
    days = _parse_since(since)
    use_mock = mode.lower() == "mock"

    settings = AppSettings()
    con = duckdb.connect(settings.duckdb_path)
    try:
        ensure_market_tables(con)
        count = ingest_oil(con, since_days=days, use_mock=use_mock)
    finally:
        con.close()

    source_label = "mock" if use_mock else "live"
    rprint(f"[green][market][/green] oil_daily upserts: {count} ({source_label})")


@app.command("ingest-portstays")
def ingest_portstays(
    iso_datetime: str = typer.Option(
        None,
        help="ISO-8601 timestamp (UTC) for the snapshot. Defaults to current UTC if omitted.",
    )
):
    """
    Fetch a single PortStays snapshot and persist tanker departures/arrivals.
    """
    with log_step("PortStays snapshot"):
        rows = run_portstays(iso_datetime)
    if rows is None:
        rprint("[yellow]PortStays credentials not configured; nothing to do.[/yellow]")
    else:
        rprint(f"[green]Stored PortStays snapshot with {rows} aggregated rows.[/green]")


@app.command("open-sea-consume")
def open_sea_consume(
    polygons: Path = typer.Option(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        writable=False,
        readable=True,
        help="Path to polygons GeoJSON file.",
    ),
    gates: Path = typer.Option(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        writable=False,
        readable=True,
        help="Path to gates GeoJSON file.",
    ),
    config_path: Path = typer.Option(Path("config.yml"), help="Config file containing 'open_sea' section."),
    api_key: str = typer.Option("", help="AISStream API key (falls back to env AISSTREAM_API_KEY)."),
    duckdb_path: Path | None = typer.Option(
        None,
        exists=False,
        file_okay=True,
        dir_okay=False,
        writable=True,
        readable=False,
        resolve_path=True,
        help="DuckDB database path for consumer writes (defaults to AppSettings).",
    ),
    metrics_host: str | None = typer.Option(
        None,
        help="Host/IP for Prometheus metrics server (defaults to env OPEN_SEA_METRICS_HOST or 0.0.0.0).",
    ),
    metrics_port: int | None = typer.Option(
        None,
        help="Port for Prometheus metrics server (defaults to env OPEN_SEA_METRICS_PORT or 9110).",
    ),
):
    """Run the AISStream consumer for open-sea polygons/gates."""

    with log_step("Loading open-sea configuration"):
        cfg = get_open_sea_config(str(config_path))
    run_open_sea_consumer(
        cfg,
        polygons.resolve(),
        gates.resolve(),
        api_key or None,
        duckdb_path=duckdb_path.resolve() if duckdb_path else None,
        metrics_host=metrics_host,
        metrics_port=metrics_port,
    )


@app.command("open-sea-aggregate")
def open_sea_aggregate(
    config_path: Path = typer.Option(Path("config.yml"), help="Config file containing 'open_sea' section."),
    duckdb_path: Path | None = typer.Option(None, help="DuckDB database path (defaults to AppSettings)."),
):
    """Compute open-sea aggregation tables (occupancy, gate flux, transit)."""

    with log_step("Loading open-sea configuration"):
        cfg = get_open_sea_config(str(config_path))
    settings = AppSettings()
    target_path = duckdb_path or Path(settings.duckdb_path)
    compute_aggregates(cfg, target_path)
    rprint("[green]Open-sea aggregates refreshed.[/green]")


@app.command("ingest-weather")
def ingest_weather(regions: str = typer.Option("", help="Comma-separated list of chokepoint regions to sample.")):
    """
    Fetch OpenWeather observations and record weather flags.
    """
    region_list = [region.strip() for region in regions.split(",") if region.strip()] if regions else None
    with log_step("OpenWeather snapshot"):
        upserted = run_openweather(region_list)
    if upserted == 0:
        rprint("[yellow]No weather observations ingested (missing key or all requests failed).[/yellow]")
    else:
        rprint(f"[green]Stored {upserted} weather observations from OpenWeather.[/green]")


@app.command("ingest-sea-state")
def ingest_sea_state(
    provider: str = typer.Option(
        "auto", help="auto | rtofs | cmems. 'auto' uses fallback chain: CMEMS → RTOFS → degraded"
    ),
    regions: str = typer.Option("", help="Comma-separated list of chokepoint regions to sample."),
    lookback_days: int = typer.Option(3, help="Number of days to fetch (CMEMS only)."),
):
    """
    Fetch sea-state observations with automatic fallback.
    Use provider='auto' (default) for automatic fallback: CMEMS → RTOFS → graceful degradation.
    Use provider='rtofs' for NOAA RTOFS/WW3 only.
    Use provider='cmems' for Copernicus Marine Service only.
    """
    region_list = [region.strip() for region in regions.split(",") if region.strip()] if regions else None

    if provider == "auto":
        # Use fallback chain
        from spvx.sea_state.fallback import SeaStateFallbackChain

        username = os.getenv("CMEMS_USERNAME")
        password = os.getenv("CMEMS_PASSWORD")
        cfg = load_config()

        chain = SeaStateFallbackChain(
            cmems_username=username,
            cmems_password=password,
            config=cfg,
        )

        with log_step("Sea-state ingestion with fallback"):
            result = chain.ingest_with_fallback(lookback_days, region_list)

        if result.status.value == "success":
            rprint(
                f"[green]Sea-state ingestion successful using {result.provider.upper()}:[/green] "
                f"{result.files_downloaded} files, {result.rows_processed} rows processed."
            )
        elif result.status.value == "degraded":
            rprint(
                f"[yellow]Weather degradation activated:[/yellow] {result.error}\n"
                f"[yellow]Index will use SPVX_LITE_EX_WEATHER variant (weather components disabled).[/yellow]"
            )
        else:
            rprint(f"[red]Sea-state ingestion failed: {result.error}[/red]")

    elif provider == "rtofs":
        with log_step("Sea-state snapshot (RTOFS/WW3)"):
            currents, waves = run_sea_state(region_list)
        if currents == 0 and waves == 0:
            rprint("[yellow]No sea-state observations ingested (all requests failed).[/yellow]")
        else:
            rprint(f"[green]Stored {currents} current samples and {waves} wave samples from RTOFS/WW3.[/green]")
    elif provider == "cmems":
        from spvx.sea_state.cmems import (
            DEFAULT_FEATURES,
            _list_days_yyyymmdd,
            download_currents,
            download_waves,
            extract_region_features,
        )

        cfg = load_config()
        sea_cfg = cfg.get("sea_state", {})
        cps_cfg = cfg.get("chokepoints", {})

        waves_dataset_id = sea_cfg.get("waves_dataset_id")
        currents_dataset_id = sea_cfg.get("currents_dataset_id")
        out_dir = sea_cfg.get("out_dir", "data/sea_state")
        buffer_km = float(sea_cfg.get("buffer_km", 0))
        features_cfg = sea_cfg.get("features") or DEFAULT_FEATURES

        if not waves_dataset_id or not currents_dataset_id:
            raise typer.BadParameter("sea_state.waves_dataset_id and currents_dataset_id must be set in config.yml")

        # Get CMEMS credentials from environment
        username = os.getenv("CMEMS_USERNAME")
        password = os.getenv("CMEMS_PASSWORD")

        days = _list_days_yyyymmdd(lookback_days)

        with log_step("Downloading CMEMS waves"):
            wav_files = download_waves(
                waves_dataset_id,
                f"{out_dir}/waves",
                days,
                username=username,
                password=password,
            )
            rprint(f"[green]Downloaded {len(wav_files)} wave files.[/green]")

            # Update metrics
            try:
                from spvx.metrics import spvx_sea_state_files_downloaded_total, spvx_sea_state_provider

                spvx_sea_state_files_downloaded_total.labels(provider="cmems", data_type="waves").inc(len(wav_files))
                if wav_files:
                    spvx_sea_state_provider.labels(source="cmems").set(1)
            except Exception:
                pass  # Metrics optional

        # Free up disk space by removing wave netCDF files after download
        # The wave data will be redownloaded if needed (caching logic handles this)
        import shutil
        if os.path.exists(f"{out_dir}/waves"):
            try:
                shutil.rmtree(f"{out_dir}/waves")
                os.makedirs(f"{out_dir}/waves", exist_ok=True)
                rprint("[yellow]Cleaned up wave files to free disk space for currents.[/yellow]")
            except Exception as exc:
                rprint(f"[yellow]Warning: Could not clean up waves directory: {exc}[/yellow]")

        with log_step("Downloading CMEMS currents"):
            cur_files = download_currents(
                currents_dataset_id,
                f"{out_dir}/currents",
                days,
                username=username,
                password=password,
            )
            rprint(f"[green]Downloaded {len(cur_files)} current files.[/green]")

            # Update metrics
            try:
                from spvx.metrics import spvx_sea_state_files_downloaded_total

                spvx_sea_state_files_downloaded_total.labels(provider="cmems", data_type="currents").inc(len(cur_files))
            except Exception:
                pass  # Metrics optional

        # Process per chokepoint
        chokepoint_ids = list(cps_cfg.keys()) if not region_list else region_list
        for cid in chokepoint_ids:
            if cid not in cps_cfg:
                rprint(f"[yellow]Chokepoint {cid} not found in config.yml, skipping.[/yellow]")
                continue

            meta = cps_cfg[cid]
            with log_step(f"Processing {cid}"):
                df = extract_region_features(
                    waves_files=wav_files,
                    currents_files=cur_files,
                    features_cfg=features_cfg,
                    bbox=meta["bbox"],
                    bearing_deg=float(meta.get("bearing_deg", 0.0)),
                    buffer_km=buffer_km,
                ).sort_values("time")
                outp = Path(f"data/processed/sea_state_{cid}.parquet")
                outp.parent.mkdir(parents=True, exist_ok=True)
                df.to_parquet(outp, index=False)
                rprint(f"[green]Saved {len(df)} rows to {outp}[/green]")

                # Update metrics
                try:
                    import datetime as dt

                    from spvx.metrics import spvx_sea_state_freshness_seconds, spvx_sea_state_records_total

                    spvx_sea_state_records_total.labels(chokepoint=cid).set(len(df))
                    if not df.empty and "time" in df.columns:
                        latest_time = pd.to_datetime(df["time"].max(), utc=True)
                        freshness = (dt.datetime.now(dt.timezone.utc) - latest_time).total_seconds()
                        spvx_sea_state_freshness_seconds.labels(chokepoint=cid).set(freshness)
                except Exception:
                    pass  # Metrics optional

        rprint("[green]CMEMS sea-state ingest completed.[/green]")
    else:
        raise typer.BadParameter("provider must be 'auto', 'rtofs', or 'cmems'")


@app.command("sea-state-join")
def sea_state_join(
    duckdb_path: Path | None = typer.Option(None, help="DuckDB database path (defaults to AppSettings)."),
):
    """
    Compute SIS (Sea Impact Score) daily aggregates from joined sea-state samples.
    """
    settings = AppSettings()
    target_path = duckdb_path or Path(settings.duckdb_path)
    if not target_path.exists():
        raise typer.BadParameter(f"DuckDB not found at {target_path}. Run ingestion jobs first.")

    with log_step("SIS daily aggregation"):
        con = duckdb.connect(str(target_path))
        try:
            inserted = compute_sis_daily(con, SISConfig())
        finally:
            con.close()
    if inserted:
        rprint(f"[green]SIS daily refreshed for {inserted} corridor-day rows.[/green]")
    else:
        rprint("[yellow]No SIS samples available for aggregation.[/yellow]")


@app.command("open-sea-detect")
def open_sea_detect(
    corridor: str = typer.Option(
        "AG->HORMUZ",
        help="Corridor identifier in the form FROM->TO for transit anomaly detection.",
    ),
    cape_gate: str = typer.Option("CAPE_GOOD_HOPE", help="Gate identifier for Cape route flux monitoring."),
    suez_gate: str = typer.Option("SUEZ", help="Gate identifier for Suez route flux monitoring."),
    floating_polygon: str = typer.Option("FUJAIRAH_ANCH_v1", help="Polygon id to monitor for floating storage."),
    duckdb_path: Path | None = typer.Option(None, help="DuckDB database path (defaults to AppSettings)."),
):
    """
    Run the open-sea detection suite (transit anomalies, route deviations, floating storage).
    """
    settings = AppSettings()
    target_path = duckdb_path or Path(settings.duckdb_path)
    if not target_path.exists():
        raise typer.BadParameter(f"DuckDB not found at {target_path}. Run ingestion jobs first.")

    with log_step("Open-sea detection"):
        con = duckdb.connect(str(target_path))
        try:
            transit_alerts = detect_transit_anomalies(con, corridor=corridor)
            route_alerts = detect_route_deviation(con, cape_gate=cape_gate, suez_gate=suez_gate)
            storage_alerts = detect_floating_storage(con, polygon_id=floating_polygon)
        finally:
            con.close()

    total = transit_alerts + route_alerts + storage_alerts
    if total:
        rprint(
            "[green]Open-sea detection complete:[/green] "
            f"transit={transit_alerts}, route={route_alerts}, floating_storage={storage_alerts} (total={total})."
        )
    else:
        rprint("[yellow]No open-sea detections triggered in the recent window.[/yellow]")


@app.command("refresh-baselines")
def refresh_baselines(
    lookback_days: int = typer.Option(400, help="Number of trailing days to use for baselines."),
    min_history_days: int = typer.Option(180, help="Warn if history span is below this threshold."),
):
    """
    Recompute seasonal day-of-year baselines in DuckDB.
    """
    settings = AppSettings()
    path = Path(settings.duckdb_path)
    if not path.exists():
        raise typer.BadParameter(f"DuckDB not found at {path}. Run ingest first.")
    con = duckdb.connect(str(path))
    try:
        ensure_core_tables(con)
        rows = refresh_doy_baselines(
            con,
            lookback_days=lookback_days,
            min_history_days=min_history_days,
        )
    finally:
        con.close()
    rprint(f"[green]Baseline table updated with {rows} rows.[/green]")


def _write_signal_snapshot(
    path: Path = Path("data/outputs/signals.json"),
    *,
    spread_report: dict[str, object] | None = None,
) -> None:
    """
    Emit a compact JSON artifact with the latest signals for frontends/newsletters.
    """
    payload: dict[str, object] = {"asof": pd.Timestamp.utcnow().isoformat()}

    index_path = Path("data/outputs/spvx_lite.csv")
    if index_path.exists():
        idx_df = pd.read_csv(index_path, parse_dates=["date"]).sort_values("date")
        if not idx_df.empty:
            latest_idx = idx_df.iloc[-1]
            payload["spvx_lite"] = float(latest_idx["SPVX_LITE"])
            if len(idx_df) > 1:
                delta = float(latest_idx["SPVX_LITE"] - idx_df.iloc[-2]["SPVX_LITE"])
            else:
                delta = 0.0
            payload["spvx_lite_chg"] = delta

    comps_path = Path("data/processed/components.parquet")
    if comps_path.exists():
        comps_df = pd.read_parquet(comps_path).sort_values("date")
        if not comps_df.empty:
            latest_comps = comps_df.iloc[-1]
            payload["drivers"] = {
                "CQ_TR": float(latest_comps.get("CQ_TR", 0.0)),
                "CQ_SG": float(latest_comps.get("CQ_SG", 0.0)),
                "PORT_EU": float(latest_comps.get("PORT_EU", 0.0)),
            }

    if spread_report:
        spread_payload = {
            "model_ver": spread_report.get("model_version"),
            "metrics": spread_report.get("metrics"),
            "drift": spread_report.get("drift"),
            "degraded": bool(spread_report.get("degraded", False)),
            "mode": spread_report.get("mode"),
            "prob_up": spread_report.get("prob_up"),
            "prob_up_raw": spread_report.get("prob_up_raw"),
            "prob_up_calibrated": spread_report.get("prob_up_calibrated"),
            "drivers": spread_report.get("drivers"),
            "reasons": spread_report.get("reasons", []),
            "top_decile_threshold": spread_report.get("top_decile_threshold"),
            "recent_window_days": spread_report.get("recent_window_days"),
            "calibration_curve": spread_report.get("calibration_curve"),
        }
        payload["spread"] = spread_payload

        # Backwards compatibility: keep spread_direction when not degraded
        if not spread_payload["degraded"]:
            prob_up = spread_payload.get("prob_up")
            threshold = spread_payload.get("top_decile_threshold")
            if prob_up is not None:
                cfg = load_config()
                top_frac = cfg["train"].get("precision_top_frac", 0.1)
                if threshold is None or (isinstance(threshold, float) and math.isnan(threshold)):
                    scores_path = Path("data/outputs/spread_scores.parquet")
                    if scores_path.exists():
                        spread_df = pd.read_parquet(scores_path).sort_values("date")
                        if not spread_df.empty:
                            if len(spread_df) > 1:
                                threshold = float(np.quantile(spread_df["prob_up"], 1 - top_frac))
                            else:
                                threshold = float(spread_df["prob_up"].iloc[-1])
                is_threshold_number = isinstance(threshold, (float, int)) and not math.isnan(float(threshold))
                top_decile = bool(is_threshold_number and prob_up >= float(threshold))
                payload["spread_direction"] = {
                    "t+1_prob_up": float(prob_up),
                    "top_decile": top_decile,
                }
            else:
                payload["spread_direction"] = None
        else:
            payload["spread_direction"] = None
        payload["degraded"] = bool(spread_payload["degraded"])
        reasons = spread_payload.get("reasons") or []
        if reasons:
            payload.setdefault("annotations", [])
            payload["annotations"] = sorted(set(map(str, payload["annotations"])) | {str(reason) for reason in reasons})
    else:
        payload["spread_direction"] = None

    throughput_path = Path("data/outputs/throughput_scores.parquet")
    if throughput_path.exists():
        throughput_df = pd.read_parquet(throughput_path).sort_values("date")
        if not throughput_df.empty:
            latest = throughput_df.iloc[-1]
            abs_err = np.abs(throughput_df["throughput_pred_72h"] - throughput_df["throughput_actual_72h"]).dropna()
            payload["throughput_72h"] = {
                "mae_units": float(abs_err.mean()) if not abs_err.empty else None,
                "nowcast": {str(pd.to_datetime(latest["date"]).date()): float(latest["throughput_pred_72h"])},
            }

    validate_signals(payload)

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(payload, path)


@app.command("open-sea-build-suez")
def open_sea_build_suez(
    outdir: str = typer.Option("data/geo", help="Zielverzeichnis für GeoJSON"),
    distances: str = typer.Option("10,25,50,100,150", help="Distanzen in nm, CSV"),
    half_width_nm: float | None = typer.Option(None, help="Globale halbe Gate-Breite in nm (überschrieben von width-map)"),
    width_map: str = typer.Option("", help="CSV Mapping 'dist:halfwidth', z.B. '10:1.0,25:1.5,50:2.0,100:2.5,150:3.0'"),
    auto_width_from_tss: bool = typer.Option(False, help="Breite aus TSS ableiten (wenn vorhanden)"),
    use_overpass: bool = typer.Option(True, help="OSM/Seamark via Overpass einbeziehen"),
    north_entry: str = typer.Option("32.301,31.265", help="lon,lat Port Said entry"),
    south_entry: str = typer.Option("32.566,29.966", help="lon,lat Port of Suez entry"),
):
    """
    Build Suez Canal approach gates with orthogonal transects and anchorage polygons.
    """
    from spvx.open_sea.tools.suez_builder import build_suez

    dists = [float(x) for x in distances.split(",") if x.strip()]
    nx, ny = [float(x) for x in north_entry.split(",")]
    sx, sy = [float(x) for x in south_entry.split(",")]
    outdir_path = Path(outdir)

    # Parse width map
    width_map_half = {}
    if width_map:
        for pair in width_map.split(","):
            if ":" in pair:
                k, v = pair.split(":")
                width_map_half[float(k)] = float(v)

    with log_step("Building Suez Canal gates and anchorages"):
        res = build_suez(
            out_gates=outdir_path / "gates.geojson",
            out_polys=outdir_path / "polygons.geojson",
            distances_nm=dists,
            half_width_nm=half_width_nm,
            width_map_half_nm=width_map_half or None,
            auto_width_from_tss=auto_width_from_tss,
            use_overpass=use_overpass,
            north_entry=(nx, ny),
            south_entry=(sx, sy),
        )
    rprint(
        f"[green][suez] wrote {res['gates']} gates and {res['polys']} polygons to {outdir_path}[/green]\n"
        f"[dim]Gates: {outdir_path / 'gates.geojson'}[/dim]\n"
        f"[dim]Polygons: {outdir_path / 'polygons.geojson'}[/dim]"
    )


@app.command("open-sea-build-corridor")
def open_sea_build_corridor(
    corridor: str = typer.Argument(..., help="Corridor name: suez | gibraltar | bosporus"),
    outdir: str = typer.Option("data/geo", help="Zielverzeichnis für GeoJSON"),
    distances: str = typer.Option("", help="Distanzen in nm, CSV (leer = corridor-spezifische defaults)"),
    width_map: str = typer.Option("", help="CSV Mapping 'dist:halfwidth', z.B. '10:1.0,25:1.5' (leer = defaults)"),
    use_overpass: bool = typer.Option(True, help="OSM/Seamark via Overpass einbeziehen"),
):
    """
    Build approach gates for maritime corridors (Suez, Gibraltar, Bosporus).

    Examples:
      # Suez with defaults
      open-sea-build-corridor suez

      # Gibraltar with custom widths
      open-sea-build-corridor gibraltar --width-map "10:1.5,25:2.0,50:2.5,100:3.0,150:3.5"

      # Bosporus offline mode
      open-sea-build-corridor bosporus --use-overpass false
    """
    from spvx.open_sea.tools.corridor_builder import build_corridor

    corridor_lower = corridor.lower()

    # Default distances per corridor
    default_distances = {
        "suez": [10, 25, 50, 100, 150],
        "gibraltar": [10, 25, 50, 100, 150],
        "bosporus": [10, 25, 50],
        "venezuela": [10, 25, 50, 100],
        "gulf_mexico": [10, 25, 50, 100],
        "houston": [10, 25, 50],
        "brazil_ports": [10, 25, 50, 100],
        "las_palmas": [10, 25, 50],
    }

    # Default widths (half-widths) per corridor
    default_widths = {
        "suez": {10: 1.0, 25: 1.5, 50: 2.0, 100: 2.5, 150: 3.0},
        "gibraltar": {10: 1.5, 25: 2.0, 50: 2.5, 100: 3.0, 150: 3.5},
        "bosporus": {10: 0.75, 25: 1.0, 50: 1.5},
        "venezuela": {10: 1.0, 25: 1.5, 50: 2.0, 100: 2.5},
        "gulf_mexico": {10: 1.5, 25: 2.0, 50: 2.5, 100: 3.0},
        "houston": {10: 1.0, 25: 1.5, 50: 2.0},
        "brazil_ports": {10: 1.2, 25: 1.8, 50: 2.3, 100: 2.8},
        "las_palmas": {10: 0.8, 25: 1.2, 50: 1.6},
    }

    if corridor_lower not in default_distances:
        raise typer.BadParameter(
            f"Unknown corridor: {corridor}. Must be one of: "
            f"suez, gibraltar, bosporus, venezuela, gulf_mexico, houston, brazil_ports, las_palmas"
        )

    # Parse distances
    if distances:
        dists = [float(x) for x in distances.split(",") if x.strip()]
    else:
        dists = default_distances[corridor_lower]

    # Parse width map
    if width_map:
        width_map_half = {}
        for pair in width_map.split(","):
            if ":" in pair:
                k, v = pair.split(":")
                width_map_half[float(k)] = float(v)
    else:
        width_map_half = default_widths[corridor_lower]

    outdir_path = Path(outdir)
    corridor_dir = outdir_path / corridor_lower

    with log_step(f"Building {corridor.upper()} corridor gates and anchorages"):
        res = build_corridor(
            corridor=corridor_lower,
            out_gates=corridor_dir / "gates.geojson",
            out_polys=corridor_dir / "polygons.geojson",
            distances_nm=dists,
            width_map_half_nm=width_map_half,
            use_overpass=use_overpass,
        )

    rprint(
        f"[green][{corridor_lower}] wrote {res['gates']} gates and {res['polys']} polygons to {corridor_dir}[/green]\n"
        f"[dim]Gates: {corridor_dir / 'gates.geojson'}[/dim]\n"
        f"[dim]Polygons: {corridor_dir / 'polygons.geojson'}[/dim]"
    )


@app.command("open-sea-build-anchorages")
def open_sea_build_anchorages(
    corridor: str = typer.Argument(..., help="Corridor name: suez | gibraltar | bosporus"),
    db_path: str = typer.Option("db/spvx.duckdb", help="Path to DuckDB with AIS data"),
    outdir: str = typer.Option("data/geo", help="Output directory"),
    lookback_days: int = typer.Option(60, help="Days of AIS history to analyze"),
    sog_max: float = typer.Option(0.5, help="Maximum SOG (knots) for dwell detection"),
    dwell_min_minutes: int = typer.Option(60, help="Minimum dwell time (minutes)"),
    buffer_meters: float = typer.Option(200.0, help="Buffer around dwell points (meters)"),
    min_points: int = typer.Option(10, help="Minimum points required for polygon"),
    alpha: float | None = typer.Option(None, help="Alpha-shape parameter (None = auto)"),
    table_name: str = typer.Option("ais_canon", help="Table name (ais_canon or open_sea_fixes)"),
    timestamp_field: str = typer.Option("msg_time", help="Timestamp field (msg_time or ts)"),
):
    """
    Generate anchorage polygons from AIS dwell data using alpha-shapes.

    This command analyzes historical AIS data to identify areas where vessels
    dwell (low speed, minimal movement) and generates realistic anchorage polygons.

    Examples:
      # Generate Suez anchorages from last 60 days
      open-sea-build-anchorages suez

      # Gibraltar with custom dwell threshold
      open-sea-build-anchorages gibraltar --dwell-min-minutes 120

      # Bosporus with manual alpha parameter
      open-sea-build-anchorages bosporus --alpha 0.5
    """
    from spvx.open_sea.tools.anchorage_from_ais import (
        generate_anchorages_for_corridor,
        save_anchorages,
        DwellConfig,
        AnchorageConfig,
        CORRIDOR_ANCHORAGES,
    )

    corridor_lower = corridor.lower()

    if corridor_lower not in CORRIDOR_ANCHORAGES:
        raise typer.BadParameter(f"Unknown corridor: {corridor}. Must be one of: suez, gibraltar, bosporus")

    dwell_config = DwellConfig(
        sog_max=sog_max,
        dwell_min_minutes=dwell_min_minutes,
        lookback_days=lookback_days,
    )

    anchorage_config = AnchorageConfig(
        alpha=alpha,
        buffer_meters=buffer_meters,
        min_points=min_points,
    )

    with log_step(f"Generating AIS-based anchorages for {corridor.upper()}"):
        features = generate_anchorages_for_corridor(
            db_path=db_path,
            corridor=corridor_lower,
            anchorage_definitions=CORRIDOR_ANCHORAGES[corridor_lower],
            dwell_config=dwell_config,
            anchorage_config=anchorage_config,
            table_name=table_name,
            timestamp_field=timestamp_field,
        )

    if not features:
        rprint(
            f"[yellow]Warning: No anchorages generated for {corridor}.[/yellow]\n"
            f"[dim]This likely means insufficient AIS dwell data in the database.[/dim]\n"
            f"[dim]Try: (1) reducing --min-points, (2) increasing --lookback-days, or (3) checking open_sea_fixes table.[/dim]"
        )
        return

    outdir_path = Path(outdir) / corridor_lower
    out_path = outdir_path / "anchorages_ais.geojson"

    save_anchorages(features, out_path)

    rprint(
        f"[green][{corridor_lower}] Generated {len(features)} AIS-based anchorages[/green]\n"
        f"[dim]Output: {out_path}[/dim]\n"
        f"[dim]Lookback: {lookback_days} days, Min dwell: {dwell_min_minutes} min, SOG max: {sog_max} kn[/dim]"
    )


@app.command("open-sea-current-anchorage")
def open_sea_current_anchorage(
    anchorage: str = typer.Argument(..., help="Anchorage name (e.g., port_said, bosporus_south)"),
    db_path: str = typer.Option("db/spvx.duckdb", help="Path to DuckDB"),
    table_name: str = typer.Option("ais_canon", help="AIS table name"),
    timestamp_field: str = typer.Option("msg_time", help="Timestamp field"),
    sog_threshold: float = typer.Option(0.5, help="Max SOG for dwelling (knots)"),
    max_age_hours: float = typer.Option(2.0, help="Max age of last fix (hours)"),
):
    """
    Show vessels currently dwelling in an anchorage area.

    Examples:
      # Port Said anchorage current occupancy
      open-sea-current-anchorage port_said

      # Bosporus South with custom SOG threshold
      open-sea-current-anchorage bosporus_south --sog-threshold 1.0
    """
    from spvx.analytics.current_anchorage import (
        get_current_dwelling_vessels,
        format_dwelling_vessels_table,
        get_anchorage_statistics,
    )

    # Predefined anchorage bounding boxes
    anchorages = {
        "port_said": (32.12, 31.34, 32.56, 31.54),
        "great_bitter_lake": (32.35, 30.26, 32.42, 30.50),
        "bosporus_south": (28.80, 40.85, 29.20, 41.10),
        "bosporus_north": (28.90, 41.10, 29.20, 41.30),
        "gibraltar_bay": (-5.40, 36.10, -5.30, 36.18),
        "algeciras": (-5.50, 36.08, -5.40, 36.15),
    }

    anchorage_lower = anchorage.lower()
    if anchorage_lower not in anchorages:
        rprint(f"[red]Unknown anchorage: {anchorage}[/red]")
        rprint(f"[dim]Available: {', '.join(anchorages.keys())}[/dim]")
        raise typer.Exit(1)

    bbox = anchorages[anchorage_lower]

    with log_step(f"Querying current vessels in {anchorage.upper()}"):
        vessels = get_current_dwelling_vessels(
            db_path=db_path,
            bbox=bbox,
            table_name=table_name,
            timestamp_field=timestamp_field,
            sog_threshold=sog_threshold,
            max_age_hours=max_age_hours,
        )

    stats = get_anchorage_statistics(vessels)

    rprint(f"\n[bold cyan]═══ {anchorage.upper()} - Current Anchorage Occupancy ═══[/bold cyan]\n")
    rprint(f"[green]Total vessels:[/green] {stats['total_vessels']}")
    rprint(f"[green]Tankers:[/green] {stats['tankers']}")
    rprint(f"[green]Avg dwell time:[/green] {stats['avg_dwell_hours']:.1f} hours")
    rprint(f"[green]Max dwell time:[/green] {stats['max_dwell_hours']:.1f} hours")
    rprint(f"[dim]Criteria: SOG ≤ {sog_threshold} kn, Last fix within {max_age_hours} hours[/dim]\n")

    if vessels:
        rprint(format_dwelling_vessels_table(vessels))
    else:
        rprint("[yellow]No dwelling vessels found in this anchorage.[/yellow]")


@app.command("open-sea-convoy-windows")
def open_sea_convoy_windows(
    db_path: str = typer.Option("db/spvx.duckdb"),
    gates_csv: str = typer.Option("GATE_SUEZ_N_10NM,GATE_SUEZ_S_10NM"),
    days: int = typer.Option(30),
    out: str = typer.Option("data/geo/convoy_windows.json"),
):
    """
    Derive convoy time windows from historical gate_crossings data.
    """
    from spvx.open_sea.tools.suez_builder import derive_convoy_windows

    gate_ids = [g.strip() for g in gates_csv.split(",") if g.strip()]

    with log_step("Analyzing convoy windows from gate crossings"):
        win = derive_convoy_windows(db_path, gate_ids, days)

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(win, indent=2, ensure_ascii=False))
    rprint(f"[green][suez] wrote convoy windows to {out_path}[/green]")


@app.command("registry-bootstrap")
def registry_bootstrap(
    db_path: str = typer.Option("db/spvx.duckdb", help="Path to DuckDB database"),
    since: str = typer.Option("7d", help="Look back period (e.g., '7d', '30d')"),
):
    """
    Bootstrap ship_registry with skeleton entries for unknown MMSIs.

    Creates entries with NULL type but valid first_seen/last_seen timestamps
    for all vessels that have transmitted AIS data in the specified time window.
    """
    from spvx.registry.schema import create_ship_registry_schema, bootstrap_unknown_mmsi

    # Parse time period
    if since.endswith('d'):
        days = int(since[:-1])
    else:
        days = int(since)

    with log_step(f"Bootstrapping ship registry from last {days} days"):
        con = duckdb.connect(db_path)
        try:
            # Ensure schema exists
            create_ship_registry_schema(con)

            # Bootstrap unknown vessels
            count = bootstrap_unknown_mmsi(con, since_days=days)

            rprint(f"[green]✓ Bootstrapped {count:,} new MMSIs[/green]")

        finally:
            con.close()


@app.command("registry-enrich")
def registry_enrich(
    db_path: str = typer.Option("db/spvx.duckdb", help="Path to DuckDB database"),
    horizon: str = typer.Option("90d", help="Look back period for heuristics"),
    geo_term: str = typer.Option("data/geo/oil_terminals.geojson", help="Oil terminals GeoJSON"),
    geo_sts: str = typer.Option("data/geo/sts_zones.geojson", help="STS zones GeoJSON"),
    skip_rules: str = typer.Option("", help="Comma-separated rule IDs to skip"),
):
    """
    Enrich ship_registry using behavioral heuristics (H1-H3).

    Applies:
    - H1: Terminal-Dwell (oil terminals)
    - H2: STS-Zone (ship-to-ship transfer areas)
    - H3: Corridor-Pattern (frequent chokepoint crossings)

    Writes audit trail to ship_registry_audit table.
    """
    from spvx.registry.heuristics import apply_all_heuristics
    from spvx.registry.schema import create_ship_registry_schema, get_registry_stats

    # Parse horizon
    if horizon.endswith('d'):
        days = int(horizon[:-1])
    else:
        days = int(horizon)

    # Parse skip rules
    skip_list = [r.strip() for r in skip_rules.split(',') if r.strip()]

    with log_step(f"Enriching ship registry (horizon={days}d)"):
        con = duckdb.connect(db_path)
        try:
            # Ensure schema exists
            create_ship_registry_schema(con)

            # Apply heuristics
            results = apply_all_heuristics(con, horizon_days=days, skip_rules=skip_list)

            # Show results
            rprint("\n[bold]Classification Results:[/bold]")
            for rule_id, count in results.items():
                rprint(f"  {rule_id}: {count:,} vessels")

            # Show updated stats
            stats = get_registry_stats(con)
            rprint(f"\n[bold]Registry Status:[/bold]")
            rprint(f"  Total vessels: {stats['total']:,}")
            rprint(f"  Tankers: {stats['tankers']:,}")
            rprint(f"  Unknown (24h): {stats['unknown_24h']:,}")
            avg_conf = stats['avg_confidence']
            rprint(f"  Avg confidence: {avg_conf:.2f}" if avg_conf is not None else "  Avg confidence: N/A")

        finally:
            con.close()


@app.command("registry-stats")
def registry_stats(
    db_path: str = typer.Option("db/spvx.duckdb", help="Path to DuckDB database"),
):
    """
    Show current ship registry statistics.
    """
    from spvx.registry.schema import get_registry_stats

    con = duckdb.connect(db_path, read_only=True)
    try:
        stats = get_registry_stats(con)

        rprint("\n[bold cyan]Ship Registry Statistics[/bold cyan]")
        rprint("=" * 50)
        rprint(f"📊 Total vessels:       {stats['total']:,}")
        rprint(f"🛢️  Tankers:             {stats['tankers']:,}")
        rprint(f"❓ Unknown (24h):       {stats['unknown_24h']:,}")
        avg_conf = stats['avg_confidence']
        rprint(f"📈 Avg confidence:      {avg_conf:.2f}" if avg_conf is not None else "📈 Avg confidence:      N/A")

        # Breakdown by source
        result = con.execute("""
            SELECT type_source, COUNT(*) as cnt
            FROM ship_registry
            WHERE type_source IS NOT NULL
            GROUP BY type_source
            ORDER BY cnt DESC
        """).fetchall()

        if result:
            rprint("\n[bold]Classification Sources:[/bold]")
            for source, cnt in result:
                rprint(f"  {source}: {cnt:,}")

    finally:
        con.close()


@app.command("registry-backfill")
def registry_backfill(
    db_path: str = typer.Option("db/spvx.duckdb", help="Path to DuckDB database"),
    since: str = typer.Option("", help="Start date (YYYY-MM-DD) or leave empty for all"),
):
    """
    Backfill tanker detection for historical AIS records.

    Updates ais_canon.is_tanker flag based on current ship_registry.
    Processes all historical data to ensure no data loss.
    """
    with log_step("Backfilling tanker flags in ais_canon"):
        con = duckdb.connect(db_path)
        try:
            # Build WHERE clause
            where_clause = ""
            if since:
                where_clause = f"WHERE a.msg_time >= '{since}'"

            # Update is_tanker flag
            result = con.execute(f"""
                UPDATE ais_canon a
                SET is_tanker = (
                    SELECT CASE
                        WHEN r.ship_type_code >= 80 AND r.ship_type_code < 90 THEN TRUE
                        ELSE FALSE
                    END
                    FROM ship_registry r
                    WHERE r.mmsi = a.mmsi
                )
                {where_clause}
                RETURNING mmsi
            """)

            count = len(result.fetchall())
            con.commit()

            rprint(f"[green]✓ Backfilled {count:,} records[/green]")

            # Show tanker statistics
            result = con.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN is_tanker THEN 1 ELSE 0 END) as tankers,
                    SUM(CASE WHEN is_tanker THEN 1 ELSE 0 END)::FLOAT / COUNT(*) * 100 as pct
                FROM ais_canon
            """).fetchone()

            if result:
                total, tankers, pct = result
                rprint(f"\n[bold]AIS Canon Statistics:[/bold]")
                rprint(f"  Total records: {total:,}")
                rprint(f"  Tanker records: {tankers:,}")
                rprint(f"  Tanker %: {pct:.1f}%")

        finally:
            con.close()


@app.command("registry-decay")
def registry_decay(
    db_path: str = typer.Option("db/spvx.duckdb", help="Path to DuckDB database"),
    days: int = typer.Option(180, help="Apply decay if last_seen > N days ago"),
):
    """
    Apply confidence decay to heuristic classifications without recent evidence.

    Reduces confidence by 0.2 (min 0.5) for vessels not seen in last N days.
    TYPE5 classifications are never decayed.
    """
    from spvx.registry.schema import apply_confidence_decay

    with log_step(f"Applying confidence decay (>{days}d without evidence)"):
        con = duckdb.connect(db_path)
        try:
            count = apply_confidence_decay(con, days_threshold=days)
            rprint(f"[green]✓ Applied decay to {count:,} vessels[/green]")
        finally:
            con.close()


@app.command("polygon-detect")
def polygon_detect(
    db_path: str = typer.Option("db/spvx.duckdb", help="Path to DuckDB database"),
    terminals: str = typer.Option("data/geo/oil_terminals.geojson", help="Oil terminals GeoJSON"),
    sts: str = typer.Option("data/geo/sts_zones.geojson", help="STS zones GeoJSON"),
    since: str = typer.Option("7d", help="Replay fixes since (e.g., '7d', '2025-10-20')"),
    batch_size: int = typer.Option(10000, help="Process fixes in batches of this size"),
):
    """
    Replay AIS fixes through polygon detector to generate polygon_events.

    Processes historical ais_canon data and detects vessel dwells at oil
    terminals and STS zones. Creates polygon_events table with completed dwells.
    """
    from spvx.open_sea.polygon_detect import PolygonDetector, PolygonConfig
    from datetime import datetime

    # Parse since parameter
    if since.endswith('d'):
        days = int(since[:-1])
        since_clause = f"msg_time >= NOW() - INTERVAL '{days} days'"
    else:
        since_clause = f"msg_time >= '{since}'"

    with log_step(f"Replaying AIS fixes through polygon detector (since={since})"):
        con = duckdb.connect(db_path)
        try:
            # Initialize detector
            config = PolygonConfig()
            detector = PolygonDetector(con, terminals, sts, config)

            # Query fixes - count first
            count_result = con.execute(f"""
                SELECT COUNT(*) FROM ais_canon WHERE {since_clause}
            """).fetchone()
            total_available = count_result[0] if count_result else 0
            rprint(f"[cyan]Found {total_available:,} AIS fixes to process...[/cyan]")

            # Process in batches using LIMIT/OFFSET
            total_fixes = 0
            total_events = 0
            offset = 0

            while offset < total_available:
                batch = con.execute(f"""
                    SELECT mmsi, msg_time, lon, lat, sog
                    FROM ais_canon
                    WHERE {since_clause}
                    ORDER BY msg_time ASC
                    LIMIT {batch_size} OFFSET {offset}
                """).fetchall()

                if not batch:
                    break

                for row in batch:
                    mmsi, ts, lon, lat, sog = row
                    events = detector.handle_fix(mmsi, ts, lon, lat, sog)
                    total_events += len(events)
                    total_fixes += 1

                if total_fixes % 50000 == 0:
                    rprint(f"  Processed {total_fixes:,}/{total_available:,} fixes, {total_events} events so far...")
                    detector.flush()  # Periodic flush

                offset += batch_size

            # Finalize
            rprint(f"[cyan]Finalizing detector...[/cyan]")
            final_events = detector.finalize(datetime.now())
            total_events += len(final_events)

            con.commit()

            rprint(f"\n[bold green]✓ Polygon Detection Complete[/bold green]")
            rprint(f"  Fixes processed: {total_fixes:,}")
            rprint(f"  Events generated: {total_events:,}")

            # Show summary
            summary = con.execute("""
                SELECT kind, COUNT(*) as events, SUM(dwell_min) as total_dwell_min
                FROM polygon_events
                GROUP BY kind
            """).fetchall()

            if summary:
                rprint("\n[bold]Event Summary:[/bold]")
                for kind, events, total_dwell in summary:
                    rprint(f"  {kind}: {events:,} events ({total_dwell:,} min total dwell)")

        finally:
            con.close()


@app.command("polygon-aggregate")
def polygon_aggregate(
    db_path: str = typer.Option("db/spvx.duckdb", help="Path to DuckDB database"),
    date: str = typer.Option("", help="Date to aggregate (YYYY-MM-DD), empty = yesterday"),
):
    """
    Aggregate polygon_events into daily rollups.

    Creates summary tables:
    - terminal_visits_daily: Visits per terminal per day
    - sts_visits_daily: Visits per STS zone per day
    """
    from datetime import datetime, timedelta

    # Parse date
    if date:
        target_date = date
    else:
        yesterday = datetime.now() - timedelta(days=1)
        target_date = yesterday.strftime('%Y-%m-%d')

    with log_step(f"Aggregating polygon events for {target_date}"):
        con = duckdb.connect(db_path)
        try:
            # Create aggregate tables
            con.execute("""
                CREATE TABLE IF NOT EXISTS terminal_visits_daily (
                    ds DATE,
                    polygon_id VARCHAR,
                    visits INTEGER,
                    dwell_sum_min INTEGER,
                    unique_vessels INTEGER,
                    PRIMARY KEY (ds, polygon_id)
                )
            """)

            con.execute("""
                CREATE TABLE IF NOT EXISTS sts_visits_daily (
                    ds DATE,
                    polygon_id VARCHAR,
                    visits INTEGER,
                    dwell_sum_min INTEGER,
                    unique_vessels INTEGER,
                    PRIMARY KEY (ds, polygon_id)
                )
            """)

            # Aggregate terminals
            result = con.execute(f"""
                INSERT INTO terminal_visits_daily (ds, polygon_id, visits, dwell_sum_min, unique_vessels)
                SELECT
                    DATE(ts_in) as ds,
                    polygon_id,
                    COUNT(*) as visits,
                    SUM(dwell_min) as dwell_sum_min,
                    COUNT(DISTINCT mmsi) as unique_vessels
                FROM polygon_events
                WHERE kind = 'OIL_TERMINAL'
                  AND DATE(ts_in) = '{target_date}'
                GROUP BY DATE(ts_in), polygon_id
                ON CONFLICT (ds, polygon_id) DO UPDATE SET
                    visits = EXCLUDED.visits,
                    dwell_sum_min = EXCLUDED.dwell_sum_min,
                    unique_vessels = EXCLUDED.unique_vessels
                RETURNING polygon_id
            """)
            terminal_count = len(result.fetchall())

            # Aggregate STS zones
            result = con.execute(f"""
                INSERT INTO sts_visits_daily (ds, polygon_id, visits, dwell_sum_min, unique_vessels)
                SELECT
                    DATE(ts_in) as ds,
                    polygon_id,
                    COUNT(*) as visits,
                    SUM(dwell_min) as dwell_sum_min,
                    COUNT(DISTINCT mmsi) as unique_vessels
                FROM polygon_events
                WHERE kind = 'STS_ZONE'
                  AND DATE(ts_in) = '{target_date}'
                GROUP BY DATE(ts_in), polygon_id
                ON CONFLICT (ds, polygon_id) DO UPDATE SET
                    visits = EXCLUDED.visits,
                    dwell_sum_min = EXCLUDED.dwell_sum_min,
                    unique_vessels = EXCLUDED.unique_vessels
                RETURNING polygon_id
            """)
            sts_count = len(result.fetchall())

            con.commit()

            rprint(f"[green]✓ Aggregated {target_date}[/green]")
            rprint(f"  Terminals: {terminal_count} polygons")
            rprint(f"  STS zones: {sts_count} polygons")

        finally:
            con.close()


@app.command("compute-index")
def compute_index_cmd(
    version: str = typer.Option("1.5", help="Index version: 1.5"),
    date: str = typer.Option(None, help="Target date (YYYY-MM-DD), defaults to today"),
    start_date: str = typer.Option(None, help="Start date for time series (YYYY-MM-DD)"),
    end_date: str = typer.Option(None, help="End date for time series (YYYY-MM-DD)"),
    output: Path | None = typer.Option(None, help="Output JSON file path"),
):
    """
    Compute SPVX Global Index v1.5 (robust & explainable).

    Examples:
      # Single date
      python -m spvx.cli compute-index --version=1.5

      # Time series
      python -m spvx.cli compute-index --start-date=2025-10-01 --end-date=2025-10-31
    """
    import datetime as dt
    import json

    from spvx.index.v1_5 import compute_global_index_timeseries, compute_global_index_v15, forecast_global_index_v15

    settings = AppSettings()
    con = duckdb.connect(str(settings.duckdb_path), read_only=True)

    try:
        if version == "1.5":
            if start_date and end_date:
                # Time series
                start = dt.date.fromisoformat(start_date)
                end = dt.date.fromisoformat(end_date)

                rprint(f"[cyan]Computing Global Index v1.5 time series: {start} to {end}[/cyan]")
                df = compute_global_index_timeseries(con, start, end)

                result = {
                    "version": "1.5",
                    "type": "timeseries",
                    "start_date": start_date,
                    "end_date": end_date,
                    "data": df.to_dict(orient="records"),
                }

                rprint(f"[green]✓ Computed {len(df)} days[/green]")
                rprint(f"  Mean Index: {df['global_index_scaled'].mean():.2f}")
                rprint(f"  Range: {df['global_index_scaled'].min():.2f} - {df['global_index_scaled'].max():.2f}")
            else:
                # Single date
                target_date = dt.date.fromisoformat(date) if date else dt.date.today()

                rprint(f"[cyan]Computing Global Index v1.5 for {target_date}[/cyan]")
                result = compute_global_index_v15(con, target_date)

                rprint(f"[green]✓ Global Index: {result['global_index_scaled']:.2f}[/green]")
                rprint(f"  Coverage: {result['coverage']:.1%}")
                rprint(f"  Corridors with data: {result['corridors_with_data']}/{result['num_corridors']}")

                rprint("\n[bold]Component Breakdown:[/bold]")
                for cid, comp in result["components"].items():
                    if comp["has_data"]:
                        rprint(f"  {cid}: stress={comp['stress']:.3f} (flux={comp['flux_score']:.3f}, sis={comp['sis_score']:.3f})")

            # Save output if requested
            if output:
                output.parent.mkdir(parents=True, exist_ok=True)
                with open(output, "w") as f:
                    json.dump(result, f, indent=2, default=str)
                rprint(f"[green]Saved to {output}[/green]")
            else:
                # Print JSON to stdout
                print(json.dumps(result, indent=2, default=str))
        else:
            raise typer.BadParameter(f"Unknown version: {version}")
    finally:
        con.close()


@app.command("forecast")
def forecast_cmd(
    horizon: int = typer.Option(7, help="Forecast horizon in days (default: 7)"),
    date: str = typer.Option(None, help="Base date for forecast (YYYY-MM-DD), defaults to today"),
    output: Path | None = typer.Option(None, help="Output JSON file path"),
):
    """
    Generate 7-day forecast of SPVX Global Index v1.5.

    Uses persistence + EMA approach with uncertainty bands.

    Examples:
      # 7-day forecast from today
      python -m spvx.cli forecast

      # 14-day forecast
      python -m spvx.cli forecast --horizon=14

      # Forecast from specific date
      python -m spvx.cli forecast --date=2025-10-31 --horizon=7
    """
    import datetime as dt
    import json

    from spvx.index.v1_5 import forecast_global_index_v15

    settings = AppSettings()
    con = duckdb.connect(str(settings.duckdb_path), read_only=True)

    try:
        base_date = dt.date.fromisoformat(date) if date else dt.date.today()

        rprint(f"[cyan]Generating {horizon}-day forecast from {base_date}[/cyan]")
        df = forecast_global_index_v15(con, base_date, horizon_days=horizon)

        result = {
            "version": "1.5",
            "type": "forecast",
            "base_date": base_date.isoformat(),
            "horizon_days": horizon,
            "forecast": df.to_dict(orient="records"),
        }

        rprint(f"[green]✓ Generated {len(df)} forecast points[/green]")
        rprint(f"  Method: {df['method'].iloc[0] if not df.empty else 'N/A'}")
        rprint(f"  Coverage: {df['coverage'].iloc[0]:.1%}" if not df.empty else "")

        if not df.empty:
            rprint("\n[bold]Forecast Summary:[/bold]")
            rprint(f"  Day +1: {df['global_index_scaled'].iloc[0]:.2f} ({df['lower_bound'].iloc[0]:.2f} - {df['upper_bound'].iloc[0]:.2f})")
            rprint(f"  Day +{horizon}: {df['global_index_scaled'].iloc[-1]:.2f} ({df['lower_bound'].iloc[-1]:.2f} - {df['upper_bound'].iloc[-1]:.2f})")

        # Save output if requested
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            with open(output, "w") as f:
                json.dump(result, f, indent=2, default=str)
            rprint(f"[green]Saved to {output}[/green]")
        else:
            # Print JSON to stdout
            print(json.dumps(result, indent=2, default=str))
    finally:
        con.close()


@app.command("compute-transit-times")
def compute_transit_times_cmd(
    date: str = typer.Option(None, help="Target date (YYYY-MM-DD), defaults to yesterday"),
):
    """
    Compute transit times through corridors from polygon entry/exit events.

    Transit time = time between ENTER and EXIT of same polygon for each vessel.

    Examples:
      python -m spvx.cli compute-transit-times
      python -m spvx.cli compute-transit-times --date=2025-11-01
    """
    import datetime as dt
    from spvx.etl.transit_times import compute_and_persist_transit_times

    settings = AppSettings()

    target_date = dt.date.fromisoformat(date) if date else (dt.date.today() - dt.timedelta(days=1))

    rprint(f"[cyan]Computing transit times for {target_date}[/cyan]")

    df = compute_and_persist_transit_times(str(settings.duckdb_path), target_date)

    if not df.empty:
        rprint(f"[green]✓ Computed transit times for {len(df)} corridors[/green]")
        rprint("\n[bold]Transit Time Summary:[/bold]")
        for _, row in df.iterrows():
            rprint(f"  {row['corridor_id']}: {row['median_h']:.2f}h median ({row['num_transits']} transits)")
    else:
        rprint("[yellow]⚠ No complete transits found[/yellow]")
        rprint("  Vessels need to fully ENTER and EXIT on the same date")


@app.command("derive-anchorage")
def derive_anchorage_cmd(
    db: str = typer.Option("db/spvx.duckdb", help="Path to DuckDB database"),
    polygons: str = typer.Option("data/geo/polygons.geojson", help="GeoJSON file to update"),
    name: str = typer.Option("ANCH_LAS_PALMAS", "--name", help="Feature id for the anchorage"),
    feature_name: str = typer.Option("Las Palmas Anchorage", help="Human-readable feature name"),
    center_lat: float = typer.Option(28.13, help="Latitude center for candidate fixes"),
    center_lon: float = typer.Option(-15.42, help="Longitude center for candidate fixes"),
    radius_km: float = typer.Option(22.0, help="Search radius around center (km)"),
    days: int = typer.Option(14, help="Lookback window in days"),
    sog_max_kn: float = typer.Option(0.5, help="Maximum SOG threshold for dwell points (knots)"),
    eps_m: float = typer.Option(350.0, help="DBSCAN epsilon (meters)"),
    min_samples: int = typer.Option(30, help="Minimum samples per cluster"),
    buffer_m: float = typer.Option(120.0, help="Buffer around convex hull (meters)"),
    simplify_m: float = typer.Option(30.0, help="Simplify tolerance in meters"),
):
    """
    Derive an anchorage polygon by clustering slow-speed AIS fixes.
    """
    params = DeriveParams(
        center_lat=center_lat,
        center_lon=center_lon,
        radius_km=radius_km,
        days_lookback=days,
        sog_max_kn=sog_max_kn,
        eps_m=eps_m,
        min_samples=min_samples,
        buffer_m=buffer_m,
        simplify_m=simplify_m,
        feature_name=feature_name,
    )
    feature = build_anchorage(db, polygons, params=params, fid=name)
    points = feature["properties"]["metadata"]["cluster_points"]
    typer.echo(
        f"Anchorage '{name}' ({feature['properties']['name']}) written to {polygons} "
        f"using {points} dwell fixes"
    )


@app.command("anchorage-episodes")
def anchorage_episodes_cmd(
    db: str = typer.Option("db/spvx.duckdb", help="Path to DuckDB database"),
    polygons: str = typer.Option("data/geo/polygons.geojson", help="Anchorage polygons GeoJSON"),
    start: Optional[str] = typer.Option(None, help="Start timestamp (YYYY-MM-DD)"),
    end: Optional[str] = typer.Option(None, help="End timestamp (YYYY-MM-DD)"),
    min_dwell_min: int = typer.Option(60, help="Minimum dwell time in minutes"),
):
    """
    Detect anchorage episodes from AIS fixes (TH-2).

    Processes AIS fixes to detect when vessels enter/exit anchorage areas
    and creates episode records with dwell times.
    """
    from spvx.anchorage.detect import AnchorageConfig, AnchorageDetector
    from datetime import datetime

    rprint("[bold cyan]TH-2: Anchorage Episode Detection[/bold cyan]")

    # Parse dates
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None

    # Connect to database
    con = duckdb.connect(db)

    # Create detector
    config = AnchorageConfig(min_dwell_min=min_dwell_min)
    detector = AnchorageDetector(con, polygons, config)

    # Process fixes
    detector.process_fixes(start_ts=start_dt, end_ts=end_dt)

    # Show summary
    result = con.execute("""
        SELECT
            anchorage_id,
            COUNT(*) as episodes,
            COUNT(DISTINCT mmsi) as vessels,
            AVG(dwell_hours) as avg_dwell_h,
            MAX(ts_exit) as latest_exit
        FROM anchorage_episodes
        GROUP BY anchorage_id
        ORDER BY episodes DESC
    """).fetchall()

    rprint("\n[bold]Episode Summary:[/bold]")
    if result:
        for anch, eps, vessels, avg_dwell, latest in result:
            rprint(f"  {anch:30s}: {eps:5d} episodes | {vessels:4d} vessels | {avg_dwell:5.1f}h avg")
    else:
        rprint("[yellow]  No episodes detected yet[/yellow]")

    con.close()


@app.command("anchorage-backfill")
def anchorage_backfill_cmd(
    db: str = typer.Option("db/spvx.duckdb", help="Path to DuckDB database"),
    start: Optional[str] = typer.Option(None, help="Start date for aggregation (YYYY-MM-DD)"),
    end: Optional[str] = typer.Option(None, help="End date for aggregation (YYYY-MM-DD)"),
    lookback_days: int = typer.Option(90, help="Days to use for baseline computation"),
    min_samples: int = typer.Option(20, help="Minimum samples per baseline bucket"),
):
    """
    Compute daily metrics, baselines, and Z-scores for anchorages (TH-3).

    Aggregates episodes into daily metrics and enriches with statistical
    baselines for anomaly detection.
    """
    from spvx.anchorage.baseline import backfill_all
    from datetime import datetime

    rprint("[bold cyan]TH-3: Anchorage Baseline & Z-Score Enrichment[/bold cyan]")

    # Parse dates
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None

    # Connect to database
    con = duckdb.connect(db)

    # Run backfill
    backfill_all(con, start_dt, end_dt, lookback_days, min_samples)

    # Show summary
    result = con.execute("""
        SELECT
            anchorage_id,
            COUNT(*) as days,
            AVG(median_dwell_h) as avg_dwell,
            COUNT(*) FILTER (WHERE anomaly_detected) as anomaly_days,
            MAX(ds) as latest_date
        FROM anchorage_daily_dwell
        GROUP BY anchorage_id
        ORDER BY days DESC
    """).fetchall()

    rprint("\n[bold]Daily Metrics Summary:[/bold]")
    if result:
        for anch, days, avg_dwell, anomalies, latest in result:
            status = "🔴" if anomalies > 0 else "✅"
            rprint(f"  {status} {anch:30s}: {days:3d} days | {avg_dwell:5.1f}h avg | {anomalies:2d} anomalies | Latest: {latest}")
    else:
        rprint("[yellow]  No daily metrics yet[/yellow]")

    con.close()


def run():
    app()


if __name__ == "__main__":
    run()
