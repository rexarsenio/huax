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
    CREATE TABLE IF NOT EXISTS open_sea_fixes (
        mmsi BIGINT,
        ts TIMESTAMP,
        lat DOUBLE,
        lon DOUBLE,
        sog DOUBLE,
        cog DOUBLE,
        shiptype_num INTEGER,
        is_tanker BOOLEAN,
        PRIMARY KEY (mmsi, ts)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS polygon_events (
        mmsi BIGINT,
        polygon_id TEXT,
        event TEXT CHECK (event IN ('enter','exit')),
        ts TIMESTAMP,
        lat DOUBLE,
        lon DOUBLE,
        sog DOUBLE,
        cog DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tanker_presence (
        mmsi BIGINT,
        polygon_id TEXT,
        enter_ts TIMESTAMP,
        exit_ts TIMESTAMP,
        last_seen_ts TIMESTAMP,
        inside BOOLEAN,
        samples_inside INTEGER,
        sog_min DOUBLE,
        sog_max DOUBLE,
        sog_avg DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gate_crossings (
        mmsi BIGINT,
        gate_id TEXT,
        ts TIMESTAMP,
        direction TEXT CHECK (direction IN ('AtoB','BtoA')),
        lat DOUBLE,
        lon DOUBLE,
        sog DOUBLE,
        cog DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tracklets (
        tracklet_id TEXT,
        mmsi BIGINT,
        start_ts TIMESTAMP,
        end_ts TIMESTAMP,
        n_points INTEGER,
        mean_cog DOUBLE,
        mean_sog DOUBLE,
        poly_from_id TEXT,
        poly_to_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sea_state_samples (
        tracklet_id TEXT,
        ts TIMESTAMP,
        lat DOUBLE,
        lon DOUBLE,
        hs DOUBLE,
        u10 DOUBLE,
        v10 DOUBLE,
        uo DOUBLE,
        vo DOUBLE,
        sst_anom DOUBLE,
        head_current_kn DOUBLE,
        head_wind_ms DOUBLE,
        wave_encounter_m DOUBLE
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
    CREATE TABLE IF NOT EXISTS turkish_events (
        ts TIMESTAMP PRIMARY KEY,
        closure_minutes DOUBLE,
        wait_hours DOUBLE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tanker_occupancy_intraday (
        ts TIMESTAMP,
        polygon_id TEXT,
        count_now INTEGER,
        PRIMARY KEY (ts, polygon_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tanker_entries_daily (
        ds DATE,
        polygon_id TEXT,
        entries INTEGER,
        PRIMARY KEY (ds, polygon_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tanker_dwell_daily (
        ds DATE,
        polygon_id TEXT,
        dwell_p50_min DOUBLE,
        dwell_p90_min DOUBLE,
        n INTEGER,
        PRIMARY KEY (ds, polygon_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gate_flux_hourly (
        ts TIMESTAMP,
        gate_id TEXT,
        direction TEXT,
        crossings INTEGER,
        PRIMARY KEY (ts, gate_id, direction)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gate_flux_daily (
        ds DATE,
        gate_id TEXT,
        direction TEXT,
        crossings INTEGER,
        PRIMARY KEY (ds, gate_id, direction)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gate_flux_rolling (
        window_label TEXT,
        gate_id TEXT,
        direction TEXT,
        end_ts TIMESTAMP,
        crossings INTEGER,
        PRIMARY KEY (window_label, gate_id, direction, end_ts)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transit_times_daily (
        ds DATE,
        corridor_id TEXT,
        from_id TEXT,
        to_id TEXT,
        median_h DOUBLE,
        mean_h DOUBLE,
        p90_h DOUBLE,
        n INTEGER,
        PRIMARY KEY (ds, corridor_id, from_id, to_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sea_state_daily (
        ds DATE,
        corridor_id TEXT,
        sis_mean DOUBLE,
        sis_p90 DOUBLE,
        pct_sis_gt_0_7 DOUBLE,
        hc_p90_kn DOUBLE,
        hw_p90_ms DOUBLE,
        we_p90_m DOUBLE,
        n_samples INTEGER,
        PRIMARY KEY (ds, corridor_id)
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
        sea_hs_z DOUBLE DEFAULT 0,
        sea_opp_current DOUBLE DEFAULT 0,
        sea_data_timestamp TIMESTAMP,
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
        sea_hs_z_avg DOUBLE DEFAULT 0,
        sea_data_timestamp TIMESTAMP,
        PRIMARY KEY (d, basin)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spvx_global_daily (
        d DATE PRIMARY KEY,
        spvx_global DOUBLE,
        basins_present INTEGER,
        weather_flag INTEGER DEFAULT 0,
        sea_hs_z_avg DOUBLE DEFAULT 0,
        sea_data_timestamp TIMESTAMP
    )
    """,
    """
    ALTER TABLE components_daily ADD COLUMN IF NOT EXISTS weather_flag INTEGER DEFAULT 0
    """,
    """
    ALTER TABLE components_daily ADD COLUMN IF NOT EXISTS sea_hs_z DOUBLE DEFAULT 0
    """,
    """
    ALTER TABLE components_daily ADD COLUMN IF NOT EXISTS sea_opp_current DOUBLE DEFAULT 0
    """,
    """
    ALTER TABLE components_daily ADD COLUMN IF NOT EXISTS sea_data_timestamp TIMESTAMP
    """,
    """
    ALTER TABLE spvx_basin_daily ADD COLUMN IF NOT EXISTS weather_flag INTEGER DEFAULT 0
    """,
    """
    ALTER TABLE spvx_basin_daily ADD COLUMN IF NOT EXISTS sea_hs_z_avg DOUBLE DEFAULT 0
    """,
    """
    ALTER TABLE spvx_basin_daily ADD COLUMN IF NOT EXISTS sea_data_timestamp TIMESTAMP
    """,
    """
    ALTER TABLE spvx_global_daily ADD COLUMN IF NOT EXISTS weather_flag INTEGER DEFAULT 0
    """,
    """
    ALTER TABLE spvx_global_daily ADD COLUMN IF NOT EXISTS sea_hs_z_avg DOUBLE DEFAULT 0
    """,
    """
    ALTER TABLE spvx_global_daily ADD COLUMN IF NOT EXISTS sea_data_timestamp TIMESTAMP
    """,
)


def ensure_core_tables(con: duckdb.DuckDBPyConnection) -> None:
    """
    Create core SPVX-Lite tables if they do not exist.
    """
    for ddl in DDL_STATEMENTS:
        con.execute(ddl)
    LOG.debug("Ensured core DuckDB tables are present.")
