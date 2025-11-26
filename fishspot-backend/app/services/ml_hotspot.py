# app/services/ml_hotspot.py

from pathlib import Path
from typing import List, Dict

import joblib
import numpy as np

from app.ml.feature_config import FEATURE_COLS, T_CAND, T_CORE

MODEL_PATH = Path(__file__).resolve().parents[1] / "ml" / "xgb_classification_tuned.joblib"

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
    cells: list of dicts with keys in FEATURE_COLS
    """
    if not cells:
        return []

    X = np.array([[cell[col] for col in FEATURE_COLS] for cell in cells])
    probs = _model.predict_proba(X)[:, 1]

    results: List[Dict] = []
    for cell, p in zip(cells, probs):
        p_float = float(p)
        results.append({
            **cell,
            "p_hotspot": p_float,
            "hotspot_level": _classify_level(p_float),
        })
    return results
