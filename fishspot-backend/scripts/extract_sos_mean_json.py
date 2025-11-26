import xarray as xr
import json
import os
import glob
import sys
import pandas as pd

# Script expects to be run from repo root: D:/Fish-Full/Backend/fishspot-backend
root = os.getcwd()
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
# Mean over spatial dims (latitude, longitude). Some datasets may use 'lat'/'lon' or 'latitude'/'longitude'.
spatial_dims = [d for d in ('latitude','longitude','lat','lon') if d in sos.dims]
if not spatial_dims:
    print(json.dumps({'error': 'no spatial dims found on sos variable', 'dims': list(sos.dims)}))
    sys.exit(5)

# Reduce over lat & lon and depth (if present) to get a time series
reduce_dims = [d for d in ('latitude','longitude','depth') if d in sos.dims]
mean_ts = sos.mean(dim=tuple(reduce_dims))

# Extract times and values
times = mean_ts['time'].values
vals = mean_ts.values

out = []
for t, v in zip(times, vals):
    # convert numpy types to python primitives
    try:
        t_iso = pd.to_datetime(t).isoformat()
    except Exception:
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
    out.append({'time': t_iso, 'mean_sos': v_f})

print(json.dumps(out))
