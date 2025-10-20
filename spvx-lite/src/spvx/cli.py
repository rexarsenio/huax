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
from spvx.db import ensure_core_tables
from spvx.etl import build_components_daily, compute_basin_indices
from spvx.features.baseline_tables import refresh_doy_baselines
from spvx.features.components import build_components
from spvx.index.spvx_lite import compute_spvx_lite
from spvx.models.spread_direction import ScoreResult, score_spread, train_spread
from spvx.models.throughput_72h import score_throughput, train_throughput
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
            turkish_straits.run()
            mpa_sg.run()
            rotterdam.run()
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
def compute_index():
    with log_step("Building component features"):
        build_components()
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


def run():
    app()


if __name__ == "__main__":
    run()
