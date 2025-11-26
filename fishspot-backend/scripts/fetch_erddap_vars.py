"""
Search ERDDAP for datasets containing variables and fetch nearest gridpoint values.
Usage: python scripts/fetch_erddap_vars.py <date> <lat> <lon>
If date is omitted, defaults to 2024-11-11 (example date where chlor_a exists near point).
"""
import sys
import csv
import urllib.request
from pathlib import Path

ERDDAP_SEARCH = "https://coastwatch.noaa.gov/erddap/search/index.csv"
ERDDAP_GRIDDAP_BASE = "https://coastwatch.noaa.gov/erddap/griddap"

VARS = ["sst", "sss", "ssd", "chlor_a"]


def search_datasets(var, max_results=20):
    q = f"{ERDDAP_SEARCH}?searchFor={var}&itemsPerPage={max_results}"
    try:
        with urllib.request.urlopen(q, timeout=20) as resp:
            text = resp.read().decode("utf-8")
    except Exception as e:
        print(f"Search failed for {var}: {e}")
        return []
    lines = [l for l in text.splitlines() if l.strip()]
    # first line is header
    reader = csv.DictReader(lines)
    results = []
    for r in reader:
        # datasetID and datasetType columns are present in ERDDAP search index CSV
        ds = r.get('Dataset ID') or r.get('datasetID') or r.get('DatasetID') or r.get('Dataset')
        title = r.get('Title') or r.get('title')
        if ds:
            results.append({'id': ds, 'title': title})
    return results


def try_fetch_from_dataset(ds_id, var, date, lat, lon, box=0.1):
    lat_min = lat - box
    lat_max = lat + box
    lon_min = lon - box
    lon_max = lon + box
    # include altitude axis (0):(0) to be safe — many datasets have altitude dimension
    query = (
        f"?{var}[({date}T12:00:00Z):({date}T12:00:00Z)]"
        f"[(0):(0)]"
        f"[({lat_min}):({lat_max})]"
        f"[({lon_min}):({lon_max})]"
    )
    url = f"{ERDDAP_GRIDDAP_BASE}/{ds_id}.csv" + query
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            text = resp.read().decode('utf-8')
    except Exception as e:
        return {'error': str(e), 'dataset': ds_id}
    lines = [l for l in text.splitlines() if l.strip() and not l.startswith('#')]
    if not lines:
        return {'dataset': ds_id, 'value': None}
    reader = csv.DictReader(lines)
    rows = list(reader)
    if not rows:
        return {'dataset': ds_id, 'value': None}
    best = None
    bestd = None
    for r in rows:
        try:
            rlat = float(r.get('latitude') or r.get('lat') or r.get('LAT'))
            rlon = float(r.get('longitude') or r.get('lon') or r.get('LON'))
            val = r.get(var) or r.get(var.upper())
            if val is None:
                # try to find variable in other keys
                for k in r.keys():
                    if k.lower().startswith(var.lower()):
                        val = r[k]
                        break
            valf = float(val)
        except Exception:
            continue
        d2 = (rlat - lat) ** 2 + (rlon - lon) ** 2
        if best is None or d2 < bestd:
            best = (rlat, rlon, valf)
            bestd = d2
    if best is None:
        return {'dataset': ds_id, 'value': None}
    return {'dataset': ds_id, 'lat': best[0], 'lon': best[1], 'value': best[2]}


if __name__ == '__main__':
    if len(sys.argv) >= 4:
        date = sys.argv[1]
        lat = float(sys.argv[2])
        lon = float(sys.argv[3])
    else:
        date = '2024-11-11'
        lat = 9.961524
        lon = 79.701832

    out = {}
    for var in VARS:
        print(f"Searching for variable: {var}")
        datasets = search_datasets(var, max_results=50)
        if not datasets:
            print(f"No search results for {var}")
            out[var] = {'found': False}
            continue
        # try top candidates
        found = None
        for ds in datasets:
            dsid = ds['id']
            # attempt to fetch from this dataset
            res = try_fetch_from_dataset(dsid, var, date, lat, lon, box=0.1)
            print(f"Tried {dsid} -> {res.get('value') if 'value' in res else res.get('error')}")
            if res.get('value') is not None and str(res.get('value')).lower() != 'nan':
                found = res
                found['dataset'] = dsid
                break
        if found is None:
            out[var] = {'found': False}
        else:
            out[var] = {'found': True, 'dataset': found.get('dataset'), 'lat': found.get('lat'), 'lon': found.get('lon'), 'value': found.get('value')}

    print('\nSUMMARY:')
    for k, v in out.items():
        print(k, v)
