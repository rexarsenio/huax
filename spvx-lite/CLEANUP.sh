#!/bin/bash
#
# CLEANUP.sh - Automatic disk space cleanup
#
# Removes old sea state files to prevent "No space left on device" errors
# Run this periodically (e.g., daily) to keep disk usage manageable
#

cd "$(dirname "$0")"

echo "🧹 SPVX-Lite Disk Cleanup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check current disk usage
echo "📊 Current disk usage:"
df -h / | tail -1
echo ""

# Clean up old sea state files (older than 7 days - keep recent data!)
echo "🗑️  Removing old sea state files (older than 7 days)..."
BEFORE=$(du -sh data/ 2>/dev/null | cut -f1)
echo "   Before: $BEFORE"

cd data/sea_state 2>/dev/null
if [ -d "." ]; then
    # Count files before deletion
    OLD_COUNT=$(find . -name "*.nc" -mtime +7 | wc -l | tr -d ' ')
    TEMP_COUNT=$(find . -name "*.nc.E*" | wc -l | tr -d ' ')
    RECENT_COUNT=$(find . -name "*.nc" -mtime -7 | wc -l | tr -d ' ')

    echo "   Current: $RECENT_COUNT recent files (≤7 days)"
    echo "   Old: $OLD_COUNT files (>7 days)"
    echo "   Temp: $TEMP_COUNT incomplete downloads"

    if [ "$OLD_COUNT" -gt 0 ] || [ "$TEMP_COUNT" -gt 0 ]; then
        # Delete old files (keeping last 7 days for SIS calculations)
        find . -name "*.nc" -mtime +7 -delete
        find . -name "*.nc.E*" -delete

        echo "   ✅ Deleted $(($OLD_COUNT + $TEMP_COUNT)) files"
        echo "   ℹ️  Kept $RECENT_COUNT recent files for Sea-State Index"
    else
        echo "   ℹ️  No old files to delete"
    fi
fi
cd ../..

AFTER=$(du -sh data/ 2>/dev/null | cut -f1)
echo "   After:  $AFTER"
echo ""

# Clean up old log files (keep last 7 days)
echo "🗑️  Cleaning up old log files..."
cd logs 2>/dev/null
if [ -d "." ]; then
    find . -name "*.log" -mtime +7 -exec rm {} \;
    echo "   ✅ Removed logs older than 7 days"
fi
cd ..

# Clean up Python cache
echo "🗑️  Cleaning Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null
echo "   ✅ Removed __pycache__ directories"

echo ""
echo "📊 Final disk usage:"
df -h / | tail -1
echo ""
echo "✅ Cleanup complete!"
