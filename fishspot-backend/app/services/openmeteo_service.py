"""Open-Meteo Marine API helper for backend.

Provides a small helper to fetch hourly `sea_surface_temperature` and
`sea_level_height_msl` for lists of lat/lon points. Returns per-point
mean values (in memory) — no files are written.
"""
from typing import List, Dict, Tuple
import math
import requests_cache
import openmeteo_requests
from retry_requests import retry


def _safe_mean_from_response(r, var_index: int):
    try:
        hourly = r.Hourly()
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


def get_sst_ssh_for_points(lats: List[float], lons: List[float], retries: int = 3) -> List[Dict[str, float]]:
    """Query Open-Meteo Marine API for each lat/lon and return list of dicts:
    [{'sst': float|None, 'ssh': float|None}, ...]
    """
    if len(lats) != len(lons):
        raise ValueError("lats and lons must be same length")

    session = requests_cache.CachedSession('.cache', expire_after=3600)
    sess = retry(session, retries=retries, backoff_factor=0.2)
    client = openmeteo_requests.Client(session=sess)

    out = []
    for lat, lon in zip(lats, lons):
        try:
            params = {
                'latitude': float(lat),
                'longitude': float(lon),
                'hourly': ['sea_surface_temperature', 'sea_level_height_msl'],
                'utm_source': 'fishspot-backend',
            }
            responses = client.weather_api('https://marine-api.open-meteo.com/v1/marine', params=params)
            if not responses:
                out.append({'sst': None, 'ssh': None})
                continue
            r = responses[0]
            sst = _safe_mean_from_response(r, 0)
            ssh = _safe_mean_from_response(r, 1)
            out.append({'sst': sst, 'ssh': ssh})
        except Exception:
            out.append({'sst': None, 'ssh': None})
    return out
