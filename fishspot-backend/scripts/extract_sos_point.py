import xarray as xr
import json
import os
import glob
import sys
import argparse
import numpy as np

parser = argparse.ArgumentParser(description='Extract sos time series at nearest grid point')
parser.add_argument('--lat', type=float, required=True, help='latitude')
parser.add_argument('--lon', type=float, required=True, help='longitude')
parser.add_argument('--file', type=str, default=None, help='path to .nc file (optional)')
args = parser.parse_args()

root = os.getcwd()
if args.file:
    fn = args.file
else:
    path = os.path.join(root, 'data', 'cmems_week')
    files = sorted(glob.glob(os.path.join(path, '*.nc')))
    if not files:
        print(json.dumps({'error': 'no cmems_week .nc files found', 'searched': path}))
        sys.exit(2)
    fn = files[-1]

try:
    ds = xr.open_dataset(fn)
except Exception as e:
    print(json.dumps({'error': 'failed to open dataset', 'file': fn, 'exc': str(e)}))
    sys.exit(3)

if 'sos' not in ds.variables:
    print(json.dumps({'error': "variable 'sos' not found in dataset", 'file': fn, 'vars': list(ds.variables)}))
    sys.exit(4)

sos = ds['sos']
# Handle common lat/lon names
lat_name = next((n for n in ('latitude','lat') if n in sos.dims), None)
lon_name = next((n for n in ('longitude','lon') if n in sos.dims), None)
if not lat_name or not lon_name:
    print(json.dumps({'error': 'latitude/longitude dims not found on sos variable', 'dims': list(sos.dims)}))
    sys.exit(5)

# Select nearest point
try:
    sel = sos.sel({lat_name: args.lat, lon_name: args.lon}, method='nearest')
except Exception:
    # Fallback: compute nearest by distance
    lats = sos.coords[lat_name].values
    lons = sos.coords[lon_name].values
    # handle lons possibly 0..360
    lon_array = lons
    desired_lon = args.lon
    if lon_array.max() > 180 and desired_lon < 0:
        desired_lon = desired_lon % 360
    ilat = int(np.abs(lats - args.lat).argmin())
    ilon = int(np.abs(lon_array - desired_lon).argmin())
    sel = sos.isel({lat_name: ilat, lon_name: ilon})

# If depth dimension present, reduce or select surface
if 'depth' in sel.dims:
    # prefer depth=0 if present
    try:
        sel = sel.sel(depth=0, method='nearest')
    except Exception:
        sel = sel.isel(depth=0)

# sel should now be a DataArray indexed by time
if 'time' not in sel.dims:
    # maybe time is the only dim or it's a scalar
    print(json.dumps({'error': 'no time dimension in selected sos array', 'selection_dims': list(sel.dims)}))
    sys.exit(6)

times = sel['time'].values
vals = sel.values

out = []
for t, v in zip(times, vals):
    try:
        t_iso = str(t.tolist())
    except Exception:
        t_iso = str(t)
    try:
        # ensure scalar
        if hasattr(v, 'item'):
            v_val = v.item()
        else:
            v_val = v
        v_f = float(v_val) if (v_val is not None and str(v_val).lower() != 'nan') else None
    except Exception:
        v_f = None
    out.append({'time': t_iso, 'sos': v_f})

meta = {
    'file': fn,
    'requested': {'lat': args.lat, 'lon': args.lon},
    'selected_point': {}
}
# report the actual grid point selected
actual_lat = float(sel.coords[lat_name].values)
actual_lon = float(sel.coords[lon_name].values)
meta['selected_point'][lat_name] = actual_lat
meta['selected_point'][lon_name] = actual_lon

print(json.dumps({'meta': meta, 'data': out}))
