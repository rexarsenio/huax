"""
Persistence helpers for day-of-year baselines used in basin Z-score
standardisation.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Iterable, Sequence, Tuple

import duckdb
import numpy as np
import pandas as pd

LOG = logging.getLogger(__name__)


def _as_native(value: float | None) -> float | None:
    if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
        return None
    return float(value)


def refresh_doy_baselines(
    con: duckdb.DuckDBPyConnection,
    *,
    lookback_days: int = 400,
    min_history_days: int = 180,
) -> int:
    """
    Recompute seasonal baselines for every component/basin combination.

    Returns the number of rows written to `baselines_doy`.
    """
    df = con.execute(
        """
        SELECT d, key, raw_value
        FROM component_inputs_daily
        WHERE raw_value IS NOT NULL
        """
    ).df()

    if df.empty:
        LOG.info("No component history available; skipping baseline refresh.")
        return 0

    df["d"] = pd.to_datetime(df["d"])
    max_date: dt.datetime = df["d"].max()
    min_cutoff = max_date - dt.timedelta(days=lookback_days)
    df = df[df["d"] >= min_cutoff]

    span_days = (df["d"].max() - df["d"].min()).days + 1
    if span_days < min_history_days:
        LOG.warning(
            "Baseline refresh has only %s days (min required %s). Proceeding but mark output tentative.",
            span_days,
            min_history_days,
        )

    df["key"] = df["key"].astype(str)
    df["doy"] = df["d"].dt.dayofyear

    grouped = (
        df.groupby(["key", "doy"])["raw_value"]
        .agg(
            mean="mean",
            std="std",
            n="count",
        )
        .reset_index()
    )

    if grouped.empty:
        LOG.info("After filtering, no baseline rows produced.")
        return 0

    grouped.loc[grouped["n"] < 2, "std"] = np.nan
    grouped.loc[grouped["std"].abs() < 1e-6, "std"] = np.nan

    rows: Sequence[Tuple[str, int, float | None, float | None]] = [
        (
            str(row.key),
            int(row.doy),
            _as_native(row.mean),
            _as_native(row.std),
        )
        for row in grouped.itertuples(index=False)
    ]

    keys: Iterable[Tuple[str]] = [(row[0],) for row in rows]
    if rows:
        con.execute("BEGIN")
        try:
            con.executemany("DELETE FROM baselines_doy WHERE key = ?", keys)  # type: ignore[arg-type]
            con.executemany(
                """
                INSERT INTO baselines_doy (key, doy, mean, std)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )
        except Exception:
            con.execute("ROLLBACK")
            raise
        else:
            con.execute("COMMIT")

    LOG.info("Refreshed %s baseline rows across %s keys.", len(rows), grouped["key"].nunique())
    return len(rows)
