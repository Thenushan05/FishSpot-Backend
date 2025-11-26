"""Depth lookup service using the provided GEBCO NetCDF file.

This module exposes `get_depth(lat, lon)` which returns the nearest
grid depth/elevation value from the NetCDF file located under
`data/depth/GEBCO_2025_sub_ice.nc`.

Notes:
- The code attempts to auto-detect the depth variable name (e.g. 'elevation', 'depth').
- Handles longitude conventions (0-360 vs -180..180) when necessary.
"""
from pathlib import Path
from typing import Tuple, Any, Optional
import xarray as xr
import numpy as np

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "depth" / "GEBCO_2025_sub_ice.nc"


def _find_coord_names(ds: xr.Dataset) -> Tuple[Optional[str], Optional[str]]:
    lat_name = None
    lon_name = None
    for candidate in ("lat", "latitude", "y"):
        if candidate in ds.coords or candidate in ds.dims:
            lat_name = candidate
            break
    for candidate in ("lon", "longitude", "x"):
        if candidate in ds.coords or candidate in ds.dims:
            lon_name = candidate
            break
    return lat_name, lon_name


def _find_depth_var(ds: xr.Dataset) -> Optional[str]:
    names = list(ds.data_vars.keys())
    lower = [n.lower() for n in names]
    for target in ("elevation", "depth", "z", "bathymetry", "altitude", "gebco_elevation"):
        if any(target in n for n in lower):
            return names[lower.index(next(n for n in lower if target in n))]
    # fallback: return first numeric data var
    for n in names:
        if np.issubdtype(ds[n].dtype, np.number):
            return n
    return None


def get_depth(lat: float, lon: float) -> dict:
    """Return depth/elevation at nearest grid point for given lat, lon.

    Returns a dict: { 'value': float|None, 'var': varname, 'lat': grid_lat, 'lon': grid_lon }
    """
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Depth NetCDF not found at {DATA_PATH}")

    ds = xr.open_dataset(DATA_PATH)
    try:
        lat_name, lon_name = _find_coord_names(ds)
        if lat_name is None or lon_name is None:
            raise RuntimeError(f"Could not find lat/lon coords in dataset: {list(ds.coords.keys())}")

        varname = _find_depth_var(ds)
        if varname is None:
            raise RuntimeError("Could not detect a depth variable in NetCDF")

        lons = ds[lon_name].values
        # handle 0..360 lon arrays
        lon_in = lon
        if lons.max() > 180 and lon < 0:
            lon_in = lon % 360

        sel = ds[varname].sel({lat_name: lat, lon_name: lon_in}, method="nearest")
        val = sel.values
        grid_lat = float(sel.coords[lat_name].values)
        grid_lon = float(sel.coords[lon_name].values)
        # ensure scalar
        if hasattr(val, 'item'):
            val = val.item()
        # Cast to float or None
        try:
            v = None if np.isnan(val) else float(val)
        except Exception:
            v = None

        return {"value": v, "var": varname, "lat": grid_lat, "lon": grid_lon}
    finally:
        try:
            ds.close()
        except Exception:
            pass
