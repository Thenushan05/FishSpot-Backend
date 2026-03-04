import sys, math, warnings
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')

from app.services.ml_hotspot import predict_cells

SPECIES = 'BET'

cases = [
    dict(label="SL-1", lat=6.0, lon=83.0, year=2020, month=6,  monsoon='IO_SW_monsoon',          depth=4200, sst=28.9, sss=34.6, ssd=1024.2, ssh=0.42, chlo=0.36),
    dict(label="SL-2", lat=6.5, lon=82.0, year=2020, month=7,  monsoon='IO_SW_monsoon',          depth=3200, sst=28.7, sss=34.7, ssd=1024.3, ssh=0.35, chlo=0.28),
    dict(label="SL-3", lat=5.8, lon=81.2, year=2020, month=9,  monsoon='IO_SW_monsoon',          depth=2500, sst=28.4, sss=34.8, ssd=1024.4, ssh=0.28, chlo=0.22),
    dict(label="SL-4", lat=7.2, lon=81.8, year=2020, month=10, monsoon='IO_Second_Intermonsoon', depth=2200, sst=28.1, sss=34.8, ssd=1024.5, ssh=0.25, chlo=0.18),
    dict(label="SL-5", lat=7.8, lon=80.8, year=2020, month=11, monsoon='IO_Second_Intermonsoon', depth=1800, sst=27.8, sss=34.9, ssd=1024.6, ssh=0.22, chlo=0.14),
    dict(label="SL-6", lat=8.5, lon=80.5, year=2020, month=1,  monsoon='IO_NE_monsoon',          depth=1200, sst=26.8, sss=35.2, ssd=1024.8, ssh=0.18, chlo=0.10),
    dict(label="SL-7", lat=9.2, lon=79.8, year=2020, month=2,  monsoon='IO_NE_monsoon',          depth=900,  sst=26.5, sss=35.3, ssd=1024.9, ssh=0.15, chlo=0.08),
    dict(label="SL-8", lat=6.8, lon=82.5, year=2020, month=4,  monsoon='IO_First_Intermonsoon',  depth=2800, sst=27.6, sss=34.9, ssd=1024.6, ssh=0.24, chlo=0.16),
]


def build_cell(c):
    month = c['month']
    sst   = c['sst']
    sss   = c['sss']
    ssd   = c['ssd']
    ssh   = c['ssh']
    chlo  = c['chlo']
    depth = c['depth']
    lat   = c['lat']
    lon   = c['lon']
    return {
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
        'SPECIES_CODE': SPECIES,
        'monsoon':      c['monsoon'],
    }


THRESHOLD = 0.60

def confidence_label(score):
    if score >= THRESHOLD:
        return "HOTSPOT    (>= 0.60)"
    else:
        return "NO HOTSPOT (<  0.60)"


cells   = [build_cell(c) for c in cases]
results = predict_cells(cells)

print()
print("=" * 62)
print(f"  BET PREDICTION  |  Species: {SPECIES}")
print("=" * 62)
print(f"  {'Case':<14} {'Score':>7}  {'Confidence':<28}  {'Level'}")
print(f"  {'-'*13} {'-'*7}  {'-'*28}  {'-'*20}")

for c, r in zip(cases, results):
    score = r['score']
    bar_filled = int(score * 20)
    result = 'HOTSPOT' if score >= THRESHOLD else 'NO HOTSPOT'
    bar = '[' + '#' * bar_filled + '.' * (20 - bar_filled) + ']'
    print(f"  {c['label']:<14} {score:>6.4f}  {bar}  {result}")

print()
print(" Detail per case:")
print()

for c, r in zip(cases, results):
    score = r['score']
    print(f"  Case {c['label']}")
    print(f"    lat={c['lat']}, lon={c['lon']}, month={c['month']}, monsoon={c['monsoon']}")
    print(f"    SST={c['sst']}C  SSS={c['sss']}PSU  SSD={c['ssd']}  SSH={c['ssh']}m  CHLO={c['chlo']}mg/m3  depth={c['depth']}m")
    print(f"    Score      : {score:.4f}")
    print(f"    Confidence : {confidence_label(score)}")
    result = 'HOTSPOT' if score >= THRESHOLD else 'NO HOTSPOT'
    print(f"    Result     : {result}")
    print()

print("  Threshold: score >= 0.60 = HOTSPOT | score < 0.60 = NO HOTSPOT")
print("=" * 62)
