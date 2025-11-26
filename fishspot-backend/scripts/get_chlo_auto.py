"""
Automated chlorophyll fetcher with fallback to CMEMS subset.

Usage examples:
  # Dry run: try ERDDAP for the dates; do NOT call CMEMS
  python scripts/get_chlo_auto.py --lat 9.82887 --lon 79.869067 --start 2025-11-19 --end 2025-11-26

  # Auto fallback: if ERDDAP missing, attempt CMEMS subset (requires saved credentials or env vars)
  python scripts/get_chlo_auto.py --lat 9.82887 --lon 79.869067 --start 2025-11-19 --end 2025-11-26 --auto

Notes:
- If you want automatic CMEMS selection without prompting, set env var `CMEMS_CHL_DATASET` to the dataset_id to request.
- The script will request a single NetCDF for the full date range (no per-day downloads) when using CMEMS subset.
"""

import argparse
import os
import json
from datetime import datetime, timedelta
from call_chlo_simple import fetch_chlo

parser = argparse.ArgumentParser()
parser.add_argument('--lat', type=float, required=True)
parser.add_argument('--lon', type=float, required=True)
parser.add_argument('--start', type=str, required=True, help='inclusive start date YYYY-MM-DD')
parser.add_argument('--end', type=str, required=True, help='inclusive end date YYYY-MM-DD')
parser.add_argument('--auto', action='store_true', help='Automatically call CMEMS subset fallback if ERDDAP returns no data')
parser.add_argument('--cmems-dataset', type=str, default=os.environ.get('CMEMS_CHL_DATASET'), help='CMEMS dataset id to request (or set CMEMS_CHL_DATASET env var)')
parser.add_argument('--output-dir', type=str, default='data/cmems_chl', help='output directory for CMEMS NetCDF')
args = parser.parse_args()

requested = {'lat': args.lat, 'lon': args.lon, 'start': args.start, 'end': args.end}

# 1) Try ERDDAP per-day
start_dt = datetime.fromisoformat(args.start)
end_dt = datetime.fromisoformat(args.end)
days = (end_dt - start_dt).days + 1
results = []
missing_days = []
for i in range(days):
    d = (start_dt + timedelta(days=i)).strftime('%Y-%m-%d')
    try:
        r = fetch_chlo(d, args.lat, args.lon)
        # fetch_chlo returns 'chlo': nan when no data - normalize to None
        ch = r.get('chlo')
        if ch is None:
            results.append({'date': d, 'chlo': None, 'source': 'erddap', 'meta': r})
            missing_days.append(d)
        else:
            # some implementations return float('nan') for no-data
            try:
                if str(ch).lower() == 'nan':
                    results.append({'date': d, 'chlo': None, 'source': 'erddap', 'meta': r})
                    missing_days.append(d)
                else:
                    results.append({'date': d, 'chlo': float(ch), 'source': 'erddap', 'meta': r})
            except Exception:
                results.append({'date': d, 'chlo': None, 'source': 'erddap', 'meta': r})
                missing_days.append(d)
    except Exception as e:
        results.append({'date': d, 'chlo': None, 'source': 'erddap', 'error': str(e)})
        missing_days.append(d)

out = {'requested': requested, 'erddap_results': results}

# 2) If any missing and --auto, attempt CMEMS subset fallback
if missing_days and args.auto:
    try:
        import copernicusmarine
    except Exception as e:
        out['cmems_error'] = f'copernicusmarine not available: {e}'
        print(json.dumps(out, indent=2))
        raise SystemExit(1)

    # dataset selection
    dsid = args.cmems_dataset
    if not dsid:
        out['cmems_error'] = 'No CMEMS dataset id provided. Set CMEMS_CHL_DATASET env var or pass --cmems-dataset'
        print(json.dumps(out, indent=2))
        raise SystemExit(1)

    # variables to try
    candidate_vars = ['chlor_a', 'chl', 'CHL', 'CHL_OC4', 'CHLA']

    start_dt_str = f"{args.start}T00:00:00"
    end_dt_str = f"{args.end}T23:59:59"

    os.makedirs(args.output_dir, exist_ok=True)
    try:
        # Request subset (single NetCDF for full range)
        copernicusmarine.subset(
            dataset_id=dsid,
            variables=candidate_vars,
            minimum_longitude=args.lon - 0.5,
            maximum_longitude=args.lon + 0.5,
            minimum_latitude=args.lat - 0.5,
            maximum_latitude=args.lat + 0.5,
            start_datetime=start_dt_str,
            end_datetime=end_dt_str,
            file_format='netcdf',
            output_directory=args.output_dir,
        )
    except Exception as e:
        out['cmems_error'] = f'CMEMS subset failed: {e}'
        print(json.dumps(out, indent=2))
        raise SystemExit(1)

    # find downloaded file
    import glob
    files = sorted(glob.glob(os.path.join(args.output_dir, '*.nc')))
    if not files:
        out['cmems_error'] = 'No NetCDF returned by CMEMS subset'
        print(json.dumps(out, indent=2))
        raise SystemExit(1)

    nc = files[-1]
    out['cmems_file'] = nc

    # open and extract point time series
    try:
        import xarray as xr
        ds = xr.open_dataset(nc)
    except Exception as e:
        out['cmems_error'] = f'Could not open NetCDF: {e}'
        print(json.dumps(out, indent=2))
        raise SystemExit(1)

    # find the variable name in dataset for chlorophyll
    varname = None
    for v in candidate_vars:
        if v in ds.data_vars:
            varname = v
            break
    if not varname:
        # fallback: pick first data var that contains 'chl' substring
        for v in ds.data_vars:
            if 'chl' in v.lower():
                varname = v
                break

    if not varname:
        out['cmems_error'] = f'No chlorophyll variable found in file. Available: {list(ds.data_vars)}'
        print(json.dumps(out, indent=2))
        raise SystemExit(1)

    da = ds[varname]
    # select nearest grid point
    lat_names = [n for n in ('latitude', 'lat') if n in da.dims]
    lon_names = [n for n in ('longitude', 'lon', 'longitude_long') if n in da.dims]
    if not lat_names or not lon_names:
        out['cmems_error'] = f'No lat/lon dims on variable {varname}, dims: {list(da.dims)}'
        print(json.dumps(out, indent=2))
        raise SystemExit(1)

    lat_name = lat_names[0]
    lon_name = lon_names[0]

    try:
        sel = da.sel({lat_name: args.lat, lon_name: args.lon}, method='nearest')
    except Exception:
        sel = da.isel({lat_name: 0, lon_name: 0})

    # reduce depth if present
    if 'depth' in sel.dims:
        try:
            sel = sel.sel(depth=0, method='nearest')
        except Exception:
            sel = sel.isel(depth=0)

    # prepare time series
    ts = []
    if 'time' in sel.dims:
        for t, v in zip(sel['time'].values, sel.values):
            try:
                t_iso = str(t.tolist())
            except Exception:
                t_iso = str(t)
            try:
                v_f = float(v) if (v is not None and str(v).lower() != 'nan') else None
            except Exception:
                v_f = None
            ts.append({'time': t_iso, 'chl': v_f})
    else:
        ts = [{'time': None, 'chl': None}]

    out['cmems_chl_var'] = varname
    out['cmems_point'] = {lat_name: float(sel.coords[lat_name].values), lon_name: float(sel.coords[lon_name].values)}
    out['cmems_timeseries'] = ts

print(json.dumps(out, indent=2))
