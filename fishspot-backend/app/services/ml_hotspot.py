# app/services/ml_hotspot.py

import sys
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from pathlib import Path
from typing import List, Dict

import joblib
import numpy as np
import pandas as pd

from app.ml.feature_config import FEATURE_COLS, T_CAND, T_CORE

MODEL_PATH = Path(__file__).resolve().parents[1] / "ml" / "new_xgb_trained_random_ts20260214_084749.joblib"

print("🔄 Loading hotspot model from:", MODEL_PATH)
_model = joblib.load(MODEL_PATH)
print("✅ Hotspot model loaded")

def _classify_level(p: float) -> str:
    if p >= T_CORE:
        return "core_hotspot"
    elif p >= T_CAND:
        return "candidate_hotspot"
    return "no_hotspot"

def predict_cells(cells: List[Dict]) -> List[Dict]:
    """
    cells: list of dicts; must contain all keys in FEATURE_COLS.
    Extra keys (uppercase originals like SST, SSH …) are preserved in output.
    """
    if not cells:
        return []

    # Build a named DataFrame so the Pipeline's ColumnTransformer gets correct columns
    X = pd.DataFrame([{col: cell[col] for col in FEATURE_COLS} for cell in cells])
    probs = _model.predict_proba(X)[:, 1]

    results: List[Dict] = []
    for cell, p in zip(cells, probs):
        p_float = float(p)
        results.append({
            **cell,
            "score":      p_float,   # key used by hotspots.py
            "p_hotspot":  p_float,   # keep for compatibility
            "hotspot_level": _classify_level(p_float),
        })
    return results
