#!/usr/bin/env python3
"""
Migration script to add ship_registry table to existing database.

This script safely adds the ship_registry table to the database without
affecting existing data.
"""

import logging
from pathlib import Path

import duckdb

from spvx.ingest.ship_registry import create_ship_registry_table

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
LOG = logging.getLogger(__name__)


def main():
    db_path = Path("db/spvx.duckdb")

    if not db_path.exists():
        LOG.error(f"Database not found: {db_path}")
        return 1

    LOG.info(f"Connecting to {db_path}...")
    con = duckdb.connect(str(db_path))

    # Check if table already exists
    existing_tables = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()
    table_names = [t[0] for t in existing_tables]

    LOG.info(f"Found {len(table_names)} existing tables: {', '.join(table_names)}")

    if "ship_registry" in table_names:
        LOG.info("ship_registry table already exists")
        row_count = con.execute("SELECT COUNT(*) FROM ship_registry").fetchone()[0]
        LOG.info(f"  Current size: {row_count:,} vessels")
    else:
        LOG.info("Creating ship_registry table...")
        create_ship_registry_table(con)
        LOG.info("✓ ship_registry table created successfully")

    # Verify schema
    schema = con.execute("DESCRIBE ship_registry").fetchall()
    LOG.info("ship_registry schema:")
    for col in schema:
        LOG.info(f"  {col[0]:20} {col[1]}")

    con.close()
    LOG.info("Migration complete!")
    return 0


if __name__ == "__main__":
    exit(main())
