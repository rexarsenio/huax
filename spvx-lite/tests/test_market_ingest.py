import duckdb

from spvx.open_market.ingest import ensure_tables, ingest_oil


def test_ingest_oil_mock(tmp_path):
    db_path = tmp_path / "test.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        ensure_tables(con)
        inserted = ingest_oil(con, since_days=30, use_mock=True)
        # Mock inserts 180 days * 2 series
        assert inserted == 360
        latest = con.execute("SELECT max(ds) FROM oil_daily").fetchone()[0]
        assert latest is not None
    finally:
        con.close()
