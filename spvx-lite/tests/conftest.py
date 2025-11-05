import os
import sys
from pathlib import Path

import duckdb
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if SRC_DIR.exists():
    src_str = str(SRC_DIR)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)

from spvx.db import ensure_core_tables
from spvx.etl import build_components_daily, compute_basin_indices
from spvx.sources import mock


@pytest.fixture(scope="module")
def prepared_db(tmp_path_factory):
    """
    Create a temporary DuckDB populated with mock data for integration tests.
    """
    temp_dir = tmp_path_factory.mktemp("spvx_basin")
    db_path = temp_dir / "spvx.duckdb"
    previous = os.environ.get("DUCKDB_PATH")
    os.environ["DUCKDB_PATH"] = str(db_path)
    try:
        mock.run(days=220)
        con = duckdb.connect(str(db_path))
        try:
            ensure_core_tables(con)
            build_components_daily(con)
            compute_basin_indices(con)
        finally:
            con.close()
        yield str(db_path)
    finally:
        if previous is None:
            os.environ.pop("DUCKDB_PATH", None)
        else:
            os.environ["DUCKDB_PATH"] = previous
