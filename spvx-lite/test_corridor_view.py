#!/usr/bin/env python3
"""
Test the corridor_view endpoint with a mock snapshot database.
"""
import datetime as dt
import tempfile
from pathlib import Path

import duckdb


def create_test_snapshot():
    """Create a test snapshot database with polygon_events data."""
    # Create temporary database
    import os
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_snapshot.duckdb"

    con = duckdb.connect(str(db_path))

    # Create polygon_events table
    con.execute("""
        CREATE TABLE polygon_events (
            mmsi BIGINT,
            polygon_id TEXT,
            event TEXT,
            ts TIMESTAMP,
            lat DOUBLE,
            lon DOUBLE,
            sog DOUBLE,
            cog DOUBLE
        )
    """)

    # Insert test data for SINGAPORE (Malacca Strait)
    now = dt.datetime.utcnow()
    test_data = []

    # Singapore STS - 10 vessels in last 24h
    for i in range(10):
        mmsi = 200000000 + i
        ts = now - dt.timedelta(hours=i*2)
        test_data.append((mmsi, 'SINGAPORE_STS', 'enter', ts, 1.3, 103.8, 10.5, 180.0))

    # Singapore Jurong - 15 vessels in last 24h
    for i in range(15):
        mmsi = 300000000 + i
        ts = now - dt.timedelta(hours=i*1.5)
        test_data.append((mmsi, 'SINGAPORE_JURONG', 'enter', ts, 1.3, 103.7, 9.2, 270.0))

    # Rotterdam Oil - 8 vessels in last 24h
    for i in range(8):
        mmsi = 400000000 + i
        ts = now - dt.timedelta(hours=i*2.5)
        test_data.append((mmsi, 'ROTTERDAM_OIL', 'enter', ts, 51.9, 4.1, 8.0, 90.0))

    # Antwerp Oil - 5 vessels in last 24h
    for i in range(5):
        mmsi = 500000000 + i
        ts = now - dt.timedelta(hours=i*3)
        test_data.append((mmsi, 'ANTWERP_OIL', 'enter', ts, 51.3, 4.3, 7.5, 45.0))

    # Port Said Anchorage - 3 vessels in last 24h
    for i in range(3):
        mmsi = 600000000 + i
        ts = now - dt.timedelta(hours=i*6)
        test_data.append((mmsi, 'PORT_SAID_ANCHORAGE', 'enter', ts, 31.3, 32.3, 5.0, 135.0))

    con.executemany(
        "INSERT INTO polygon_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        test_data
    )

    con.close()
    return db_path


def test_corridor_view_with_fastapi():
    """Test corridor_view endpoint using FastAPI TestClient."""
    from fastapi.testclient import TestClient
    from spvx.api_app import app
    from spvx.config import AppSettings

    # Create test snapshot
    snapshot_path = create_test_snapshot()

    # Move it to the expected location
    settings = AppSettings()
    api_db_path = Path(settings.duckdb_path).parent / "spvx_api.duckdb"
    api_db_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy the test database to the API snapshot location
    import shutil
    shutil.copy(snapshot_path, api_db_path)

    try:
        # Test the endpoint
        client = TestClient(app)
        response = client.get("/api/open_sea/corridor_view?window=h24")

        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        assert len(data) > 0, "Should have at least one corridor"

        # Check that we have our expected corridors
        corridor_ids = {item['corridor_id'] for item in data}
        print(f"\nCorridor IDs found: {corridor_ids}")

        # Verify MALACCA_STRAIT (should have 25 vessels)
        malacca = next((c for c in data if c['corridor_id'] == 'MALACCA_STRAIT'), None)
        assert malacca is not None, "MALACCA_STRAIT should be present"
        print(f"\nMALACCA_STRAIT:")
        print(f"  flux_h: {malacca['flux_h']}")
        print(f"  flux_z: {malacca['flux_z']}")
        print(f"  delay_ratio: {malacca['delay_ratio']}")
        print(f"  sis_p90: {malacca['sis_p90']}")
        print(f"  as_of: {malacca['as_of']}")

        # Verify NORTH_SEA (should have 13 vessels)
        north_sea = next((c for c in data if c['corridor_id'] == 'NORTH_SEA'), None)
        assert north_sea is not None, "NORTH_SEA should be present"
        print(f"\nNORTH_SEA:")
        print(f"  flux_h: {north_sea['flux_h']}")
        print(f"  flux_z: {north_sea['flux_z']}")
        print(f"  delay_ratio: {north_sea['delay_ratio']}")
        print(f"  sis_p90: {north_sea['sis_p90']}")

        # Verify SUEZ_APPROACH (should have 3 vessels)
        suez = next((c for c in data if c['corridor_id'] == 'SUEZ_APPROACH'), None)
        assert suez is not None, "SUEZ_APPROACH should be present"
        print(f"\nSUEZ_APPROACH:")
        print(f"  flux_h: {suez['flux_h']}")
        print(f"  flux_z: {suez['flux_z']}")
        print(f"  delay_ratio: {suez['delay_ratio']}")
        print(f"  sis_p90: {suez['sis_p90']}")

        print("\n✅ All tests passed!")

    finally:
        # Cleanup
        snapshot_path.unlink(missing_ok=True)
        api_db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    test_corridor_view_with_fastapi()
