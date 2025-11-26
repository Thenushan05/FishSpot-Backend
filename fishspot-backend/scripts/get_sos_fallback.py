"""
Search local CMEMS NetCDF files for `sos` starting from today and going back up to 7 days.
If no valid sos is found locally, optionally request a CMEMS subset for the last 7 days (one NetCDF)
and extract the sos time series for the point.

Usage (PowerShell):
  & '.\app\.venv\Scripts\Activate.ps1'
  python .\scripts\get_sos_fallback.py --lat 9.82887 --lon 79.869067 --auto-download --cmems-dataset cmems_obs-mob_glo_phy-sss_nrt_multi_P1D

By default the script will try today then today-1 ... today-6 (7 days total) using local cached NetCDFs in
`data/cmems_week/` and `data/cmems_cache/`.

If `--auto-download` is passed, the script will call `copernicusmarine.subset` to create one NetCDF
for the last 7 days around the point (small box ±0.25°) then extract sos from that file.
"""

import os
import glob
import json
import argparse
from datetime import datetime, timedelta

import xarray as xr
import numpy as np

parser = argparse.ArgumentParser()
parser.add_argument('--lat', type=float, required=True)
parser.add_argument('--lon', type=float, required=True)
parser.add_argument('--days', type=int, default=7, help='how many days back to try (default 7)')
parser.add_argument('--auto-download', action='store_true', help='If no local data, download weekly CMEMS subset')
parser.add_argument('--cmems-dataset', type=str, default=os.environ.get('CMEMS_SOS_DATASET','cmems_obs-mob_glo_phy-sss_nrt_multi_P1D'))
parser.add_argument('--outdir', type=str, default='data/cmems_cache')
args = parser.parse_args()

LAT = args.lat
LON = args.lon
DAYS = args.days

SEARCH_DIRS = [os.path.join('data','cmems_week'), os.path.join('data','cmems_cache')]


def find_local_files():
    files = []
    for d in SEARCH_DIRS:
        files.extend(glob.glob(os.path.join(d, '*.nc')))
    files = sorted(files)
    return files


def file_covers_date_and_point(fn, date_obj, lat, lon):
    try:
        ds = xr.open_dataset(fn)
    except Exception:
        return False
    # check time coverage
    if 'time' not in ds.coords and 'time' not in ds.dims:
        return False
    tmin = np.array(ds['time'].min())
    tmax = np.array(ds['time'].max())
    try:
        import pandas as pd
        t0 = pd.to_datetime(tmin).date()
        t1 = pd.to_datetime(tmax).date()
    except Exception:
        return False
    if not (t0 <= date_obj <= t1):
        return False
    # check lat/lon range
    lat_name = next((n for n in ('latitude','lat') if n in ds.coords or n in ds.dims), None)
    lon_name = next((n for n in ('longitude','lon') if n in ds.coords or n in ds.dims), None)
    if not lat_name or not lon_name:
        return False
    lats = ds.coords[lat_name].values
    lons = ds.coords[lon_name].values
    # handle 0..360 lon
    lon_check = lon
    if lons.max() > 180 and lon < 0:
        lon_check = lon % 360
    if (lats.min() <= lat <= lats.max()) and (lons.min() <= lon_check <= lons.max()):
        return True
    return False


def extract_sos_on_date(fn, date_obj, lat, lon):
    try:
        ds = xr.open_dataset(fn)
    except Exception as e:
        return {'error': f'open_failed: {e}'}
    # find variable
    varname = None
    for v in ds.data_vars:
        if v.lower() == 'sos' or 'salin' in v.lower():
            varname = v
            break
    if not varname:
        return {'error': 'no_sos_var', 'available_vars': list(ds.data_vars)}

    da = ds[varname]
    lat_name = next((n for n in ('latitude','lat') if n in da.dims), None)
    lon_name = next((n for n in ('longitude','lon') if n in da.dims), None)
    if not lat_name or not lon_name:
        return {'error': 'latlon_missing', 'dims': list(da.dims)}

    # select nearest lat/lon
    sel = da.sel({lat_name: lat, lon_name: lon}, method='nearest')
    # select time nearest to date at noon
    times = sel['time'].values
    import pandas as pd
    # convert to dates
    time_dates = [pd.to_datetime(t).date() for t in times]
    # find index for matching date
    try:
        idx = time_dates.index(date_obj)
    except ValueError:
        # choose nearest in time
        deltas = [abs((td - date_obj).days) for td in time_dates]
        idx = int(np.argmin(deltas))
    val = sel.isel(time=idx).values
    try:
        if hasattr(val, 'item'):
            val = val.item()
        val_f = None if val is None or (isinstance(val, float) and np.isnan(val)) else float(val)
    except Exception:
        val_f = None
    actual_lat = float(sel.coords[lat_name].values)
    actual_lon = float(sel.coords[lon_name].values)
    return {'file': fn, 'date': str(date_obj), 'selected_point': {lat_name: actual_lat, lon_name: actual_lon}, 'sos': val_f}


def cmems_subset_last_week_and_extract(lat, lon, days, dataset_id, outdir):
    # request last `days` up to today
    end = datetime.utcnow().date()
    start = end - timedelta(days=days-1)
    start_str = f"{start.isoformat()}T00:00:00"
    end_str = f"{end.isoformat()}T23:59:59"
    lon_min = lon - 0.25
    lon_max = lon + 0.25
    lat_min = lat - 0.25
    lat_max = lat + 0.25
    os.makedirs(outdir, exist_ok=True)
    try:
        import copernicusmarine
    except Exception as e:
        return {'error': f'copernicusmarine_not_installed: {e}'}
    try:
        copernicusmarine.subset(
            dataset_id=dataset_id,
            variables=['sos','sea_surface_salinity','salinity'],
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
        return {'error': f'subset_failed: {e}'}
    # pick last file
    files = sorted(glob.glob(os.path.join(outdir, '*.nc')))
    if not files:
        return {'error': 'no_file_created'}
    fn = files[-1]
    # extract full timeseries at nearest point
    try:
        ds = xr.open_dataset(fn)
        varname = None
        for v in ds.data_vars:
            if v.lower() == 'sos' or 'salin' in v.lower():
                varname = v
                break
        if not varname:
            return {'error': 'no_sos_var_in_cmems', 'vars': list(ds.data_vars)}
        da = ds[varname]
        lat_name = next((n for n in ('latitude','lat') if n in da.dims), None)
        lon_name = next((n for n in ('longitude','lon') if n in da.dims), None)
        sel = da.sel({lat_name: lat, lon_name: lon}, method='nearest')
        if 'depth' in sel.dims:
            sel = sel.sel(depth=0, method='nearest')
        out_ts = []
        import pandas as pd
        for t, v in zip(sel['time'].values, sel.values):
            try:
                t_iso = pd.to_datetime(t).isoformat()
            except Exception:
                t_iso = str(t)
            v_val = None
            try:
                if hasattr(v, 'item'):
                    v_val = v.item()
                else:
                    v_val = v
                if isinstance(v_val, float) and np.isnan(v_val):
                    v_val = None
            except Exception:
                v_val = None
            out_ts.append({'time': t_iso, 'sos': v_val})
        return {'file': fn, 'timeseries': out_ts}
    except Exception as e:
        return {'error': f'extract_failed: {e}'}


# MAIN
files = find_local_files()
if not files:
    local_msg = 'no local cmems netcdf files found in data/cmems_week or data/cmems_cache'
else:
    local_msg = f'found {len(files)} local netcdf files'

# try dates from today to today - (DAYS-1)
today = datetime.utcnow().date()
for d in range(0, DAYS):
    check_date = today - timedelta(days=d)
    # search local files for coverage and point
    for fn in files:
        if file_covers_date_and_point(fn, check_date, LAT, LON):
            # extract value at that date
            res = extract_sos_on_date(fn, check_date, LAT, LON)
            if 'sos' in res and res['sos'] is not None:
                out = {'method': 'local_file', 'file': fn, 'date_found': res['date'], 'selected_point': res.get('selected_point'), 'sos': res['sos']}
                print(json.dumps(out, indent=2))
                raise SystemExit(0)
            # if file covers but sos is None, keep trying

# if we get here, no valid sos found in local files for last DAYS
if not args.auto_download:
    print(json.dumps({'method': 'none', 'message': f'no valid local sos found for last {DAYS} days', 'local_msg': local_msg}, indent=2))
    raise SystemExit(0)

# attempt CMEMS subset for last DAYS days and extract
cmems_id = args.cmems_dataset
res = cmems_subset_last_week_and_extract(LAT, LON, DAYS, cmems_id, args.outdir)
print(json.dumps({'method': 'cmems_subset', 'result': res}, indent=2))
