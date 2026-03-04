"""Test ML model with realistic Sri Lanka ocean scenarios."""
import sys, math, numpy as np
sys.path.insert(0, '.')
from app.services.ml_hotspot import predict_cells
from app.services.monsoon_classifier import classify_monsoon

def make_cell(lat, lon, sst, ssh, chlo, sss, depth, species='YFT'):
    month   = 3  # March
    dep_abs = abs(depth)
    ssd     = 1025.0 + 0.8 * (sss - 35.0) - 0.2 * (sst - 25.0)
    chlo_v  = max(chlo, 1e-6)
    monsoon_f = classify_monsoon(lat, lon, month)
    monsoon   = next((k for k, v in monsoon_f.items() if v == 1), 'No_monsoon_region')
    return {
        'month': month, 'depth_abs': dep_abs, 'sss': sss, 'ssd': ssd,
        'sst': sst, 'ssh': ssh, 'chlo': chlo_v,
        'month_sin':  math.sin(2 * math.pi * month / 12),
        'month_cos':  math.cos(2 * math.pi * month / 12),
        'sst_x_chlo':  sst * chlo_v,  'ssh_x_chlo':  ssh * chlo_v,
        'sst_x_ssh':   sst * ssh,     'depth_x_sst': dep_abs * sst,
        'depth_x_chlo': dep_abs * chlo_v,
        'sst_squared': sst ** 2,
        'chlo_log':    np.log(chlo_v + 1e-6),
        'sss_x_sst':   sss * sst,
        'lat_sin': math.sin(math.radians(lat)),
        'lat_cos': math.cos(math.radians(lat)),
        'lon_sin': math.sin(math.radians(lon)),
        'lon_cos': math.cos(math.radians(lon)),
        'SPECIES_CODE': species, 'monsoon': monsoon,
        'SST': sst, 'SSH': ssh, 'CHLO': chlo_v, 'SSS': sss,
        'SSD': ssd, 'DEPTH': -depth, 'LAT': lat, 'LON': lon,
    }

# (name, lat, lon, sst, ssh, chlo, sss, depth_m, species)
scenarios = [
    ("Bay NE  - warm + elevated chlo",    7.5, 81.5, 29.5, 0.45, 0.35, 34.8, 180, 'YFT'),
    ("SW coast - upwelling zone",          6.0, 80.2, 27.0, 0.62, 0.55, 35.2, 120, 'YFT'),
    ("Deep ocean - pelagic",               8.5, 83.0, 28.8, 0.30, 0.12, 34.5, 850, 'YFT'),
    ("Shallow coastal - low chlo",         6.5, 80.0, 28.2, 0.15, 0.08, 34.0,  45, 'YFT'),
    ("Convergence zone - high chlo",       7.0, 82.0, 27.5, 0.70, 0.80, 35.5, 220, 'YFT'),
    ("Warm + low chlo (poor)",             9.0, 84.0, 31.2, 0.20, 0.05, 34.2, 600, 'YFT'),
    ("BET - deep cool",                    7.5, 81.5, 26.5, 0.55, 0.28, 35.0, 400, 'BET'),
    ("SWO - swordfish grounds",            8.0, 82.5, 28.0, 0.50, 0.22, 34.9, 300, 'SWO'),
    ("Bloom event - very high chlo",       7.2, 80.9, 28.0, 0.65, 1.20, 35.3, 150, 'YFT'),
    ("Cold eddy - low SST",                7.8, 82.2, 25.5, 0.85, 0.45, 35.8, 280, 'YFT'),
]

cells   = [make_cell(*s[1:]) for s in scenarios]
results = predict_cells(cells)

RESET  = "\033[0m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"

def color(level):
    if level == 'core_hotspot':      return GREEN
    if level == 'candidate_hotspot': return YELLOW
    return RED

print()
print(f"{'Scenario':<36} {'Sp':3} {'Lat':>5} {'Lon':>6} {'SST':>5} {'CHLO':>6} {'Depth':>6}  {'Score':>7}  Level")
print("-" * 100)
for (name, lat, lon, sst, ssh, chlo, sss, depth, sp), r in zip(scenarios, results):
    c = color(r['hotspot_level'])
    bar = int(r['score'] * 20) * '#'
    print(f"{name:<36} {sp:3} {lat:>5.1f} {lon:>6.1f} {sst:>5.1f} {chlo:>6.2f} {depth:>6}m  "
          f"{c}{r['score']:>6.1%}{RESET}  {c}{r['hotspot_level']:<20}{RESET}  [{bar:<20}]")
print()
