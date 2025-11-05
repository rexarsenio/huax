"""
Index aggregation utilities for basin and global SPVX outputs.
"""

from __future__ import annotations

import logging
from typing import Tuple

import duckdb

from spvx.db import ensure_core_tables

LOG = logging.getLogger(__name__)


def compute_basin_indices(con: duckdb.DuckDBPyConnection) -> Tuple[int, int]:
    """
    Materialise basin-level indices and global composite.

    Returns:
        Tuple of (basin_rows, global_rows) upserted.
    """
    ensure_core_tables(con)

    basin_rows = con.execute(
        """
        INSERT INTO spvx_basin_daily (
            d,
            basin,
            spvx_basin,
            comps_present,
            weather_flag,
            sea_hs_z_avg,
            sea_data_timestamp
        )
        SELECT
            d,
            basin,
            100 * exp(AVG(z_value)) AS spvx_basin,
            COUNT(*) AS comps_present,
            MAX(weather_flag) AS weather_flag,
            AVG(sea_hs_z) AS sea_hs_z_avg,
            MAX(sea_data_timestamp) AS sea_data_timestamp
        FROM components_daily
        WHERE z_value IS NOT NULL
        GROUP BY d, basin
        ON CONFLICT (d, basin) DO UPDATE SET
            spvx_basin = excluded.spvx_basin,
            comps_present = excluded.comps_present,
            weather_flag = excluded.weather_flag,
            sea_hs_z_avg = excluded.sea_hs_z_avg,
            sea_data_timestamp = excluded.sea_data_timestamp
        RETURNING 1
        """
    ).fetchall()

    global_rows = con.execute(
        """
        INSERT INTO spvx_global_daily (
            d,
            spvx_global,
            basins_present,
            weather_flag,
            sea_hs_z_avg,
            sea_data_timestamp
        )
        SELECT
            d,
            100 * exp(AVG(ln(spvx_basin / 100.0))) AS spvx_global,
            COUNT(*) AS basins_present,
            MAX(weather_flag) AS weather_flag,
            AVG(sea_hs_z_avg) AS sea_hs_z_avg,
            MAX(sea_data_timestamp) AS sea_data_timestamp
        FROM spvx_basin_daily
        WHERE spvx_basin IS NOT NULL
          AND spvx_basin > 0
          AND comps_present >= 1
        GROUP BY d
        ON CONFLICT (d) DO UPDATE SET
            spvx_global = excluded.spvx_global,
            basins_present = excluded.basins_present,
            weather_flag = excluded.weather_flag,
            sea_hs_z_avg = excluded.sea_hs_z_avg,
            sea_data_timestamp = excluded.sea_data_timestamp
        RETURNING 1
        """
    ).fetchall()

    LOG.info(
        "Updated %s basin rows and %s global rows.",
        len(basin_rows),
        len(global_rows),
    )
    return len(basin_rows), len(global_rows)
