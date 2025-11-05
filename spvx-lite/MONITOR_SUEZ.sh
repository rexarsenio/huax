#!/bin/bash
# Real-time Suez Consumer Monitor

cd "$(dirname "$0")"
source .venv/bin/activate

echo "🔍 SUEZ CONSUMER REAL-TIME MONITOR"
echo "=================================="
echo ""

# Check process
if [ -f logs/suez_consumer.pid ]; then
    PID=$(cat logs/suez_consumer.pid)
    if ps -p $PID > /dev/null 2>&1; then
        ELAPSED=$(ps -p $PID -o etime= | tr -d ' ')
        echo "✅ Consumer Running: PID $PID (uptime: $ELAPSED)"
    else
        echo "❌ Consumer NOT running (PID $PID dead)"
    fi
else
    echo "❌ No PID file found"
fi

echo ""
echo "📊 Database Statistics:"
echo "----------------------"

python3 << 'PYTHON'
import duckdb
from datetime import datetime

try:
    con = duckdb.connect("db/spvx.duckdb", read_only=True)
    
    # Check tables
    ais_tables = ['gate_crossings', 'polygon_events', 'ais_positions']
    
    for table in ais_tables:
        try:
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            
            if count > 0:
                # Get time range
                time_range = con.execute(f"""
                    SELECT 
                        MIN(ts)::VARCHAR as first,
                        MAX(ts)::VARCHAR as last
                    FROM {table}
                """).fetchone()
                
                print(f"✅ {table:20s}: {count:6,} rows")
                print(f"   First: {time_range[0][:19]}")
                print(f"   Last:  {time_range[1][:19]}")
                
                # Show recent activity
                if table == 'gate_crossings':
                    recent = con.execute(f"""
                        SELECT gate_id, COUNT(*) as cnt
                        FROM {table}
                        WHERE ts >= NOW() - INTERVAL '1 hour'
                        GROUP BY gate_id
                        ORDER BY cnt DESC
                        LIMIT 5
                    """).fetchall()
                    
                    if recent:
                        print(f"   Recent gate activity (last hour):")
                        for gate, cnt in recent:
                            print(f"     - {gate}: {cnt} crossings")
            else:
                print(f"⏳ {table:20s}: 0 rows (waiting for data...)")
                
        except Exception as e:
            print(f"⏳ {table:20s}: Not created yet")
        
        print("")
    
    con.close()
    
except Exception as e:
    print(f"⚠️  Database: {e}")

PYTHON

echo ""
echo "📝 Recent Logs:"
echo "--------------"
tail -20 logs/suez_consumer.log | grep -v "│"

echo ""
echo "💡 Usage:"
echo "   watch -n 5 ./MONITOR_SUEZ.sh    # Auto-refresh every 5 seconds"
echo "   tail -f logs/suez_consumer.log  # Live log stream"
