"""
DuckDB schema management for SPVX-Lite basin indices.
"""

from __future__ import annotations

import logging
from typing import Iterable

import duckdb

LOG = logging.getLogger(__name__)

DDL_STATEMENTS: Iterable[str] = (
    """
    CREATE TABLE IF NOT EXISTS ais_raw (
        ts TIMESTAMP,
        mmsi BIGINT,
        lat DOUBLE,
        lon DOUBLE,
        sog DOUBLE,
        cog DOUBLE,
        shiptype INTEGER,
        region TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dwell_10m (
        window_start TIMESTAMP,
        region TEXT,
        slow_count INTEGER,
        PRIMARY KEY (window_start, region)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS portwatch_daily (
        d DATE,
        portname TEXT,
        port_code TEXT,
        iso3 TEXT,
        shiptype TEXT DEFAULT 'tanker',
        departures DOUBLE,
        arrivals DOUBLE,
        movements DOUBLE,
        source TEXT DEFAULT 'portwatch',
        PRIMARY KEY (d, port_code, shiptype, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS portstays_snapshots (
        snapshot_ts TIMESTAMP,
        request_date TIMESTAMP,
        payload TEXT,
        PRIMARY KEY (snapshot_ts, request_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS portstays_daily (
        d DATE,
        port_code TEXT,
        port_name TEXT,
        tanker_departures INTEGER,
        tanker_arrivals INTEGER,
        source TEXT DEFAULT 'portstays_uat',
        snapshot_ts TIMESTAMP,
        PRIMARY KEY (d, port_code, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS weather_observations (
        observed_at TIMESTAMP,
        region TEXT,
        basin TEXT,
        wind_speed_kn DOUBLE,
        wind_gust_kn DOUBLE,
        wave_height_m DOUBLE,
        weather_flag INTEGER,
        source TEXT DEFAULT 'openweather',
        raw_payload TEXT,
        PRIMARY KEY (observed_at, region, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sea_currents_daily (
        observed_at TIMESTAMP,
        region TEXT,
        basin TEXT,
        u_knots DOUBLE,
        v_knots DOUBLE,
        speed_knots DOUBLE,
        weather_flag INTEGER,
        source TEXT,
        PRIMARY KEY (observed_at, region, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sea_waves_daily (
        observed_at TIMESTAMP,
        region TEXT,
        basin TEXT,
        hs_m DOUBLE,
        tp_s DOUBLE,
        dp_deg DOUBLE,
        weather_flag INTEGER,
        source TEXT,
        PRIMARY KEY (observed_at, region, source)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS components_daily (
        d DATE,
        basin TEXT,
        comp TEXT,
        z_value DOUBLE,
        raw_value DOUBLE,
        n_obs INTEGER,
        missing_reason TEXT,
        weather_flag INTEGER DEFAULT 0,
        PRIMARY KEY (d, basin, comp)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS component_inputs_daily (
        d DATE,
        key TEXT,
        raw_value DOUBLE,
        n_obs INTEGER,
        PRIMARY KEY (d, key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS baselines_doy (
        key TEXT,
        doy INTEGER,
        mean DOUBLE,
        std DOUBLE,
        PRIMARY KEY (key, doy)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spvx_basin_daily (
        d DATE,
        basin TEXT,
        spvx_basin DOUBLE,
        comps_present INTEGER,
        weather_flag INTEGER DEFAULT 0,
        PRIMARY KEY (d, basin)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spvx_global_daily (
        d DATE PRIMARY KEY,
        spvx_global DOUBLE,
        basins_present INTEGER,
        weather_flag INTEGER DEFAULT 0
    )
    """,
    """
    ALTER TABLE components_daily ADD COLUMN IF NOT EXISTS weather_flag INTEGER DEFAULT 0
    """,
    """
    ALTER TABLE spvx_basin_daily ADD COLUMN IF NOT EXISTS weather_flag INTEGER DEFAULT 0
    """,
    """
    ALTER TABLE spvx_global_daily ADD COLUMN IF NOT EXISTS weather_flag INTEGER DEFAULT 0
    """,
)


def ensure_core_tables(con: duckdb.DuckDBPyConnection) -> None:
    """
    Create core SPVX-Lite tables if they do not exist.
    """
    for ddl in DDL_STATEMENTS:
        con.execute(ddl)
    LOG.debug("Ensured core DuckDB tables are present.")
