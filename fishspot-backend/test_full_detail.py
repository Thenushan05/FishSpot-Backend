"""Full detailed input/output inspection for every ML scenario."""
import sys, math, numpy as np, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '.')
from app.services.ml_hotspot import predict_cells
from app.services.monsoon_classifier import classify_monsoon

def make_cell(lat, lon, sst, ssh, chlo, sss, depth, species='YFT', month=3):
    dep_abs = abs(depth)
    ssd     = round(1025.0 + 0.8*(sss-35.0) - 0.2*(sst-25.0), 4)
    chlo_v  = max(chlo, 1e-6)
    monsoon_f = classify_monsoon(lat, lon, month)
    monsoon   = next((k for k,v in monsoon_f.items() if v==1), 'No_monsoon_region')
    return {
        # ── 23 model features ──
        'month':        month,
        'depth_abs':    dep_abs,
        'sss':          sss,
        'ssd':          ssd,
        'sst':          sst,
        'ssh':          ssh,
        'chlo':         chlo_v,
        'month_sin':    round(math.sin(2*math.pi*month/12), 6),
        'month_cos':    round(math.cos(2*math.pi*month/12), 6),
        'sst_x_chlo':   round(sst*chlo_v, 6),
        'ssh_x_chlo':   round(ssh*chlo_v, 6),
        'sst_x_ssh':    round(sst*ssh, 6),
        'depth_x_sst':  round(dep_abs*sst, 6),
        'depth_x_chlo': round(dep_abs*chlo_v, 6),
        'sst_squared':  round(sst**2, 6),
        'chlo_log':     round(float(np.log(chlo_v+1e-6)), 6),
        'sss_x_sst':    round(sss*sst, 6),
        'lat_sin':      round(math.sin(math.radians(lat)), 6),
        'lat_cos':      round(math.cos(math.radians(lat)), 6),
        'lon_sin':      round(math.sin(math.radians(lon)), 6),
        'lon_cos':      round(math.cos(math.radians(lon)), 6),
        'SPECIES_CODE': species,
        'monsoon':      monsoon,
        # ── originals for display ──
        'SST': sst, 'SSH': ssh, 'CHLO': chlo_v, 'SSS': sss,
        'SSD': ssd, 'DEPTH': -dep_abs, 'LAT': lat, 'LON': lon,
    }

scenarios = [
    # name,                              lat,  lon,  sst,  ssh,  chlo, sss,  depth, sp,    month
    ("Bay E  - warm elevated chlo",      7.5,  81.5, 29.5, 0.45, 0.35, 34.8, 180,  'YFT', 3),
    ("SW coast - upwelling zone",         6.0,  80.2, 27.0, 0.62, 0.55, 35.2, 120,  'YFT', 3),
    ("Deep ocean - pelagic",              8.5,  83.0, 28.8, 0.30, 0.12, 34.5, 850,  'YFT', 3),
    ("Shallow coastal - low chlo",        6.5,  80.0, 28.2, 0.15, 0.08, 34.0,  45,  'YFT', 3),
    ("Convergence - high chlo",           7.0,  82.0, 27.5, 0.70, 0.80, 35.5, 220,  'YFT', 3),
    ("Warm + low chlo (poor YFT)",        9.0,  84.0, 31.2, 0.20, 0.05, 34.2, 600,  'YFT', 3),
    ("BET deep cool thermocline",         7.5,  81.5, 26.5, 0.55, 0.28, 35.0, 400,  'BET', 3),
    ("SWO swordfish grounds",             8.0,  82.5, 28.0, 0.50, 0.22, 34.9, 300,  'SWO', 3),
    ("Bloom event very high chlo",        7.2,  80.9, 28.0, 0.65, 1.20, 35.3, 150,  'YFT', 3),
    ("Cold eddy low SST",                 7.8,  82.2, 25.5, 0.85, 0.45, 35.8, 280,  'YFT', 3),
    ("SW monsoon June YFT",               7.5,  81.5, 26.8, 0.75, 0.65, 35.4, 200,  'YFT', 6),
    ("NE monsoon Jan YFT",                7.5,  81.5, 27.5, 0.40, 0.20, 34.7, 200,  'YFT', 1),
]

cells   = [make_cell(*s[1:]) for s in scenarios]
results = predict_cells(cells)

SEP = "=" * 90

for i, ((name, lat, lon, sst, ssh, chlo, sss, depth, sp, month), cell, r) in enumerate(
        zip(scenarios, cells, results)):
    print(f"\n{SEP}")
    print(f"  SCENARIO {i+1}: {name}")
    print(SEP)
    print(f"  {'--- RAW INPUTS ---'}")
    print(f"  Location : lat={lat}, lon={lon}")
    print(f"  Month    : {month}  =>  monsoon = {cell['monsoon']}")
    print(f"  Species  : {sp}")
    print(f"  SST      : {sst} degC")
    print(f"  SSH      : {ssh} m")
    print(f"  CHLO     : {chlo} mg/m3")
    print(f"  SSS      : {sss} PSU")
    print(f"  SSD      : {cell['ssd']} kg/m3  (computed from SSS+SST via TEOS-10)")
    print(f"  Depth    : {depth} m")
    print()
    print(f"  {'--- ALL 23 MODEL FEATURES ---'}")
    feature_order = [
        'month','depth_abs','sss','ssd','sst','ssh','chlo',
        'month_sin','month_cos',
        'sst_x_chlo','ssh_x_chlo','sst_x_ssh','depth_x_sst','depth_x_chlo',
        'sst_squared','chlo_log','sss_x_sst',
        'lat_sin','lat_cos','lon_sin','lon_cos',
        'SPECIES_CODE','monsoon'
    ]
    for feat in feature_order:
        print(f"  {feat:<18} = {cell[feat]}")
    print()
    print(f"  {'--- MODEL OUTPUT ---'}")
    print(f"  Score (p_hotspot) : {r['score']:.4f}  ({r['score']*100:.1f}%)")
    print(f"  Confidence        : {r.get('p_hotspot', r['score'])*100:.1f}%")
    print(f"  Hotspot level     : {r['hotspot_level']}")
    level = r['hotspot_level']
    if level == 'core_hotspot':
        verdict = "HOTSPOT  (score >= 0.80)"
    elif level == 'candidate_hotspot':
        verdict = "CANDIDATE (score >= 0.60)"
    else:
        verdict = "Not a hotspot (score < 0.60)"
    print(f"  Verdict           : {verdict}")

print(f"\n{SEP}")
print("  SUMMARY TABLE")
print(f"  {'Scenario':<36} {'Sp':3} {'Mo':2}  {'Monsoon':<28} {'Score':>7}  Level")
print(f"  {'-'*95}")
for (name, lat, lon, sst, ssh, chlo, sss, depth, sp, month), cell, r in zip(scenarios, cells, results):
    mon_short = cell['monsoon'].replace('IO_','').replace('_monsoon','').replace('_Intermonsoon','_Intermonsoon')
    lvl = r['hotspot_level'].upper().replace('_HOTSPOT','').replace('NO_','—')
    print(f"  {name:<36} {sp:3} {month:2}  {cell['monsoon']:<28} {r['score']*100:>6.1f}%  {lvl}")
print(SEP)
