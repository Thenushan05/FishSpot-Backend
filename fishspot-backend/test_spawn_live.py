"""
test_spawn_live.py
Quick test to show the spawn model running and producing results.
"""
import sys, math, warnings
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
warnings.filterwarnings("ignore")

from app.services import ml_hotspot

# 5 test points around east Sri Lanka
POINTS = [
    (7.5, 82.5, 120.0, 28.5, 0.18, 0.22, 34.8, 1023.4),
    (8.0, 82.5, 120.0, 28.8, 0.20, 0.19, 34.7, 1023.3),
    (7.5, 83.0,  80.0, 28.2, 0.19, 0.25, 34.9, 1023.5),
    (9.0, 82.0, 200.0, 27.8, 0.17, 0.18, 35.0, 1023.6),
    (8.5, 81.5,  50.0, 29.0, 0.21, 0.27, 34.6, 1023.2),
]

MONTH = 3
cells = []
for (lat, lon, depth, sst, ssh, chlo, sss, ssd) in POINTS:
    cells.append({
        "month": MONTH, "depth_abs": abs(depth), "sss": sss, "ssd": ssd,
        "sst": sst, "ssh": ssh, "chlo": chlo,
        "month_sin": math.sin(2 * math.pi * MONTH / 12),
        "month_cos": math.cos(2 * math.pi * MONTH / 12),
        "sst_x_chlo": sst * chlo, "ssh_x_chlo": ssh * chlo, "sst_x_ssh": sst * ssh,
        "depth_x_sst": abs(depth) * sst, "depth_x_chlo": abs(depth) * chlo,
        "sst_squared": sst ** 2, "chlo_log": math.log(chlo + 1e-6),
        "sss_x_sst": sss * sst,
        "lat_sin": math.sin(math.radians(lat)), "lat_cos": math.cos(math.radians(lat)),
        "lon_sin": math.sin(math.radians(lon)), "lon_cos": math.cos(math.radians(lon)),
        "SPECIES_CODE": "SKJ", "monsoon": "IO_NE_monsoon",
        "LAT": lat, "LON": lon, "DEPTH": depth,
        "SST": sst, "SSH": ssh, "CHLO": chlo, "SSS": sss, "SSD": ssd,
    })

print()
print("=" * 80)
print("  Running predict_cells() with 5 points (spawn model now wired in)")
print("=" * 80)
results = ml_hotspot.predict_cells(cells)

print()
print("=" * 80)
print("  FINAL COMBINED RESULTS")
print("=" * 80)
print(f"  {'LAT':>5} {'LON':>6}  {'HOTSPOT_SCORE':>13}  {'LEVEL':<22}  {'SPAWN_PROB':>10}  SPAWNING")
print("  " + "-" * 76)
for r in results:
    spawn_flag = "YES  <-- spawning!" if r["spawning"] else "no"
    sp = r["spawn_probability"]
    print(
        f"  {r['LAT']:>5.1f} {r['LON']:>6.1f}  "
        f"{r['score']:>13.4f}  "
        f"{r['hotspot_level']:<22}  "
        f"{(sp if sp is not None else 0.0):>10.4f}  "
        f"{spawn_flag}"
    )
print()
