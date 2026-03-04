import sys, math, warnings
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')

from app.services.ml_hotspot import predict_cells

# --- raw inputs ---
month   = 6
sst     = 28.0
sss     = 34.8
ssd     = 1022.5
ssh     = 0.25
chlo    = 0.20
depth   = 2500.0
lat     = 7.5       # Sri Lanka area  IO_SW_monsoon in June
lon     = 81.5
monsoon = 'IO_SW_monsoon'
species = 'BET'

# --- engineered features (must match training pipeline) ---
cell = {
    'month':        month,
    'depth_abs':    abs(depth),
    'sss':          sss,
    'ssd':          ssd,
    'sst':          sst,
    'ssh':          ssh,
    'chlo':         chlo,
    'month_sin':    math.sin(2 * math.pi * month / 12),
    'month_cos':    math.cos(2 * math.pi * month / 12),
    'sst_x_chlo':   sst * chlo,
    'ssh_x_chlo':   ssh * chlo,
    'sst_x_ssh':    sst * ssh,
    'depth_x_sst':  depth * sst,
    'depth_x_chlo': depth * chlo,
    'sst_squared':  sst ** 2,
    'chlo_log':     math.log(chlo + 1e-6),
    'sss_x_sst':    sss * sst,
    'lat_sin':      math.sin(math.radians(lat)),
    'lat_cos':      math.cos(math.radians(lat)),
    'lon_sin':      math.sin(math.radians(lon)),
    'lon_cos':      math.cos(math.radians(lon)),
    'SPECIES_CODE': species,
    'monsoon':      monsoon,
}

results = predict_cells([cell])
r = results[0]

print()
print("============  BET PREDICTION  ============")
print(f"  Species       : {species}")
print(f"  Month         : {month} (June)")
print(f"  Location      : lat={lat}, lon={lon}")
print(f"  Monsoon       : {monsoon}")
print()
print(f"  SST           : {sst} C")
print(f"  SSS           : {sss} PSU")
print(f"  SSD           : {ssd} kg/m3")
print(f"  SSH           : {ssh} m")
print(f"  CHLO          : {chlo} mg/m3")
print(f"  Depth         : {depth} m")
print()
print(f"  --- Engineered Features ---")
print(f"  month_sin     : {cell['month_sin']:.4f}")
print(f"  month_cos     : {cell['month_cos']:.4f}")
print(f"  sst_x_chlo    : {cell['sst_x_chlo']:.4f}")
print(f"  ssh_x_chlo    : {cell['ssh_x_chlo']:.4f}")
print(f"  sst_x_ssh     : {cell['sst_x_ssh']:.4f}")
print(f"  depth_x_sst   : {cell['depth_x_sst']:.1f}")
print(f"  depth_x_chlo  : {cell['depth_x_chlo']:.1f}")
print(f"  sst_squared   : {cell['sst_squared']:.1f}")
print(f"  chlo_log      : {cell['chlo_log']:.4f}")
print(f"  sss_x_sst     : {cell['sss_x_sst']:.2f}")
print(f"  lat_sin/cos   : {cell['lat_sin']:.4f} / {cell['lat_cos']:.4f}")
print(f"  lon_sin/cos   : {cell['lon_sin']:.4f} / {cell['lon_cos']:.4f}")
print()
print(f"  >>> score        : {r['score']:.4f}")
print(f"  >>> hotspot_level: {r['hotspot_level']}")
print("==========================================")
print()
print("  Thresholds: core >= 0.80 | candidate >= 0.60 | no_hotspot < 0.60")
