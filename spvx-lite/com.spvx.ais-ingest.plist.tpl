<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.spvx.ais-ingest</string>

    <key>ProgramArguments</key>
    <array>
        <string>@@PYTHON@@</string>
        <string>-u</string>
        <string>@@ROOT@@/ingest_aisstream.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>@@ROOT@@</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>@@PATH@@</string>
        <key>TZ</key>
        <string>@@TZ@@</string>
        <key>AGGREGATION_INTERVAL_SECONDS</key>
        <string>@@AGG_INTERVAL@@</string>
        <key>SPVX_METRICS_PORT</key>
        <string>@@METRICS_PORT@@</string>
        <key>SPVX_HEALTH_PORT</key>
        <string>@@HEALTH_PORT@@</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>10</integer>

    <key>StandardOutPath</key>
    <string>@@ROOT@@/logs/ais-ingest.log</string>

    <key>StandardErrorPath</key>
    <string>@@ROOT@@/logs/ais-ingest.error.log</string>
</dict>
</plist>
