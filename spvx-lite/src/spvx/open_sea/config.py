"""
Configuration helpers for the open-sea polygon/gate engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from spvx.config import load_config


@dataclass(frozen=True)
class TTLConfig:
    moving: int
    anchorage: int


@dataclass(frozen=True)
class SOGThresholds:
    dwell_max_kn: float


@dataclass(frozen=True)
class GateDefaults:
    width_nm_default: float


@dataclass(frozen=True)
class CMEMSConfig:
    enabled: bool
    features: tuple[str, ...]


@dataclass(frozen=True)
class SISWeights:
    wave: float
    head_current: float
    head_wind: float


@dataclass(frozen=True)
class SISConfig:
    weights: SISWeights
    high_impact_p: float


@dataclass(frozen=True)
class GateFluxConfig:
    count_modes: tuple[str, ...]
    tanker_only: bool
    sog_min_kn: float
    rehit_hours_default: float
    rehit_hours_by_group: dict[str, float]

    def rehit_hours_for(self, group_id: str) -> float:
        return self.rehit_hours_by_group.get(group_id, self.rehit_hours_default)


@dataclass(frozen=True)
class OpenSeaConfig:
    downsample_secs: int
    hysteresis_hits: int
    ttl_min: TTLConfig
    sog_thresholds: SOGThresholds
    gates: GateDefaults
    cmems: CMEMSConfig
    sis: SISConfig
    flux: GateFluxConfig

    @staticmethod
    def _tuple_features(values: Iterable[str] | None) -> tuple[str, ...]:
        if values is None:
            return ()
        return tuple(str(item) for item in values)

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "OpenSeaConfig":
        ttl_data = data.get("ttl_min")
        if not isinstance(ttl_data, Mapping):
            raise ValueError("open_sea.ttl_min section missing or invalid.")
        sog_data = data.get("sog_thresholds")
        if not isinstance(sog_data, Mapping):
            raise ValueError("open_sea.sog_thresholds section missing or invalid.")
        gates_data = data.get("gates")
        if not isinstance(gates_data, Mapping):
            raise ValueError("open_sea.gates section missing or invalid.")
        cmems_data = data.get("cmems")
        if not isinstance(cmems_data, Mapping):
            raise ValueError("open_sea.cmems section missing or invalid.")
        sis_data = data.get("sis")
        if not isinstance(sis_data, Mapping):
            raise ValueError("open_sea.sis section missing or invalid.")
        weights_data = sis_data.get("weights")
        if not isinstance(weights_data, Mapping):
            raise ValueError("open_sea.sis.weights section missing or invalid.")

        ttl_cfg = TTLConfig(
            moving=int(ttl_data.get("moving", 30)),
            anchorage=int(ttl_data.get("anchorage", 90)),
        )
        sog_cfg = SOGThresholds(
            dwell_max_kn=float(sog_data.get("dwell_max_kn", 1.0)),
        )
        gate_cfg = GateDefaults(
            width_nm_default=float(gates_data.get("width_nm_default", 0.8)),
        )
        cmems_cfg = CMEMSConfig(
            enabled=bool(cmems_data.get("enabled", False)),
            features=cls._tuple_features(cmems_data.get("features")),
        )
        sis_cfg = SISConfig(
            weights=SISWeights(
                wave=float(weights_data.get("wave", 0.5)),
                head_current=float(weights_data.get("head_current", 0.35)),
                head_wind=float(weights_data.get("head_wind", 0.15)),
            ),
            high_impact_p=float(sis_data.get("high_impact_p", 0.7)),
        )
        flux_data = data.get("flux", {})
        if flux_data and not isinstance(flux_data, Mapping):
            raise ValueError("open_sea.flux section must be a mapping if provided.")
        flux_data = flux_data or {}
        count_modes_raw = flux_data.get("count_modes", ("gate_hits", "paired_transits"))
        if isinstance(count_modes_raw, (list, tuple)):
            count_modes = tuple(str(item) for item in count_modes_raw if str(item).strip())
        else:
            count_modes = (str(count_modes_raw),)
        rehit_overrides_raw = flux_data.get("rehit_hours_by_group", {}) or {}
        if not isinstance(rehit_overrides_raw, Mapping):
            raise ValueError("open_sea.flux.rehit_hours_by_group must be a mapping if provided.")
        rehit_overrides = {str(key): float(value) for key, value in rehit_overrides_raw.items()}
        flux_cfg = GateFluxConfig(
            count_modes=count_modes if count_modes else ("gate_hits",),
            tanker_only=bool(flux_data.get("tanker_only", True)),
            sog_min_kn=float(flux_data.get("sog_min_kn", 0.0)),
            rehit_hours_default=float(flux_data.get("rehit_hours", 6.0)),
            rehit_hours_by_group=rehit_overrides,
        )
        return cls(
            downsample_secs=int(data.get("downsample_secs", 60)),
            hysteresis_hits=int(data.get("hysteresis_hits", 2)),
            ttl_min=ttl_cfg,
            sog_thresholds=sog_cfg,
            gates=gate_cfg,
            cmems=cmems_cfg,
            sis=sis_cfg,
            flux=flux_cfg,
        )


def get_open_sea_config(config_path: str | None = None) -> OpenSeaConfig:
    """Load global config and return the open_sea section."""
    raw_cfg = load_config(config_path or "config.yml")
    open_sea_cfg = raw_cfg.get("open_sea")
    if not isinstance(open_sea_cfg, Mapping):
        raise KeyError("open_sea section missing in configuration.")
    return OpenSeaConfig.from_mapping(open_sea_cfg)
