# Copernicus Marine Service (CMEMS) Integration

This guide walks through the complete setup and usage of the CMEMS integration for sea-state data in SPVX-Lite.

## Overview

The CMEMS integration provides:
- **Wave data**: Significant wave height (Hs) from global wave analysis/forecast
- **Current data**: Ocean surface currents (u/v components) from physical ocean models
- **Features**: SEA_HS_Z (wave height Z-score) and OPPOSING_CURRENT (projected current)

## 1. Prerequisites

### Install Dependencies
```bash
pip install -r requirements.txt
```

This installs:
- `copernicusmarine>=1.0.0` - CMEMS data access library
- `xarray>=2023.1.0` - Multi-dimensional array processing
- `netcdf4>=1.6.0` - NetCDF file format support

## 2. Create CMEMS Account (Free)

1. Visit: https://data.marine.copernicus.eu/register
2. Create a free account
3. Save your username and password

## 3. Configure Credentials

### Option A: One-time interactive login (recommended for local development)
```bash
copernicusmarine login
# Follow prompts to enter username/password
# Credentials will be cached locally
```

### Option B: Environment variables (recommended for CI/CD)
Edit `.env` and add:
```
CMEMS_USERNAME=your_username_here
CMEMS_PASSWORD=your_password_here
```

## 4. Configuration

The `config.yml` already includes CMEMS configuration:

```yaml
sea_state:
  provider: "cmems"
  waves_dataset_id: "cmems_mod_glo_wav_anfc_0.083deg_PT3H-i"
  currents_dataset_id: "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m"
  lookback_days: 3
  out_dir: "data/sea_state"

chokepoints:
  CQ_SG:
    bbox: {lat_min: 0.5, lat_max: 2.0, lon_min: 103.3, lon_max: 104.3}
    bearing_deg: 300  # Main vessel traffic direction
  CQ_TR:
    bbox: {lat_min: 40.9, lat_max: 41.4, lon_min: 28.6, lon_max: 29.3}
    bearing_deg: 20
  PORT_EU:
    bbox: {lat_min: 51.9, lat_max: 52.1, lon_min: 3.9, lon_max: 4.2}
    bearing_deg: 270
```

### Dataset Details

**Waves** (3-hourly):
- Product: GLOBAL_ANALYSISFORECAST_WAV_001_027
- Dataset: `cmems_mod_glo_wav_anfc_0.083deg_PT3H-i`
- Variable: VHM0 (significant wave height in meters)
- Resolution: 0.083° (~9 km)
- Update frequency: 3 hours

**Currents** (daily):
- Product: GLOBAL_ANALYSISFORECAST_PHY_001_024
- Dataset: `cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m`
- Variables: uo, vo (surface currents in m/s)
- Resolution: 0.083° (~9 km)
- Update frequency: Daily

## 5. Usage

### Ingest Sea-State Data
```bash
# Download and process CMEMS data for all chokepoints
python -m spvx.cli ingest-sea-state --provider cmems --lookback-days 3

# Process specific regions only
python -m spvx.cli ingest-sea-state --provider cmems --regions "CQ_SG,CQ_TR"
```

This will:
1. Download NetCDF files from CMEMS for the last 3 days
2. Extract wave height and currents for each chokepoint bounding box
3. Compute spatial means and opposing current components
4. Save processed data to `data/processed/sea_state_{chokepoint_id}.parquet`

### Compute Components and Index
```bash
# Build component features (includes SEA_HS_Z and OPPOSING_CURRENT)
python -m spvx.cli compute-index

# This produces:
# - data/processed/components.parquet (with sea-state features)
# - data/outputs/spvx_lite.csv (with SPVX_LITE and SPVX_LITE_EX_WEATHER)
```

### Run Tests
```bash
pytest tests/test_sea_state_cmems.py -v
```

## 6. Features

### SEA_HS_Z (Wave Height Anomaly)
- Seasonal Z-score of significant wave height
- Captures deviations from typical conditions for time of year
- Higher values indicate rougher seas than normal
- Weight in index: 0.08 (8% contribution)

### OPPOSING_CURRENT (Current Resistance)
- Projects surface current (u, v) onto vessel bearing direction
- Positive values = opposing current (headwind/current slowing vessels)
- Negative values = following current (tailwind/current speeding vessels)
- Weight in index: 0.05 (5% contribution)

## 7. Index Variants

### SPVX_LITE (Full Index)
- Includes all components: chokepoints + weather
- Reflects complete congestion picture

### SPVX_LITE_EX_WEATHER
- Excludes sea-state components (SEA_HS_Z, OPPOSING_CURRENT)
- Useful for isolating core chokepoint congestion from weather effects
- Both variants are computed automatically

## 8. Data Flow

```
CMEMS API
  ↓
Download NetCDF files (waves + currents)
  ↓
Extract bounding box spatial means per chokepoint
  ↓
Compute opposing current projection
  ↓
Save to data/processed/sea_state_{CQ}.parquet
  ↓
Load in components.py → compute SEA_HS_Z (seasonal Z-score)
  ↓
Merge with other components
  ↓
Index computation (weighted aggregation)
  ↓
Output: SPVX_LITE and SPVX_LITE_EX_WEATHER
```

## 9. Operational Notes

### Freshness and Fallback
- If CMEMS is unavailable, the pipeline continues without sea-state data
- Sea-state components are marked as optional in the index computation
- SPVX_LITE_EX_WEATHER always available as fallback

### Caching and Idempotency
- Downloads use `sync=True` for idempotent fetches
- Files already downloaded are skipped
- Use `--lookback-days` to control data window

### Error Handling
- Missing credentials → warnings, continues without CMEMS data
- Network errors → logged, continues with available data
- Invalid chokepoint IDs → warnings, skips unknown regions

## 10. Alternative Datasets

If you need different spatial/temporal resolution, consider:

**Higher-resolution waves**:
- `cmems_mod_glo_wav_anfc_0.042deg_PT1H-i` (4 km, hourly)

**Near-real-time currents**:
- `cmems_mod_glo_phy-cur_anfc_0.083deg_PT1H-m` (hourly)

Update `config.yml` `sea_state.waves_dataset_id` and `currents_dataset_id` accordingly.

## 11. Troubleshooting

### "ImportError: copernicusmarine package not installed"
```bash
pip install copernicusmarine
```

### "Login required" errors
```bash
copernicusmarine login
# Or set CMEMS_USERNAME and CMEMS_PASSWORD in .env
```

### Empty results
- Check bounding box coordinates in `config.yml`
- Verify dataset IDs are correct
- Confirm CMEMS account is active

### Files not found
- Use `--lookback-days` larger value to fetch older data
- Check CMEMS data availability for your time range

## 12. Next Steps

### Add Metrics (Prometheus)
```python
# In src/spvx/metrics.py
spvx_sea_state_provider = Gauge("spvx_sea_state_provider", "CMEMS provider status", ["source"])
spvx_sea_state_freshness_seconds = Gauge("spvx_sea_state_freshness_seconds", "Time since last fetch")
```

### Add to /ready Endpoint
Degrade health status if sea-state data is stale (>24h).

### Dashboard Badge
Display "Sea-State: CMEMS | as-of: 2025-01-15 12:00 UTC" in UI.

## Resources

- CMEMS Documentation: https://help.marine.copernicus.eu/
- Python Toolbox Guide: https://help.marine.copernicus.eu/en/collections/4060068-copernicus-marine-toolbox
- Dataset Catalog: https://data.marine.copernicus.eu/products
