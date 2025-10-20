"""
SPVX-Lite index computation from component features.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from spvx.config import load_config
from spvx.utils.runtime import make_run_meta, update_run_meta


def compute_spvx_lite(
    components_path: str | Path = "data/processed/components.parquet",
    output_path: str | Path = "data/outputs/spvx_lite.csv",
) -> Path:
    comps = pd.read_parquet(components_path)
    cfg = load_config()
    weights = cfg["index"]["weights"]
    columns = list(weights.keys())

    # Check for weather degradation mask
    from spvx.sea_state.fallback import should_use_degraded_index

    degraded_mode = should_use_degraded_index()

    # Optional components (e.g., sea state) - use zero if missing or degraded
    optional_components = ["SEA_HS_Z", "OPPOSING_CURRENT"]
    available_columns = []
    available_weights = []

    for col in columns:
        if col in comps.columns and not (degraded_mode and col in optional_components):
            available_columns.append(col)
            available_weights.append(weights[col])
        elif col in optional_components:
            # Optional component missing or degraded - skip it (don't fail)
            continue
        else:
            # Required component missing - fail
            raise KeyError(f"Missing required component: {col}")

    w = np.array(available_weights, dtype=float)
    z = comps[available_columns].to_numpy()
    score = (z * w).sum(axis=1) / w.sum()
    level = 100.0 * np.exp(score)

    result = comps[["date"]].copy()
    result["SPVX_LITE"] = np.round(level, 2)
    result["SPVX_LITE_CHG"] = result["SPVX_LITE"].diff()

    # Compute ex-weather variant (exclude weather components)
    weather_components = ["SEA_HS_Z", "OPPOSING_CURRENT"]
    core_columns = [c for c in available_columns if c not in weather_components]
    if core_columns:
        w_core = np.array([weights[c] for c in core_columns], dtype=float)
        z_core = comps[core_columns].to_numpy()
        score_core = (z_core * w_core).sum(axis=1) / w_core.sum()
        level_core = 100.0 * np.exp(score_core)
        result["SPVX_LITE_EX_WEATHER"] = np.round(level_core, 2)
    else:
        result["SPVX_LITE_EX_WEATHER"] = result["SPVX_LITE"]

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    staging = out_path.with_suffix(out_path.suffix + ".staging")
    result.to_csv(staging, index=False)
    staging.replace(out_path)

    data_hash = int(pd.util.hash_pandas_object(comps[available_columns], index=True).sum())
    meta = make_run_meta(
        data_hash=data_hash,
        extra={
            "rows": int(len(result)),
            "columns": available_columns,
            "output": str(out_path),
            "degraded_mode": degraded_mode,
            "weather_components_disabled": degraded_mode,
        },
    )
    update_run_meta("compute_index", meta)

    return out_path
