"""
Lightweight data contracts for key pipeline artifacts.
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa


ComponentsSchema = pa.DataFrameSchema(
    {
        "date": pa.Column(pa.DateTime, coerce=True),
        "CQ_TR": pa.Column(float, checks=[pa.Check.ge(-8), pa.Check.le(8)]),
        "CQ_SG": pa.Column(float, checks=[pa.Check.ge(-8), pa.Check.le(8)]),
        "PORT_EU": pa.Column(float, checks=[pa.Check.ge(-8), pa.Check.le(8)]),
        "CQ_SG_AIS": pa.Column(float, nullable=True),
        "CQ_SUEZ": pa.Column(float, nullable=True),
        "CQ_BOSPORUS": pa.Column(float, nullable=True),
        "CQ_HORMUZ": pa.Column(float, nullable=True),
        "CQ_CHOKE": pa.Column(float, nullable=True),
        "SEA_HS_Z": pa.Column(float, nullable=True),
        "OPPOSING_CURRENT": pa.Column(float, nullable=True),
    },
    coerce=True,
    strict=True,
)


def validate_components(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate component feature matrix prior to publishing.
    """
    validated = ComponentsSchema.validate(df, lazy=True)
    index = validated.set_index("date").index
    if not index.is_monotonic_increasing:
        raise ValueError("Component dates must be strictly increasing.")

    # Allow short bootstrap windows (<120 days) to pass even if variance is low.
    if len(validated) >= 120:
        core_cols = [col for col in ["CQ_TR", "CQ_SG", "PORT_EU"] if col in validated.columns]
        rolling_std = validated[core_cols].rolling(window=30, min_periods=10).std()
        stagnant = [col for col in core_cols if float(rolling_std[col].dropna().max()) == 0.0]
        if stagnant:
            cols = ", ".join(stagnant)
            raise ValueError(f"No variation detected in component series: {cols}.")

    return validated
