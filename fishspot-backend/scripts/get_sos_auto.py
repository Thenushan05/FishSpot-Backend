"""Get SSS (`sos`) for a requested date or date range and lat/lon.

Behavior:
- Check local CMEMS NetCDF files in `data/cmems_week/` and `data/cmems_cache/` for coverage.
- If a local file covers the requested date range and contains the point, read from it (no download).
- Otherwise, if `--auto-download` is set, request a small CMEMS subset (single NetCDF covering the range) and read the point.
- Returns JSON with timeseries and provenance.

Usage examples (PowerShell):
& '.\app\.venv\Scripts\Activate.ps1'
python .\scripts\get_sos_auto.py --lat 9.82887 --lon 79.869067 --start 2025-11-19 --end 2025-11-26

To allow automatic CMEMS download (requires Copernicus credentials saved or env vars):
python .\scripts\get_sos_auto.py --lat 9.82887 --lon 79.869067 --start 2025-11-19 --end 2025-11-26 --auto-download --cmems-dataset cmems_obs-mob_glo_phy-sss_nrt_multi_P1D
"""

import os
import glob
import json
import argparse
from datetime import datetime

parser = argparse.ArgumentParser()
parser.add_argument('--lat', type=float, required=True)
parser.add_argument('--lon', type=float, required=True)
parser.add_argument('--start', type=str, required=True, help='YYYY-MM-DD')
parser.add_argument('--end', type=str, required=True, help='YYYY-MM-DD')
parser.add_argument('--auto-download', action='store_true', help='If missing locally, request CMEMS subset')
parser.add_argument('--cmems-dataset', type=str, default=os.environ.get('CMEMS_SOS_DATASET'), help='CMEMS dataset id for SSS (or set CMEMS_SOS_DATASET)')
parser.add_argument('--outdir', type=str, default='data/cmems_cache', help='Directory to save CMEMS subsets')
args = parser.parse_args()

LAT = args.lat
LON = args.lon
START = datetime.fromisoformat(args.start)
END = datetime.fromisoformat(args.end)

SEARCH_DIRS = [os.path.join('data','cmems_week'), os.path.join('data','cmems_cache')]


def nc_time_range_contains(nc_path, start_dt, end_dt):
    try:
        import xarray as xr
        ds = xr.open_dataset(nc_path)
        if 'time' not in ds.coords and 'time' not in ds.dims:
            return False
        t0 = ds['time'].min().values
        t1 = ds['time'].max().values
        # convert to pandas timestamps
        import pandas as pd
        t0p = pd.to_datetime(t0).to_pydatetime()
        t1p = pd.to_datetime(t1).to_pydatetime()
        return (t0p <= start_dt) and (t1p >= end_dt)
    except Exception:
        return False


def nc_contains_point(nc_path, lat, lon):
    try:
        import xarray as xr
        ds = xr.open_dataset(nc_path)
        # find lat/lon coords
        lat_name = next((n for n in ('latitude','lat') if n in ds.coords or n in ds.dims), None)
        lon_name = next((n for n in ('longitude','lon') if n in ds.coords or n in ds.dims), None)
        if not lat_name or not lon_name:
            return False
        lats = ds.coords[lat_name].values
        lons = ds.coords[lon_name].values
        # handle 0..360 lon arrays
        if lons.max() > 180 and lon < 0:
            lon = lon % 360
        in_lat = lats.min() <= lat <= lats.max()
        in_lon = lons.min() <= lon <= lons.max()
        return in_lat and in_lon
    except Exception:
        return False


def find_local_nc(lat, lon, start_dt, end_dt):
    # search known dirs for .nc files that cover time and point
    candidates = []
    for d in SEARCH_DIRS:
        p = os.path.join(d, '*.nc')
        candidates.extend(glob.glob(p))
    # check each candidate
    for fn in sorted(candidates):
        if nc_time_range_contains(fn, start_dt, end_dt) and nc_contains_point(fn, lat, lon):
            return fn
    return None


def extract_point_timeseries(nc_path, lat, lon):
    import xarray as xr
    import numpy as np
    ds = xr.open_dataset(nc_path)
    # find sos variable
    varname = None
    for v in ds.data_vars:
        if v.lower() in ('sos','sea_surface_salinity','sea_surface_salinity_with_quality_flag','salinity') or 'salin' in v.lower():
            varname = v
            break
    if not varname:
        # fallback: first var containing 'sos' or 'sal' or pick the first
        for v in ds.data_vars:
            if 'sos' in v.lower() or 'sal' in v.lower():
                varname = v
                break
    if not varname:
        # nothing to extract
        return {'error': 'no salinity-like variable found', 'available_vars': list(ds.data_vars)}

    da = ds[varname]
    lat_name = next((n for n in ('latitude','lat') if n in da.dims), None)
    lon_name = next((n for n in ('longitude','lon') if n in da.dims), None)
    if not lat_name or not lon_name:
        return {'error': 'lat/lon dims missing on variable', 'dims': list(da.dims)}

    try:
        sel = da.sel({lat_name: lat, lon_name: lon}, method='nearest')
    except Exception:
        # fallback to index nearest
        import numpy as np
        lats = da.coords[lat_name].values
        lons = da.coords[lon_name].values
        ilat = int(np.abs(lats - lat).argmin())
        ilon = int(np.abs(lons - lon).argmin())
        sel = da.isel({lat_name: ilat, lon_name: ilon})

    if 'depth' in sel.dims:
        try:
            sel = sel.sel(depth=0, method='nearest')
        except Exception:
            sel = sel.isel(depth=0)

    # build timeseries
    out = []
    if 'time' in sel.dims:
        times = sel['time'].values
        vals = sel.values
        import pandas as pd
        for t, v in zip(times, vals):
            try:
                t_iso = pd.to_datetime(t).isoformat()
            except Exception:
                t_iso = str(t)
            try:
                if hasattr(v, 'item'):
                    v_val = v.item()
                else:
                    v_val = v
                v_f = float(v_val) if (v_val is not None and str(v_val).lower() != 'nan') else None
            except Exception:
                v_f = None
            out.append({'time': t_iso, 'sos': v_f})
    else:
        # scalar
        v = sel.values
        try:
            v_f = float(v)
        except Exception:
            v_f = None
        out = [{'time': None, 'sos': v_f}]

    # report selected grid cell
    selected = {lat_name: float(sel.coords[lat_name].values), lon_name: float(sel.coords[lon_name].values)}
    return {'file': nc_path, 'variable': varname, 'selected_point': selected, 'timeseries': out}


def cmems_subset_and_save(dataset_id, lat, lon, start_dt, end_dt, outdir):
    try:
        import copernicusmarine
    except Exception as e:
        return {'error': f'copernicusmarine not available: {e}'}
    os.makedirs(outdir, exist_ok=True)
    start_str = f"{start_dt.date().isoformat()}T00:00:00"
    end_str = f"{end_dt.date().isoformat()}T23:59:59"
    # small box around point to keep file small
    lon_min = lon - 0.25
    lon_max = lon + 0.25
    lat_min = lat - 0.25
    lat_max = lat + 0.25
    # variables for SSS
    vars = ['sos', 'sea_surface_salinity', 'salinity']
    try:
        copernicusmarine.subset(
            dataset_id=dataset_id,
            variables=vars,
            minimum_longitude=lon_min,
            maximum_longitude=lon_max,
            minimum_latitude=lat_min,
            maximum_latitude=lat_max,
            start_datetime=start_str,
            end_datetime=end_str,
            file_format='netcdf',
            output_directory=outdir,
        )
    except Exception as e:
        return {'error': f'CMEMS subset failed: {e}'}
    # find created file
    fl = sorted(glob.glob(os.path.join(outdir, '*.nc')))
    if not fl:
        return {'error': 'no file created by CMEMS subset'}
    return {'file': fl[-1]}


# --- main flow ---
res = {'request': {'lat': LAT, 'lon': LON, 'start': args.start, 'end': args.end}}
local = find_local_nc(LAT, LON, START, END)
if local:
    res['source'] = 'local'
    res['file'] = local
    res['extracted'] = extract_point_timeseries(local, LAT, LON)
    print(json.dumps(res, indent=2))
    raise SystemExit(0)

# no local coverage
res['source'] = 'missing_local'
if not args.auto_download:
    res['message'] = 'no local file covering request; --auto-download to fetch from CMEMS'
    print(json.dumps(res, indent=2))
    raise SystemExit(0)

# auto download requested
if not args.cmems_dataset:
    res['error'] = 'no CMEMS dataset id provided; set CMEMS_SOS_DATASET or pass --cmems-dataset'
    print(json.dumps(res, indent=2))
    raise SystemExit(1)

res['cmems_dataset'] = args.cmems_dataset
res['cmems_outdir'] = args.outdir
cd = cmems_subset_and_save(args.cmems_dataset, LAT, LON, START, END, args.outdir)
if 'error' in cd:
    res['cmems_error'] = cd['error']
    print(json.dumps(res, indent=2))
    raise SystemExit(1)

res['file_downloaded'] = cd['file']
res['source'] = 'cmems_subset'
res['extracted'] = extract_point_timeseries(cd['file'], LAT, LON)
print(json.dumps(res, indent=2))
