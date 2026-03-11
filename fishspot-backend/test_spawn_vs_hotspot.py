"""
test_spawn_vs_hotspot.py
========================
Uses the SAME lat/lon grid and oceanography inputs as new_xgb_trained
and checks whether those predicted hotspots are also spawn spots.

Grid: 5×5 = 25 points around east Sri Lanka (same region as test_5points.py)
Month: March 2026 (month=3)
"""

import sys, os, math, pickle
sys.path.insert(0, '.')

import numpy as np
import pandas as pd
import joblib
from pathlib import Path

# ── Load models ───────────────────────────────────────────────────────────────
HOTSPOT_MODEL_PATH = Path("app/ml/new_xgb_trained_random_ts20260214_084749.joblib")
SPAWN_MODEL_PATH   = Path("app/ml/spawn/xgboost_spawn_model (2).pkl")

print("🔄 Loading hotspot model ...")
hotspot_model = joblib.load(HOTSPOT_MODEL_PATH)
print("✅ Hotspot model loaded")

print("🔄 Loading spawn model ...")
with open(SPAWN_MODEL_PATH, "rb") as f:
    spawn_model = pickle.load(f)
print("✅ Spawn model loaded")

# ── Grid definition ───────────────────────────────────────────────────────────
LATS = [7.5, 8.0, 8.5, 9.0, 9.5]
LONS = [81.5, 82.0, 82.5, 83.0, 83.5]

MONTH       = 3                  # March
SPECIES     = "SKJ"              # Skipjack Tuna – highest model importance
MONSOON     = "IO_NE_monsoon"    # Indian Ocean NE monsoon (Oct–Mar)

# Typical oceanography for east Sri Lanka – March
# (same values that would come from the free ocean data service)
TYPICAL = dict(
    sst   = 28.5,   # °C  – warm equatorial water
    ssh   = 0.18,   # m
    chlo  = 0.22,   # mg/m3
    sss   = 34.8,   # PSU
    ssd   = 1023.4, # kg/m3
    depth = 120.0,  # m  (continental-shelf edge)
)

# Small spatial variation to mimic real per-point differences
SST_NOISE  = [ 0.0,  0.3, -0.2,  0.5, -0.4]
SSH_NOISE  = [ 0.0,  0.02,-0.01, 0.03,-0.02]
CHLO_NOISE = [ 0.0,  0.05,-0.03, 0.10,-0.02]
SSS_NOISE  = [ 0.0, -0.1,  0.2, -0.2,  0.1]
SSD_NOISE  = [ 0.0, -0.1,  0.1, -0.2,  0.1]
DEPTH_VARS = [80, 120, 200, 50, 300]   # varying depths across lons

# Monsoon numeric encoding for spawn model
# (IO_NE=0, IO_SW=1, IO_First_Inter=2, IO_Second_Inter=3)
MONSOON_ENC_MAP = {
    "IO_NE_monsoon": 0,
    "IO_SW_monsoon": 1,
    "IO_First_Intermonsoon": 2,
    "IO_Second_Intermonsoon": 3,
    "No_monsoon_region": 4,
}

# ── Feature engineering helpers ───────────────────────────────────────────────
def monsoon_enc(mon_str: str) -> int:
    return MONSOON_ENC_MAP.get(mon_str, 4)

def build_hotspot_row(lat, lon, depth, sss, ssd, sst, ssh, chlo):
    """Build a single-row dict with all 25 features for new_xgb_trained."""
    month_sin = math.sin(2 * math.pi * MONTH / 12)
    month_cos = math.cos(2 * math.pi * MONTH / 12)
    depth_abs = abs(depth)

    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    return {
        "month":       MONTH,
        "depth_abs":   depth_abs,
        "sss":         sss,
        "ssd":         ssd,
        "sst":         sst,
        "ssh":         ssh,
        "chlo":        chlo,
        "month_sin":   month_sin,
        "month_cos":   month_cos,
        # interaction features
        "sst_x_chlo":  sst * chlo,
        "ssh_x_chlo":  ssh * chlo,
        "sst_x_ssh":   sst * ssh,
        "depth_x_sst": depth_abs * sst,
        "depth_x_chlo":depth_abs * chlo,
        "sst_squared": sst ** 2,
        "chlo_log":    math.log(max(chlo, 1e-6)),
        "sss_x_sst":   sss * sst,
        # cyclic lat/lon
        "lat_sin":     math.sin(lat_rad),
        "lat_cos":     math.cos(lat_rad),
        "lon_sin":     math.sin(lon_rad),
        "lon_cos":     math.cos(lon_rad),
        # categorical
        "SPECIES_CODE": SPECIES,
        "monsoon":      MONSOON,
    }

def build_spawn_row(lat, lon, depth, sss, ssd, sst, ssh, chlo):
    """Build a single-row dict for the spawn model."""
    month_sin = math.sin(2 * math.pi * MONTH / 12)
    month_cos = math.cos(2 * math.pi * MONTH / 12)

    return {
        "lat":                    lat,
        "lon":                    lon,
        "depth":                  depth,
        "sss":                    sss,
        "ssd":                    ssd,
        "sst":                    sst,
        "ssh":                    ssh,
        "chlo":                   chlo,
        "month_sin":              month_sin,
        "month_cos":              month_cos,
        "monsoon_enc":            monsoon_enc(MONSOON),
        "lat_sst_interaction":    lat  * sst,
        "lon_sst_interaction":    lon  * sst,
        "depth_chlo_interaction": depth * chlo,
        "sss_sst_interaction":    sss  * sst,
    }

# ── Build the 25-point grid ───────────────────────────────────────────────────
def build_grid(species_code):
    hotspot_rows, spawn_rows, coords = [], [], []
    for i, lon in enumerate(LONS):
        for j, lat in enumerate(LATS):
            sst   = TYPICAL["sst"]   + SST_NOISE[i]
            ssh   = TYPICAL["ssh"]   + SSH_NOISE[i]
            chlo  = max(TYPICAL["chlo"]  + CHLO_NOISE[i], 0.01)
            sss   = TYPICAL["sss"]   + SSS_NOISE[i]
            ssd   = TYPICAL["ssd"]   + SSD_NOISE[i]
            depth = DEPTH_VARS[i]

            hr = build_hotspot_row(lat, lon, depth, sss, ssd, sst, ssh, chlo)
            hr["SPECIES_CODE"] = species_code
            hotspot_rows.append(hr)
            spawn_rows.append(build_spawn_row(lat, lon, depth, sss, ssd, sst, ssh, chlo))
            coords.append((lat, lon))
    return hotspot_rows, spawn_rows, coords

# Run for the two most important species
SPECIES_LIST = ["SKJ", "YFT"]

all_results = {}
for sp in SPECIES_LIST:
    hotspot_rows, spawn_rows, coords = build_grid(sp)
    X_hotspot = pd.DataFrame(hotspot_rows)
    X_spawn   = pd.DataFrame(spawn_rows)

    import warnings; warnings.filterwarnings("ignore")
    hp      = hotspot_model.predict_proba(X_hotspot)[:, 1]
    sp_prob = spawn_model.predict_proba(X_spawn)[:, 1]
    all_results[sp] = (coords, hp, sp_prob)

# ── Display results per species ───────────────────────────────────────────────
def classify_hotspot(p):
    if p >= 0.80: return "CORE_HOTSPOT"
    if p >= 0.60: return "candidate_hotspot"
    return "no_hotspot"

print()
for species_code in SPECIES_LIST:
    coords, hotspot_probs, spawn_probs = all_results[species_code]

    results = []
    for (lat, lon), hp, sp in zip(coords, hotspot_probs, spawn_probs):
        results.append({
            "lat": lat, "lon": lon,
            "hotspot_prob":  round(float(hp), 4),
            "hotspot_level": classify_hotspot(hp),
            "spawn_prob":    round(float(sp), 4),
            "is_spawn_spot": sp >= 0.50,
        })
    df = pd.DataFrame(results)

    print("=" * 90)
    print(f"  SPECIES={species_code}  MONTH={MONTH} (March)  MONSOON={MONSOON}")
    print("=" * 90)
    print(f"{'LAT':>6} {'LON':>6}  {'HOTSPOT_PROB':>12}  {'LEVEL':<22}  {'SPAWN_PROB':>10}  SPAWN?")
    print("-" * 90)
    for r in results:
        flag = "YES ✓" if r["is_spawn_spot"] else "no"
        print(
            f"  {r['lat']:>4.1f}  {r['lon']:>5.1f}  "
            f"{r['hotspot_prob']:>12.4f}  "
            f"{r['hotspot_level']:<22}  "
            f"{r['spawn_prob']:>10.4f}  {flag}"
        )

    hotspots     = df[df["hotspot_level"] != "no_hotspot"]
    spawn_hot    = hotspots[hotspots["is_spawn_spot"]]
    no_spawn_hot = hotspots[~hotspots["is_spawn_spot"]]

    print()
    print(f"  Total={len(df)}  Hotspots={len(hotspots)} "
          f"(core={( hotspots['hotspot_level']=='CORE_HOTSPOT').sum()}, "
          f"candidate={(hotspots['hotspot_level']=='candidate_hotspot').sum()})  "
          f"SpawnSpots={df['is_spawn_spot'].sum()}")
    print(f"  Hotspot AND spawn : {len(spawn_hot)}")
    print(f"  Hotspot NOT spawn : {len(no_spawn_hot)}")
    if len(spawn_hot):
        print("  *** Cells that are BOTH hotspot and spawn zone:")
        for _, r in spawn_hot.iterrows():
            print(f"      ({r.lat:.1f}N, {r.lon:.1f}E)  hotspot={r.hotspot_prob:.3f}  spawn={r.spawn_prob:.3f}")
    print()

