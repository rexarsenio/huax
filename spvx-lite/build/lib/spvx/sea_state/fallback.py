"""
Fallback logic for sea-state ingestion with retry chain.

Implements provider fallback: CMEMS → RTOFS → graceful degradation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

import pandas as pd

LOG = logging.getLogger("spvx.sea_state.fallback")


class ProviderStatus(str, Enum):
    """Sea-state provider status."""

    SUCCESS = "success"
    FAILED = "failed"
    DEGRADED = "degraded"


@dataclass
class IngestionResult:
    """Result of sea-state ingestion attempt."""

    provider: str
    status: ProviderStatus
    files_downloaded: int = 0
    rows_processed: int = 0
    error: Optional[str] = None
    degradation_mask: dict[str, bool] = None

    def __post_init__(self):
        if self.degradation_mask is None:
            self.degradation_mask = {}


class SeaStateFallbackChain:
    """
    Manages fallback logic for sea-state data ingestion.

    Tries providers in order: CMEMS → RTOFS → Degraded mode
    """

    def __init__(
        self,
        cmems_username: Optional[str] = None,
        cmems_password: Optional[str] = None,
        config: dict = None,
    ):
        """
        Initialize fallback chain.

        Args:
            cmems_username: CMEMS credentials (optional)
            cmems_password: CMEMS password (optional)
            config: Configuration dict with sea_state and chokepoints settings
        """
        self.cmems_username = cmems_username
        self.cmems_password = cmems_password
        self.config = config or {}

    def ingest_with_fallback(
        self, lookback_days: int = 3, region_list: Optional[list[str]] = None
    ) -> IngestionResult:
        """
        Attempt ingestion with automatic fallback.

        Order:
        1. Try CMEMS (if credentials available)
        2. Fallback to RTOFS
        3. Graceful degradation (disable weather components)

        Args:
            lookback_days: Days of historical data to fetch
            region_list: List of chokepoint IDs (None = all)

        Returns:
            IngestionResult with provider used and status
        """
        # Try CMEMS first
        if self.cmems_username and self.cmems_password:
            LOG.info("Attempting CMEMS ingestion...")
            result = self._try_cmems(lookback_days, region_list)
            if result.status == ProviderStatus.SUCCESS:
                LOG.info("CMEMS ingestion successful")
                return result
            LOG.warning(f"CMEMS failed: {result.error}. Falling back to RTOFS...")

        # Fallback to RTOFS
        LOG.info("Attempting RTOFS ingestion...")
        result = self._try_rtofs(region_list)
        if result.status == ProviderStatus.SUCCESS:
            LOG.info("RTOFS ingestion successful")
            return result
        LOG.warning(f"RTOFS failed: {result.error}. Degrading gracefully...")

        # Final fallback: disable weather components
        LOG.info("All providers failed, creating degradation mask...")
        return self._create_degraded_result()

    def _try_cmems(
        self, lookback_days: int, region_list: Optional[list[str]]
    ) -> IngestionResult:
        """Attempt CMEMS ingestion."""
        try:
            from spvx.sea_state.cmems import (
                _list_days_yyyymmdd,
                area_mean_opp_current,
                area_mean_waves,
                download_currents,
                download_waves,
            )

            sea_cfg = self.config.get("sea_state", {})
            cps_cfg = self.config.get("chokepoints", {})

            waves_dataset_id = sea_cfg.get("waves_dataset_id")
            currents_dataset_id = sea_cfg.get("currents_dataset_id")
            out_dir = sea_cfg.get("out_dir", "data/sea_state")

            if not waves_dataset_id or not currents_dataset_id:
                return IngestionResult(
                    provider="cmems",
                    status=ProviderStatus.FAILED,
                    error="Missing dataset IDs in config",
                )

            days = _list_days_yyyymmdd(lookback_days)

            # Download waves
            wav_files = download_waves(
                waves_dataset_id,
                f"{out_dir}/waves",
                days,
                username=self.cmems_username,
                password=self.cmems_password,
            )

            # Download currents (allow partial failure)
            cur_files = []
            try:
                cur_files = download_currents(
                    currents_dataset_id,
                    f"{out_dir}/currents",
                    days,
                    username=self.cmems_username,
                    password=self.cmems_password,
                )
            except Exception as exc:
                LOG.warning(f"CMEMS currents download failed: {exc}, continuing with waves only")

            total_rows = 0
            chokepoint_ids = list(cps_cfg.keys()) if not region_list else region_list

            for cid in chokepoint_ids:
                if cid not in cps_cfg:
                    continue

                meta = cps_cfg[cid]
                hs_df = area_mean_waves(wav_files, meta["bbox"])
                oc_df = area_mean_opp_current(cur_files, meta["bbox"], meta["bearing_deg"])

                df = pd.merge(hs_df, oc_df, on="time", how="outer").sort_values("time")
                outp = Path(f"data/processed/sea_state_{cid}.parquet")
                outp.parent.mkdir(parents=True, exist_ok=True)
                df.to_parquet(outp, index=False)
                total_rows += len(df)

            # Update metrics
            try:
                from spvx.metrics import (
                    spvx_sea_state_files_downloaded_total,
                    spvx_sea_state_provider,
                )

                spvx_sea_state_files_downloaded_total.labels(
                    provider="cmems", data_type="waves"
                ).inc(len(wav_files))
                spvx_sea_state_files_downloaded_total.labels(
                    provider="cmems", data_type="currents"
                ).inc(len(cur_files))
                spvx_sea_state_provider.labels(source="cmems").set(1)
                spvx_sea_state_provider.labels(source="rtofs").set(0)
            except Exception:
                pass

            return IngestionResult(
                provider="cmems",
                status=ProviderStatus.SUCCESS,
                files_downloaded=len(wav_files) + len(cur_files),
                rows_processed=total_rows,
            )

        except Exception as exc:
            LOG.error(f"CMEMS ingestion error: {exc}")
            return IngestionResult(
                provider="cmems", status=ProviderStatus.FAILED, error=str(exc)
            )

    def _try_rtofs(self, region_list: Optional[list[str]]) -> IngestionResult:
        """Attempt RTOFS ingestion."""
        try:
            from spvx.weather import run_sea_state

            currents, waves = run_sea_state(region_list)

            if currents == 0 and waves == 0:
                return IngestionResult(
                    provider="rtofs",
                    status=ProviderStatus.FAILED,
                    error="No samples retrieved",
                )

            # Update metrics
            try:
                from spvx.metrics import spvx_sea_state_provider

                spvx_sea_state_provider.labels(source="rtofs").set(1)
                spvx_sea_state_provider.labels(source="cmems").set(0)
            except Exception:
                pass

            return IngestionResult(
                provider="rtofs",
                status=ProviderStatus.SUCCESS,
                rows_processed=currents + waves,
            )

        except Exception as exc:
            LOG.error(f"RTOFS ingestion error: {exc}")
            return IngestionResult(
                provider="rtofs", status=ProviderStatus.FAILED, error=str(exc)
            )

    def _create_degraded_result(self) -> IngestionResult:
        """
        Create degraded result that disables weather components.

        Returns a result with degradation mask marking weather features as unavailable.
        """
        degradation_mask = {
            "SEA_HS_Z": True,  # Wave height anomaly unavailable
            "OPPOSING_CURRENT": True,  # Current data unavailable
            "weather_data_available": False,
        }

        # Write degradation state to disk for feature computation
        mask_path = Path("data/processed/weather_degradation_mask.json")
        mask_path.parent.mkdir(parents=True, exist_ok=True)
        import json

        with open(mask_path, "w") as f:
            json.dump(degradation_mask, f)

        LOG.warning(
            f"Weather degradation activated. Mask written to {mask_path}. "
            "Index will use SPVX_LITE_EX_WEATHER variant."
        )

        # Update metrics
        try:
            from spvx.metrics import spvx_sea_state_provider

            spvx_sea_state_provider.labels(source="cmems").set(0)
            spvx_sea_state_provider.labels(source="rtofs").set(0)
        except Exception:
            pass

        return IngestionResult(
            provider="degraded",
            status=ProviderStatus.DEGRADED,
            degradation_mask=degradation_mask,
            error="All providers failed, weather components disabled",
        )


def should_use_degraded_index() -> bool:
    """
    Check if weather degradation is active.

    Returns:
        True if degradation mask exists and weather is unavailable
    """
    mask_path = Path("data/processed/weather_degradation_mask.json")
    if not mask_path.exists():
        return False

    import json

    try:
        with open(mask_path) as f:
            mask = json.load(f)
        return not mask.get("weather_data_available", True)
    except Exception:
        return False
