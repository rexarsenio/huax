# PortStays Ingestion (UAT)

This module connects the Huax SPVX-Lite stack to the NxtPort PortStays API. It covers credential loading, OAuth2 token management, rate limiting, and DuckDB persistence so Antwerp/Zeebrugge departures can feed the `PORT_EU` component.

## 1. Credentials & Environment

Add the following to your `.env` (never commit secrets):

```env
NXTPORT_SUBSCRIPTION_KEY=xxxxxxxxxxxxxxxx
NXTPORT_CLIENT_ID=xxxxxxxxxxxxxxxx
NXTPORT_CLIENT_SECRET=xxxxxxxxxxxxxxxx
# Password grant (recommended in UAT)
NXTPORT_USERNAME=you@example.com
NXTPORT_PASSWORD=supersecret
NXTPORT_GRANT_TYPE=password
NXTPORT_SCOPE=openid               # optional; leave blank when not required
# Optional overrides
# NXTPORT_TOKEN_URL=https://login-uat.nxtport.com/connect/token
# NXTPORT_API_BASE=https://api-uat.nxtport.com/portstays/v1
# NXTPORT_USER_AGENT=spvx-lite/uat (email@example.com)
```

- **UAT defaults:** token endpoint `https://login-uat.nxtport.com/connect/token`, API base `https://api-uat.nxtport.com/portstays/v1`.
- Override `NXTPORT_TOKEN_URL`/`NXTPORT_API_BASE` for production cut-over.
- Tokens are cached for ~58 minutes (120 s safety margin) to respect 60 min expiry.

## 2. Manual Snapshot (CLI)

Fetch a snapshot for the current UTC time:

```bash
python -m spvx.cli ingest-portstays
```

Provide a specific timestamp (ISO-8601 UTC) for historical backfills:

```bash
python -m spvx.cli ingest-portstays --iso-datetime 2025-10-14T12:00:00Z
```

The command inserts:

- Raw snapshot JSON into `portstays_snapshots` (for audit/debug).
- Aggregated tanker departures/arrivals into `portstays_daily` keyed by `(date, port_code, source)`.

`python -m spvx.cli ingest --mode live` automatically attempts a snapshot when PortStays credentials are present.

## 3. Scheduler / Rate Limit

- Suggested cadence: **every 15 minutes** (96 calls/day) to stay within the 100 req/day limit.
- For each poll: `date = datetime.utcnow().replace(second=0, microsecond=0)`, pass as ISO string.
- Implement back-off on `429/5xx` (already handled once inside the module) and cap retries to avoid bursts.
- For historical backfills, iterate day-by-day with a slower rate (e.g. 10 calls/day) or coordinate with NxtPort support.

## 4. DuckDB Tables

`spvx.db.ensure_core_tables` now provisions:

| Table | Purpose |
|-------|---------|
| `portstays_snapshots` | Raw payloads (JSON as TEXT) keyed by snapshot time and request date. |
| `portstays_daily` | Aggregated tanker departures/arrivals per day & port (source label `portstays_uat`). |

`PORT_EU` components prefer `portstays_daily` (Antwerp/Zeebrugge) and fall back to the legacy Rotterdam mock if PortStays data is absent.

## 5. Data Mapping

- Vessel filter: `vessel.vesselType` contains `tank`, `oil`, `product`, or `chem`.
- Departure timestamp: `atd` / `actualDeparture` / `actualTimeOfDeparture`.
- Arrival timestamp: `ata` / `actualArrival` / `actualTimeOfArrival`.
- Port identifiers: `port.code` or `port.name`. They are slugified to lower-case tokens (e.g. `antwerp`, `zeebrugge`, `beanr`).
- Aggregation output counts tanker departures/arrivals per day.

## 6. Integration With Components

`spvx.features.components.build_components` prefers PortStays data for the `PORT_EU` signal. When availability is ≥90% in the trailing 30 days, you'll see Antwerp reflected in the dashboard driver chips.

## 7. Observability

- Inspect latest aggregate: `SELECT * FROM portstays_daily ORDER BY d DESC LIMIT 10;`
- Check raw payload timestamps: `SELECT * FROM portstays_snapshots ORDER BY snapshot_ts DESC LIMIT 5;`
- `ops/health` output will include `PORT_EU` coverage once snapshots populate the table.

## 8. Go-Live Notes

- Swap to production endpoints/keys via environment overrides.
- Update scheduler environment (systemd/cron) to point at the production token URL and API base.
- Monitor first-week coverage & revision metrics before declaring production readiness.
