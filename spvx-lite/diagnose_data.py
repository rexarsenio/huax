#!/usr/bin/env python3
"""
Diagnose data freshness and identify what needs to be updated.
"""

import duckdb
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = "db/spvx.duckdb"

def check_table(con, table_name, ts_column, description):
    """Check data freshness for a table."""
    try:
        result = con.execute(f"""
            SELECT
                COUNT(*) as total,
                MIN({ts_column}) as earliest,
                MAX({ts_column}) as latest
            FROM {table_name}
        """).fetchone()

        if result and result[0] > 0:
            total, earliest, latest = result
            age = datetime.now() - latest.replace(tzinfo=None)

            status = "✅" if age < timedelta(hours=24) else "⚠️" if age < timedelta(days=3) else "❌"
            print(f"{status} {description}")
            print(f"   Total records: {total:,}")
            print(f"   Latest: {latest} ({age.days}d {age.seconds//3600}h ago)")
            print(f"   Range: {earliest} to {latest}")

            return age < timedelta(hours=24)
        else:
            print(f"❌ {description}")
            print(f"   No data in table {table_name}")
            return False

    except Exception as e:
        print(f"❌ {description}")
        print(f"   Error: {e}")
        return False

def main():
    if not Path(DB_PATH).exists():
        print(f"❌ Database not found: {DB_PATH}")
        return

    con = duckdb.connect(DB_PATH, read_only=True)

    print("🔍 SPVX Data Freshness Report")
    print("=" * 70)
    print()

    # Check each data source
    checks = []

    print("📡 AIS Data (Consumer)")
    print("-" * 70)
    checks.append(check_table(con, "open_sea_fixes", "ts", "Open Sea AIS Fixes"))
    print()

    print("🌊 Sea State Data (CMEMS)")
    print("-" * 70)

    # Check if sea_state_samples exists
    try:
        con.execute("SELECT 1 FROM sea_state_samples LIMIT 1").fetchone()
        checks.append(check_table(con, "sea_state_samples", "ts", "Sea State Samples (Waves/Currents)"))
    except:
        print("❌ Sea State Samples")
        print("   Table 'sea_state_samples' does not exist")
        print("   👉 Run: PYTHONPATH=src python -m spvx.cli ingest-sea-state")
        checks.append(False)

    print()

    print("📊 Aggregated Data")
    print("-" * 70)

    # Check SIS daily
    try:
        con.execute("SELECT 1 FROM sis_daily LIMIT 1").fetchone()
        checks.append(check_table(con, "sis_daily", "ds", "SIS Daily (Sea Impact Score)"))
    except:
        print("❌ SIS Daily")
        print("   Table 'sis_daily' does not exist")
        print("   👉 Run: PYTHONPATH=src python -m spvx.cli sea-state-join")
        checks.append(False)

    print()

    # Check gate flux
    try:
        result = con.execute("SELECT MAX(window_end) FROM gate_flux").fetchone()
        if result and result[0]:
            latest = result[0]
            age = datetime.now() - latest.replace(tzinfo=None)
            status = "✅" if age < timedelta(hours=2) else "⚠️"
            print(f"{status} Gate Flux")
            print(f"   Latest window: {latest} ({age.seconds//60}min ago)")
            checks.append(age < timedelta(hours=2))
        else:
            print("❌ Gate Flux - No data")
            checks.append(False)
    except:
        print("❌ Gate Flux - Table missing")
        checks.append(False)

    print()
    print("=" * 70)

    # Summary
    fresh_count = sum(checks)
    total_count = len(checks)

    print(f"\n📈 Summary: {fresh_count}/{total_count} data sources fresh")

    if fresh_count == total_count:
        print("✅ All data is up to date!")
    else:
        print("\n⚠️  Action Required:")
        print()
        print("1️⃣  Update Sea State data (if stale):")
        print("    cd ~/Desktop/huax/spvx-lite")
        print("    source .venv/bin/activate")
        print("    PYTHONPATH=src python -m spvx.cli ingest-sea-state --provider auto --lookback-days 3")
        print()
        print("2️⃣  Compute SIS aggregations:")
        print("    PYTHONPATH=src python -m spvx.cli sea-state-join")
        print()
        print("3️⃣  Update API snapshot:")
        print("    ./UPDATE_API_SNAPSHOT.sh")
        print()
        print("4️⃣  Restart dashboard to see fresh data")

    # Check API database
    print()
    print("🔄 API Snapshot Status")
    print("-" * 70)

    api_db = Path("db/spvx_api.duckdb")
    if api_db.exists():
        api_con = duckdb.connect(str(api_db), read_only=True)

        # Check when API DB was last updated
        stat = api_db.stat()
        mod_time = datetime.fromtimestamp(stat.st_mtime)
        age = datetime.now() - mod_time

        status = "✅" if age < timedelta(hours=1) else "⚠️"
        print(f"{status} API Database")
        print(f"   Last updated: {mod_time} ({age.seconds//60}min ago)")
        print(f"   Size: {stat.st_size / 1024 / 1024:.1f} MB")

        if age > timedelta(hours=1):
            print("   👉 API snapshot is stale - run ./UPDATE_API_SNAPSHOT.sh")

        api_con.close()
    else:
        print("❌ API Database missing")
        print("   👉 Run: ./UPDATE_API_SNAPSHOT.sh")

    con.close()

if __name__ == "__main__":
    main()
