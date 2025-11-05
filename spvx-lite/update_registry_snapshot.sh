#!/bin/bash

# Update API Database Snapshot
# Copies the current production database to the API snapshot
# Run this periodically (e.g., via cron every 5 minutes) to keep the dashboard updated

cd "$(dirname "$0")"

echo "📸 Updating API database snapshot..."

# Stop briefly to ensure clean copy
if [ -f "db/spvx_api.duckdb" ]; then
    rm db/spvx_api.duckdb
fi

# Copy current production DB
cp db/spvx.duckdb db/spvx_api.duckdb

if [ $? -eq 0 ]; then
    SIZE=$(du -h db/spvx_api.duckdb | cut -f1)
    echo "✓ Snapshot updated successfully (${SIZE})"
    echo "  Timestamp: $(date)"
else
    echo "✗ Failed to update snapshot"
    exit 1
fi
