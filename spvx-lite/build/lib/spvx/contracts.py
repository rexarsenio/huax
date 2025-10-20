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

    rolling_std = validated[["CQ_TR", "CQ_SG", "PORT_EU"]].rolling(window=30, min_periods=10).std()
    if (rolling_std.dropna() == 0).any().any():
        raise ValueError("Zero-variance window detected in component series.")

    return validated
