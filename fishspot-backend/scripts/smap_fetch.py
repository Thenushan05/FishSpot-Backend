"""
Fetch SMAP SSS CSV for a given date and lat/lon box and print a short summary.
Usage: python scripts/smap_fetch.py 2025-01-01
Defaults to date 2025-01-01 if no arg provided.
"""
import sys
from urllib.request import urlopen
import csv
from io import StringIO

def fetch_smap_sss(date='2025-01-01', lat_min=3, lat_max=12, lon_min=78, lon_max=84):
    base = 'https://coastwatch.noaa.gov/erddap/griddap/noaacwSMAPsssDaily.csv'
    query = (
        f"?sss[({date}T12:00:00Z):({date}T12:00:00Z)]"
        f"[({lat_min}):({lat_max})]"
        f"[({lon_min}):({lon_max})]"
    )
    url = base + query
    print('Fetching URL:', url)
    try:
        with urlopen(url, timeout=60) as resp:
            text = resp.read().decode('utf-8')
    except Exception as e:
        print('ERROR fetching:', e)
        return None

    # parse CSV (skip comment lines starting with '#')
    lines = [l for l in text.splitlines() if l.strip() and not l.startswith('#')]
    if not lines:
        print('No data returned')
        return None
    reader = csv.DictReader(lines)
    rows = list(reader)
    if not rows:
        print('No rows in CSV')
        return None

    # print head
    print('\nFirst 8 rows:')
    for r in rows[:8]:
        print(r)

    # summary: count non-nan values for 'sss'
    valid = 0
    total = 0
    for r in rows:
        total += 1
        v = None
        for k in r.keys():
            if k.lower().startswith('sss'):
                v = r[k]
                break
        try:
            vf = float(v)
            if str(vf).lower() != 'nan':
                valid += 1
        except Exception:
            pass
    print(f'\nRows returned: {total}, valid sss values: {valid}')
    return rows

if __name__ == '__main__':
    date = sys.argv[1] if len(sys.argv) > 1 else '2025-01-01'
    fetch_smap_sss(date)
