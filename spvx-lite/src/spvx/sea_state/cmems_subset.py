"""
Optimized CMEMS downloader using subset API for bounding boxes.
Downloads only the specific regions instead of full global files.
"""

import datetime as dt
import logging
import os
from pathlib import Path

try:
    import copernicusmarine
    HAS_CMEMS = True
except ImportError:
    HAS_CMEMS = False

LOG = logging.getLogger("spvx.sea_state.cmems_subset")


def download_region_subset(
    dataset_id: str,
    bbox: dict,
    out_file: str,
    start_date: dt.date,
    end_date: dt.date,
    username: str | None = None,
    password: str | None = None,
) -> str | None:
    """
    Download CMEMS data for a specific bounding box using subset API.
    
    This downloads ONLY the region, not the full global file!
    """
    if not HAS_CMEMS:
        raise ImportError("copernicusmarine not installed")
    
    # Check if already exists
    if os.path.exists(out_file):
        LOG.debug(f"[CMEMS] Cached: {os.path.basename(out_file)}")
        return out_file
    
    # Ensure output directory
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)
    
    try:
        LOG.info(f"[CMEMS] Downloading subset: {os.path.basename(out_file)}")
        LOG.info(f"        Bbox: {bbox}")
        
        copernicusmarine.subset(
            dataset_id=dataset_id,
            minimum_longitude=bbox['lon_min'],
            maximum_longitude=bbox['lon_max'],
            minimum_latitude=bbox['lat_min'],
            maximum_latitude=bbox['lat_max'],
            start_datetime=start_date.strftime('%Y-%m-%d'),
            end_datetime=end_date.strftime('%Y-%m-%d'),
            output_filename=os.path.basename(out_file),
            output_directory=os.path.dirname(out_file),
            force_download=False,
            username=username,
            password=password,
        )
        
        if os.path.exists(out_file):
            size_mb = os.path.getsize(out_file) / (1024 * 1024)
            LOG.info(f"[CMEMS] ✅ Downloaded {os.path.basename(out_file)} ({size_mb:.1f} MB)")
            return out_file
        else:
            LOG.error(f"[CMEMS] ❌ File not created: {out_file}")
            return None
            
    except Exception as exc:
        LOG.error(f"[CMEMS] ❌ Subset download failed: {exc}")
        return None


def download_all_regions_subset(
    dataset_id: str,
    out_dir: str,
    regions: dict,
    lookback_days: int = 1,
    buffer_km: float = 50.0,
    username: str | None = None,
    password: str | None = None,
) -> dict[str, str]:
    """
    Download CMEMS subsets for all regions efficiently.
    
    Args:
        dataset_id: CMEMS dataset ID
        out_dir: Output directory
        regions: Dict of region_id -> bbox config
        lookback_days: Days to look back
        buffer_km: Buffer around bbox in km
        username: CMEMS username
        password: CMEMS password
    
    Returns:
        Dict mapping region_id to downloaded file path
    """
    end_date = dt.date.today()
    start_date = end_date - dt.timedelta(days=lookback_days)
    
    results = {}
    
    for region_id, config in regions.items():
        bbox = config.get('bbox')
        if not bbox:
            LOG.warning(f"[CMEMS] Skipping {region_id}: no bbox")
            continue
        
        # Expand bbox with buffer
        lat_buffer = buffer_km / 111.0
        import math
        lat_mid = (bbox['lat_min'] + bbox['lat_max']) / 2.0
        lon_denom = max(math.cos(math.radians(lat_mid)), 0.1)
        lon_buffer = buffer_km / (111.0 * lon_denom)
        
        expanded_bbox = {
            'lat_min': bbox['lat_min'] - lat_buffer,
            'lat_max': bbox['lat_max'] + lat_buffer,
            'lon_min': bbox['lon_min'] - lon_buffer,
            'lon_max': bbox['lon_max'] + lon_buffer,
        }
        
        # Generate output filename
        dataset_type = "waves" if "wav" in dataset_id.lower() else "currents"
        out_file = os.path.join(
            out_dir,
            f"{region_id}_{dataset_type}_{start_date}_{end_date}.nc"
        )
        
        result = download_region_subset(
            dataset_id=dataset_id,
            bbox=expanded_bbox,
            out_file=out_file,
            start_date=start_date,
            end_date=end_date,
            username=username,
            password=password,
        )
        
        if result:
            results[region_id] = result
    
    LOG.info(f"[CMEMS] ✅ Downloaded {len(results)}/{len(regions)} regions")
    return results
