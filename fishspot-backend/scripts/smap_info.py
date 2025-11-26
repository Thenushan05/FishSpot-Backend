"""
Fetch and print time coverage for noaacwSMAPsssDaily from the ERDDAP info page.
"""
import sys
from urllib.request import urlopen

URL = 'https://coastwatch.noaa.gov/erddap/info/noaacwSMAPsssDaily/index.html'
try:
    with urlopen(URL, timeout=30) as resp:
        text = resp.read().decode('utf-8')
except Exception as e:
    print('ERROR fetching info page:', e)
    sys.exit(1)

# look for time_coverage_start / end
for line in text.splitlines():
    if 'time_coverage_start' in line or 'time_coverage_end' in line or 'time_coverage' in line:
        print(line.strip())

# print a short snippet
print('\n--- snippet ---')
print('\n'.join(text.splitlines()[:40]))
