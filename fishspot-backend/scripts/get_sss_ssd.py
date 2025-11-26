"""
Find SSS (SMAP/SMOS) and SST for a point/date and compute sea-surface density (SSD) if possible.
Usage: python scripts/get_sss_ssd.py <date> <lat> <lon>
Defaults: date=2024-11-11 lat=9.961524 lon=79.701832
"""
from datetime import date, timedelta
import sys
import urllib.request
import csv

ERDDAP_GRIDDAP_BASE = "https://coastwatch.noaa.gov/erddap/griddap"

SSS_DS = ["noaacwSMAPsssDaily", "noaacwSMOSsssDaily", "noaacwSMOSsss3day"]
SST_DS = ["noaacwBLENDEDsstDaily", "noaacwecnMURdaily", "noaacwMURdaily", "noaacwBLENDEDsstDLDaily"]


def fetch_var(ds_id, var, date_str, lat, lon, box=0.1):
    lat_min = lat - box
    lat_max = lat + box
    lon_min = lon - box
    lon_max = lon + box
    # try without altitude then with altitude if needed (use %-format to avoid f-string brace issues)
    urls = []
    q1 = "?%s[(%sT12:00:00Z):(%sT12:00:00Z)][(%f):(%f)][(%f):(%f)]" % (
        var, date_str, date_str, lat_min, lat_max, lon_min, lon_max
    )
    q2 = "?%s[(%sT12:00:00Z):(%sT12:00:00Z)][(0):(0)][(%f):(%f)][(%f):(%f)]" % (
        var, date_str, date_str, lat_min, lat_max, lon_min, lon_max
    )
    urls.append(f"{ERDDAP_GRIDDAP_BASE}/{ds_id}.csv" + q1)
    urls.append(f"{ERDDAP_GRIDDAP_BASE}/{ds_id}.csv" + q2)

    for url in urls:
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                text = resp.read().decode('utf-8')
        except Exception as e:
            # return error detail to caller
            return {'error': str(e), 'url': url}
        lines = [l for l in text.splitlines() if l.strip() and not l.startswith('#')]
        if not lines:
            return {'dataset': ds_id, 'value': None, 'url': url}
        reader = csv.DictReader(lines)
        rows = list(reader)
        if not rows:
            return {'dataset': ds_id, 'value': None, 'url': url}
        best = None
        bestd = None
        for r in rows:
            try:
                rlat = float(r.get('latitude') or r.get('lat') or r.get('LAT'))
                rlon = float(r.get('longitude') or r.get('lon') or r.get('LON'))
                # find variable key
                val = None
                for k in r.keys():
                    if k.lower().startswith(var.lower()):
                        val = r[k]
                        break
                if val is None:
                    for k, v in r.items():
                        if k.lower() in ('latitude', 'longitude', 'time', 'altitude'):
                            continue
                        try:
                            _ = float(v)
                            val = v
                            break
                        except Exception:
                            continue
                valf = float(val)
            except Exception:
                continue
            d2 = (rlat - lat) ** 2 + (rlon - lon) ** 2
            if best is None or d2 < bestd:
                best = (rlat, rlon, valf)
                bestd = d2
        if best is None:
            return {'dataset': ds_id, 'value': None, 'url': url}
        return {'dataset': ds_id, 'lat': best[0], 'lon': best[1], 'value': best[2], 'url': url}


def gen_dates(center: date, days_before=3, days_after=3):
    dates = []
    for d in range(-days_before, days_after + 1):
        dates.append((center + timedelta(days=d)).isoformat())
    return dates


def find_sss_and_sst(center_date_str, lat, lon):
    center = date.fromisoformat(center_date_str)
    dates = gen_dates(center, days_before=3, days_after=3)
    boxes = [0.1, 0.25, 0.5]

    res = {'sss': None, 'sst': None}

    for dt in dates:
        if not res['sss']:
            for ds in SSS_DS:
                if res['sss']:
                    break
                for b in boxes:
                    r = fetch_var(ds, 'sss', dt, lat, lon, box=b)
                    print(f"Tried SSS {ds} date={dt} box={b} -> {r.get('value') if 'value' in r else r.get('error')}")
                    if r.get('value') is not None and str(r.get('value')).lower() != 'nan':
                        res['sss'] = {'date': dt, 'dataset': ds, 'lat': r.get('lat'), 'lon': r.get('lon'), 'value': r.get('value'), 'url': r.get('url')}
                        break
        if not res['sst']:
            for ds in SST_DS:
                if res['sst']:
                    break
                for b in boxes:
                    r = fetch_var(ds, 'sst', dt, lat, lon, box=b)
                    print(f"Tried SST {ds} date={dt} box={b} -> {r.get('value') if 'value' in r else r.get('error')}")
                    if r.get('value') is not None and str(r.get('value')).lower() != 'nan':
                        res['sst'] = {'date': dt, 'dataset': ds, 'lat': r.get('lat'), 'lon': r.get('lon'), 'value': r.get('value'), 'url': r.get('url')}
                        break
        if res['sss'] and res['sst']:
            break
    return res


def compute_density_if_possible(sss_val, sst_val, lat, lon):
    # Attempt to compute density using gsw
    try:
        import gsw
    except Exception as e:
        return {'error': 'gsw not installed', 'detail': str(e)}
    p = 0.0  # sea-surface pressure in dbar
    SA = gsw.SA_from_SP(sss_val, p, lon, lat)
    CT = gsw.CT_from_t(SA, sst_val, p)
    rho = gsw.rho(SA, CT, p)
    return {'rho': float(rho)}


if __name__ == '__main__':
    if len(sys.argv) >= 4:
        dt = sys.argv[1]
        lat = float(sys.argv[2])
        lon = float(sys.argv[3])
    else:
        dt = '2024-11-11'
        lat = 9.961524
        lon = 79.701832

    out = find_sss_and_sst(dt, lat, lon)
    print('\nFOUND:')
    print(out)

    if out['sss'] and out['sst']:
        sss_val = out['sss']['value']
        sst_val = out['sst']['value']
        dens = compute_density_if_possible(sss_val, sst_val, out['sss']['lat'], out['sss']['lon'])
        print('\nDENSITY_CALC:')
        print(dens)
    else:
        print('\nNot enough data to compute density. If you want density, install gsw and ensure SSS+SST found.')
