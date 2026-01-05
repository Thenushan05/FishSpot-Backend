#!/usr/bin/env python3
"""
Fetch SST and SSH from Open-Meteo for a bbox, sample GEBCO depths, write model inputs,
and optionally run the backend model to produce predictions.

Usage (PowerShell) from backend repo root (activate virtualenv first):

  Set-Location D:\Fish-Full\Backend\fishspot-backend
  & .\app\.venv\Scripts\Activate.ps1
  python .\scripts\fetch_and_predict_bbox.py --min-lat 54.544 --max-lat 54.61 --min-lon 10.2 --max-lon 10.4 --lat-step 0.02 --lon-step 0.02 --out-prefix D:/Fish-Full/fin-finder-grid/sst_ssh_54.544_10.2 --write-model-inputs --run-predict

Notes:
- The script uses `openmeteo_requests` + `requests_cache` + `retry_requests` for robust API calls.
- It samples GEBCO from `data/depth/GEBCO_2025_sub_ice.nc` in the backend repo (nearest-neighbor).
- It writes `model_inputs_bbox.json` to the frontend path `D:/Fish-Full/fin-finder-grid/` by default
  so the frontend and other scripts can find the file. Change `FRONTEND_MODEL_INPUT_PATH` below if needed.

Required python packages (install in backend venv):
  pip install openmeteo_requests requests-cache retry-requests pandas xarray netCDF4 numpy

"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import math
from typing import List, Tuple
import datetime

import pandas as pd
import requests_cache
import openmeteo_requests
from retry_requests import retry

try:
    import xarray as xr
except Exception:
    xr = None


FRONTEND_MODEL_INPUT_PATH = Path("D:/Fish-Full/fin-finder-grid/model_inputs_bbox.json")
GEBCO_PATH = Path(__file__).resolve().parents[1] / "data" / "depth" / "GEBCO_2025_sub_ice.nc"


def build_grid(min_lat: float, max_lat: float, min_lon: float, max_lon: float, lat_step: float, lon_step: float) -> List[Tuple[float, float]]:
    pts = []
    lat = min_lat
    # include end point when stepping
    while lat <= max_lat + 1e-12:
        lon = min_lon
        while lon <= max_lon + 1e-12:
            pts.append((round(lat, 8), round(lon, 8)))
            lon += lon_step
        lat += lat_step
    return pts


def safe_get_hourly_mean(response, var_index: int):
    try:
        hourly = response.Hourly()
        var = hourly.Variables(var_index)
        vals = var.ValuesAsNumpy()
        if hasattr(vals, 'tolist'):
            arr = vals.tolist()
        else:
            arr = [vals]
        clean = [float(x) for x in arr if x is not None and not (isinstance(x, float) and math.isnan(x))]
        if not clean:
            return None
        return sum(clean) / len(clean)
    except Exception:
        return None


def fetch_sst_ssh_for_points(points: List[Tuple[float, float]], utm_source: str = 'backend_fetch') -> List[dict]:
    cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
    retry_session = retry(cache_session, retries=4, backoff_factor=0.2)
    client = openmeteo_requests.Client(session=retry_session)

    out = []
    for lat, lon in points:
        params = {
            'latitude': float(lat),
            'longitude': float(lon),
            'hourly': ['sea_surface_temperature', 'sea_level_height_msl'],
            'utm_source': utm_source,
        }
        try:
            responses = client.weather_api('https://marine-api.open-meteo.com/v1/marine', params=params)
            if not responses:
                out.append({'lat': lat, 'lon': lon, 'sst': None, 'ssh': None})
                continue
            r = responses[0]
            sst_mean = safe_get_hourly_mean(r, 0)
            ssh_mean = safe_get_hourly_mean(r, 1)
            out.append({'lat': lat, 'lon': lon, 'sst': sst_mean, 'ssh': ssh_mean})
        except Exception as e:
            print(f"fetch error {lat},{lon}: {e}")
            out.append({'lat': lat, 'lon': lon, 'sst': None, 'ssh': None})
    return out


def sample_gebco_depths(points: List[Tuple[float, float]]):
    if xr is None:
        raise RuntimeError('xarray is required to read GEBCO netCDF (install xarray + netCDF4)')
    if not GEBCO_PATH.exists():
        raise FileNotFoundError(f"GEBCO file not found at {GEBCO_PATH}")
    ds = xr.open_dataset(GEBCO_PATH)
    # variable name 'elevation' assumed
    elev = ds['elevation']
    rows = []
    for lat, lon in points:
        try:
            sel = elev.sel(lat=lat, lon=lon, method='nearest')
            elev_val = float(sel.values)
            depth_m = max(0.0, -elev_val)
        except Exception:
            depth_m = None
        rows.append(depth_m)
    ds.close()
    return rows


def build_model_inputs(fetched: List[dict], depths: List[float], year: int, month: int, species_code: str = 'UNKNOWN') -> List[dict]:
    rows = []
    for i, p in enumerate(fetched):
        depth = depths[i] if i < len(depths) else None
        row = {
            'year': int(year) if year is not None else None,
            'month': int(month) if month is not None else None,
            'lat': p['lat'],
            'lon': p['lon'],
            'depth': depth,
            'sss': None,
            'ssd': None,
            'sst': p.get('sst'),
            'ssh': p.get('ssh'),
            'chlo': None,
            'SPECIES_CODE': species_code,
            'monsoon': 'No_monsoon_region'
        }
        rows.append(row)
    return rows


def write_model_inputs(rows: List[dict], out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(rows, f, indent=2)
    print(f"Wrote {len(rows)} model input rows to {out_path}")


def run_predict(rows: List[dict], out_path: Path):
    from app.services import ml_hotspot
    preds = ml_hotspot.predict_cells(rows)
    with open(out_path, 'w') as f:
        json.dump(preds, f, indent=2)
    print(f"Wrote {len(preds)} predictions to {out_path}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--min-lat', type=float)
    p.add_argument('--max-lat', type=float)
    p.add_argument('--min-lon', type=float)
    p.add_argument('--max-lon', type=float)
    p.add_argument('--lat-step', type=float, default=0.02)
    p.add_argument('--lon-step', type=float, default=0.02)
    p.add_argument('--bbox-file', type=str, default=None, help='Optional JSON file with keys min_lat,max_lat,min_lon,max_lon')
    p.add_argument('--out-prefix', type=str, default=None)
    p.add_argument('--write-model-inputs', action='store_true')
    p.add_argument('--run-predict', action='store_true')
    p.add_argument('--year', type=int, default=None)
    p.add_argument('--month', type=int, default=None)
    p.add_argument('--species-code', type=str, default='UNKNOWN')
    args = p.parse_args()

    if args.bbox_file:
        bf = Path(args.bbox_file)
        if not bf.exists():
            raise FileNotFoundError(f"BBox file not found: {bf}")
        j = json.loads(bf.read_text())
        min_lat = float(j['min_lat'])
        max_lat = float(j['max_lat'])
        min_lon = float(j['min_lon'])
        max_lon = float(j['max_lon'])
    else:
        if None in (args.min_lat, args.max_lat, args.min_lon, args.max_lon):
            raise SystemExit('Provide bbox via numeric args or --bbox-file')
        min_lat = args.min_lat
        max_lat = args.max_lat
        min_lon = args.min_lon
        max_lon = args.max_lon

    points = build_grid(min_lat, max_lat, min_lon, max_lon, args.lat_step, args.lon_step)
    print(f"Fetching SST/SSH for {len(points)} points")
    fetched = fetch_sst_ssh_for_points(points, utm_source='backend_fetch')

    # sample GEBCO depths if available
    depths = []
    try:
        depths = sample_gebco_depths(points)
    except Exception as e:
        print(f"Warning: GEBCO sampling failed: {e}")
        depths = [None] * len(points)

    # default year/month
    now = datetime.datetime.utcnow()
    year = args.year or now.year
    month = args.month or now.month

    model_rows = build_model_inputs(fetched, depths, year, month, species_code=args.species_code)

    out_prefix = args.out_prefix or f"D:/Fish-Find/fin-finder-grid/sst_ssh_{min_lat}_{min_lon}"
    csv_path = Path(f"{out_prefix}.csv")
    json_path = Path(f"{out_prefix}.json")
    pd.DataFrame(fetched).to_csv(csv_path, index=False)
    pd.DataFrame(fetched).to_json(json_path, orient='records', indent=2)
    print(f"Wrote SST/SSH CSV: {csv_path} JSON: {json_path}")

    # write model inputs to frontend path by default
    if args.write_model_inputs:
        write_model_inputs(model_rows, FRONTEND_MODEL_INPUT_PATH)

    if args.run_predict:
        preds_out = Path(__file__).resolve().parents[0] / 'predictions_bbox.json'
        run_predict(model_rows, preds_out)


if __name__ == '__main__':
    main()
