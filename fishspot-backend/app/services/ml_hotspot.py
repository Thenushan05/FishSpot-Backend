# app/services/ml_hotspot.py

import sys
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import math
import pickle
import warnings
from pathlib import Path
from typing import List, Dict

import joblib
import numpy as np
import pandas as pd
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*serialized model.*")
    warnings.filterwarnings("ignore", message=".*Booster.save_model.*")
    import xgboost as xgb

from app.ml.feature_config import FEATURE_COLS, T_CAND, T_CORE

MODEL_PATH = Path(__file__).resolve().parents[1] / "ml" / "new_xgb_trained_random_ts20260214_084749.joblib"
SPAWN_MODEL_PATH = Path(__file__).resolve().parents[1] / "ml" / "spawn" / "spawn_model.ubj"

# Numeric encoding for monsoon strings (must match spawn model training order)
_MONSOON_ENC = {
    "IO_NE_monsoon":          0,
    "IO_SW_monsoon":          1,
    "IO_First_Intermonsoon":  2,
    "IO_Second_Intermonsoon": 3,
    "No_monsoon_region":      4,
    # MC regions not in training set — map to closest Indian Ocean equivalent
    "MC_NW_monsoon":          1,  # SW-monsoon equivalent
    "MC_SE_monsoon":          0,  # NE-monsoon equivalent
    "MC_Transition_1":        2,  # Inter-monsoon equivalent
    "MC_Transition_2":        3,  # Second inter-monsoon equivalent
}

print("Loading hotspot model from:", MODEL_PATH)
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*serialized model.*")
    warnings.filterwarnings("ignore", message=".*Booster.save_model.*")
    _model = joblib.load(MODEL_PATH)
print("Hotspot model loaded")

_spawn_model = None
try:
    _spawn_clf = xgb.XGBClassifier()
    _spawn_clf.load_model(str(SPAWN_MODEL_PATH))
    _spawn_model = _spawn_clf
    print("Spawn model loaded from:", SPAWN_MODEL_PATH)
except Exception as e:
    print(f"WARNING: Spawn model could not be loaded ({e}). spawn_probability will be None.")


def _classify_level(p: float) -> str:
    if p >= T_CORE:
        return "core_hotspot"
    elif p >= T_CAND:
        return "candidate_hotspot"
    return "no_hotspot"


def _build_spawn_row(cell: Dict) -> Dict:
    """Build the 15-feature row the spawn model expects from an enriched cell dict."""
    lat   = float(cell.get("LAT",   cell.get("lat",   0.0)))
    lon   = float(cell.get("LON",   cell.get("lon",   0.0)))
    # DEPTH in enriched cell is raw negative GEBCO value; model was trained with positive depth
    raw_depth = cell.get("DEPTH", cell.get("depth_abs", None))
    depth = abs(float(raw_depth)) if raw_depth is not None else 100.0
    sss   = float(cell.get("sss",   34.5))
    ssd   = float(cell.get("ssd",   1025.0))
    sst   = float(cell.get("sst",   28.0))
    ssh   = float(cell.get("ssh",   0.0))
    chlo  = float(cell.get("chlo",  0.1))
    month_sin = float(cell.get("month_sin", 0.0))
    month_cos = float(cell.get("month_cos", 1.0))
    monsoon_enc = _MONSOON_ENC.get(str(cell.get("monsoon", "")), 4)  # default 4 = No_monsoon_region
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
        "monsoon_enc":            monsoon_enc,
        "lat_sst_interaction":    lat  * sst,
        "lon_sst_interaction":    lon  * sst,
        "depth_chlo_interaction": depth * chlo,
        "sss_sst_interaction":    sss  * sst,
    }


def predict_cells(cells: List[Dict]) -> List[Dict]:
    """
    cells: list of dicts; must contain all keys in FEATURE_COLS.
    Extra keys (uppercase originals like SST, SSH …) are preserved in output.
    Automatically runs the spawn model on the same inputs and adds
    spawn_probability + spawning to every result.
    """
    if not cells:
        return []

    # ── Hotspot model ─────────────────────────────────────────────────────────
    X = pd.DataFrame([{col: cell[col] for col in FEATURE_COLS} for cell in cells])
    probs = _model.predict_proba(X)[:, 1]

    # ── Spawn model ───────────────────────────────────────────────────────────
    spawn_probs: List[float | None] = [None] * len(cells)
    if _spawn_model is not None:
        try:
            X_spawn = pd.DataFrame([_build_spawn_row(c) for c in cells])
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                spawn_probs = [float(p) for p in _spawn_model.predict_proba(X_spawn)[:, 1]]
            spawn_count = sum(1 for p in spawn_probs if p is not None and p >= 0.65)
            print(f"[SPAWN MODEL] Ran on {len(cells)} cells  ->  {spawn_count}/{len(cells)} are spawn zones (prob >= 0.65)")
            for i, sp in enumerate(spawn_probs):
                lat_v = cells[i].get("LAT", cells[i].get("lat", "?"))
                lon_v = cells[i].get("LON", cells[i].get("lon", "?"))
                flag  = "SPAWN" if sp >= 0.65 else "no spawn"
                print(f"           cell[{i}] ({lat_v}, {lon_v})  spawn_prob={sp:.4f}  -> {flag}")
        except Exception as e:
            print(f"[SPAWN MODEL] WARNING: Spawn prediction failed: {e}")
    else:
        print("[SPAWN MODEL] WARNING: Spawn model not loaded — skipping spawn prediction")

    results: List[Dict] = []
    for cell, p, sp in zip(cells, probs, spawn_probs):
        p_float = float(p)
        results.append({
            **cell,
            "score":            p_float,
            "p_hotspot":        p_float,
            "hotspot_level":    _classify_level(p_float),
            "spawn_probability": sp,
            "spawning":         (sp is not None and sp >= 0.65),
        })
    return results
