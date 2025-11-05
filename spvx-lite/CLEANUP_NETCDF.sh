#!/bin/bash
# Auto-Cleanup Script for NetCDF files
# Keeps only the 2 newest files in each directory to save disk space

cd /Users/alongo/Desktop/huax/spvx-lite

echo "🧹 NetCDF Auto-Cleanup"
echo "====================="
echo ""

# Function to cleanup a directory
cleanup_dir() {
    DIR=$1
    NAME=$2

    if [ ! -d "$DIR" ]; then
        echo "⚠️  $NAME: Directory not found, skipping"
        return
    fi

    cd "$DIR"
    FILE_COUNT=$(ls -1 *.nc 2>/dev/null | wc -l | tr -d ' ')

    if [ "$FILE_COUNT" -eq 0 ]; then
        echo "✓ $NAME: No NetCDF files"
        cd - > /dev/null
        return
    fi

    if [ "$FILE_COUNT" -le 2 ]; then
        echo "✓ $NAME: Only $FILE_COUNT files (keeping all)"
        cd - > /dev/null
        return
    fi

    # Calculate how many to delete
    TO_DELETE=$((FILE_COUNT - 2))

    # Get size before cleanup
    SIZE_BEFORE=$(du -sh . | awk '{print $1}')

    # Delete old files (keep newest 2)
    ls -t *.nc | tail -n +3 | xargs rm -f

    # Get size after cleanup
    SIZE_AFTER=$(du -sh . | awk '{print $1}')

    echo "✅ $NAME: Deleted $TO_DELETE old files ($SIZE_BEFORE → $SIZE_AFTER)"

    cd - > /dev/null
}

# Cleanup waves directory
cleanup_dir "data/sea_state/waves" "Waves"

# Cleanup currents directory
cleanup_dir "data/sea_state/currents" "Currents"

echo ""
echo "📊 Final disk usage:"
du -sh data/sea_state

echo ""
echo "✅ Cleanup complete!"
