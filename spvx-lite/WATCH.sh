#!/bin/bash
#
# WATCH.sh - Continuous monitoring with auto-refresh
#
# Updates every 5 seconds to show real-time data ingestion
#

while true; do
    ./MONITOR.sh
    sleep 5
done
