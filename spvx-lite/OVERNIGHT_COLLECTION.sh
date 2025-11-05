#!/bin/bash
#
# OVERNIGHT_COLLECTION.sh
# Sammelt über Nacht AIS-Daten und verarbeitet sie regelmäßig
#

cd "$(dirname "$0")"
source .venv/bin/activate

LOG_DIR="logs/overnight"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/overnight_${TIMESTAMP}.log"

echo "========================================" | tee -a "$LOG_FILE"
echo "🌙 OVERNIGHT DATA COLLECTION STARTED" | tee -a "$LOG_FILE"
echo "Started: $(date)" | tee -a "$LOG_FILE"
echo "Log: $LOG_FILE" | tee -a "$LOG_FILE"
echo "========================================" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

# Check prerequisites
echo "📋 Checking prerequisites..." | tee -a "$LOG_FILE"

# Check if consumer is running
if pgrep -f "python -m spvx.cli ingest-ais" > /dev/null; then
    echo "✅ AIS Consumer is running" | tee -a "$LOG_FILE"
else
    echo "⚠️  AIS Consumer not running - starting it..." | tee -a "$LOG_FILE"
    ./start_consumer.sh >> "$LOG_FILE" 2>&1
    sleep 5
fi

# Check if API is running
if pgrep -f "uvicorn spvx.api_app" > /dev/null; then
    echo "✅ API Server is running" | tee -a "$LOG_FILE"
else
    echo "⚠️  API Server not running - skipping (optional)" | tee -a "$LOG_FILE"
fi

echo "" | tee -a "$LOG_FILE"

# Function to log with timestamp
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to check database stats
check_stats() {
    log "📊 Database Statistics:"
    python << EOF | tee -a "$LOG_FILE"
import duckdb
con = duckdb.connect("db/spvx.duckdb", read_only=True)

# AIS Fixes
fixes = con.execute("SELECT COUNT(*) FROM open_sea_fixes").fetchone()[0]
print(f"  AIS Fixes:        {fixes:,}")

# Polygon Events
events = con.execute("SELECT COUNT(*) FROM polygon_events").fetchone()[0]
enters = con.execute("SELECT COUNT(*) FROM polygon_events WHERE event='enter'").fetchone()[0]
exits = con.execute("SELECT COUNT(*) FROM polygon_events WHERE event='exit'").fetchone()[0]
print(f"  Polygon Events:   {events:,} ({enters:,} enter, {exits:,} exit)")

# Tracklets
tracklets = con.execute("SELECT COUNT(*) FROM tracklets WHERE tracklet_id < 1000000").fetchone()[0]
print(f"  Tracklets:        {tracklets:,}")

# Sea State Samples
samples = con.execute("SELECT COUNT(*) FROM sea_state_samples").fetchone()[0]
print(f"  Sea State Samples: {samples:,}")

# Occupancy
try:
    occ = con.execute("SELECT polygon_id, count_now FROM tanker_occupancy_intraday ORDER BY count_now DESC LIMIT 3").fetchall()
    if occ:
        print("  Top Occupancy:")
        for poly, count in occ:
            print(f"    {poly}: {count}")
except:
    pass

con.close()
EOF
    log ""
}

# Initial stats
check_stats

# Main loop: Run every 2 hours for 12 hours (6 iterations)
log "🔄 Starting overnight collection loop (every 2 hours)..."
log "Will run until: $(date -v+12H +'%Y-%m-%d %H:%M:%S')"
log ""

for i in {1..6}; do
    log "========================================"
    log "🔄 Iteration $i/6"
    log "========================================"

    # Step 1: Generate tracklets from new polygon events
    log "Step 1: Generating tracklets..."
    python generate_tracklets_from_events.py >> "$LOG_FILE" 2>&1
    TRACKLETS_EXIT=$?
    if [ $TRACKLETS_EXIT -eq 0 ]; then
        log "✅ Tracklets generated successfully"
    else
        log "❌ Tracklets generation failed (exit code: $TRACKLETS_EXIT)"
    fi

    # Step 2: Join with CMEMS data (process all tracklets from last 24h)
    log "Step 2: Joining tracklets with CMEMS data..."
    python join_tracklets_cmems_fast.py >> "$LOG_FILE" 2>&1
    JOIN_EXIT=$?
    if [ $JOIN_EXIT -eq 0 ]; then
        log "✅ CMEMS join completed successfully"
    else
        log "❌ CMEMS join failed (exit code: $JOIN_EXIT)"
    fi

    # Step 3: Compute SIS scores
    log "Step 3: Computing SIS scores..."
    python -m spvx.cli sea-state-join >> "$LOG_FILE" 2>&1
    SIS_EXIT=$?
    if [ $SIS_EXIT -eq 0 ]; then
        log "✅ SIS scores computed successfully"
    else
        log "❌ SIS computation failed (exit code: $SIS_EXIT)"
    fi

    # Step 4: Update API snapshot
    log "Step 4: Updating API snapshot..."
    ./UPDATE_API_SNAPSHOT.sh >> "$LOG_FILE" 2>&1
    API_EXIT=$?
    if [ $API_EXIT -eq 0 ]; then
        log "✅ API snapshot updated successfully"
    else
        log "❌ API snapshot update failed (exit code: $API_EXIT)"
    fi

    # Show current stats
    log ""
    check_stats

    # Wait 2 hours before next iteration (unless last iteration)
    if [ $i -lt 6 ]; then
        log "💤 Sleeping for 2 hours until next iteration..."
        log "Next run: $(date -v+2H +'%Y-%m-%d %H:%M:%S')"
        log ""
        sleep 7200  # 2 hours = 7200 seconds
    fi
done

log "========================================"
log "🌅 OVERNIGHT COLLECTION COMPLETED"
log "Finished: $(date)"
log "========================================"
log ""

# Final summary
log "📈 FINAL SUMMARY:"
check_stats

log ""
log "✅ Done! Check full log at: $LOG_FILE"
