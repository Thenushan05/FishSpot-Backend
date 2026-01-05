"""Build in-memory model inputs (lat, lon, depth, sst, ssh, year, month, species).

This module is used by the API to return raw inputs for a given bbox and date
without writing any intermediate files. It uses the existing depth service and
Open-Meteo helper to populate depth, sst and ssh for the grid.
"""
from typing import List, Tuple, Dict, Optional
from datetime import datetime

import pandas as pd

from app.services import depth_service, openmeteo_service
from app.services.predict import _synthesize_grid


def build_region_inputs(date: Optional[str], bbox: Tuple[float, float, float, float], species: str = "UNKNOWN") -> List[Dict]:
    """Return a list of input dicts for the bbox and date.

    Each dict contains: lat, lon, depth, sst, ssh, year, month, SPECIES_CODE
    """
    # Ensure date string
    if date is None:
        date = datetime.utcnow().strftime("%Y%m%d")
    # Use predict._synthesize_grid to create a regular grid inside bbox
    df = _synthesize_grid(bbox)
    # Ensure year/month filled
    try:
        year_val = int(str(date)[:4])
        month_val = int(str(date)[4:6])
    except Exception:
        now = datetime.utcnow()
        year_val = now.year
        month_val = now.month

    df["year"] = df.get("year", year_val)
    df["month"] = df.get("month", month_val)
    df["SPECIES_CODE"] = species

    # Build lat/lon lists
    lats = df["lat"].tolist()
    lons = df["lon"].tolist()

    # Depths (batched)
    depths = []
    try:
        depth_results = depth_service.get_depths(lats, lons)
        depths = [r.get("value") for r in depth_results]
    except Exception:
        depths = [None] * len(lats)

    # SST/SSH (batched via Open-Meteo helper)
    sstssh = []
    try:
        sstssh = openmeteo_service.get_sst_ssh_for_points(lats, lons)
    except Exception:
        sstssh = [{'sst': None, 'ssh': None} for _ in lats]

    rows: List[Dict] = []
    for i, (lat, lon) in enumerate(zip(lats, lons)):
        row = {
            'lat': float(lat),
            'lon': float(lon),
            'depth': depths[i] if i < len(depths) else None,
            'sst': sstssh[i].get('sst') if i < len(sstssh) else None,
            'ssh': sstssh[i].get('ssh') if i < len(sstssh) else None,
            'year': int(df.iloc[i]['year']) if 'year' in df.columns else year_val,
            'month': int(df.iloc[i]['month']) if 'month' in df.columns else month_val,
            'SPECIES_CODE': species,
        }
        rows.append(row)

    return rows
