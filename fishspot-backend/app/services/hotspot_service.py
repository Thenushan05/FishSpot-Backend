"""Compatibility wrapper service exposing HotspotService class used by routers."""
from typing import List, Dict, Any

from app.services import ml_hotspot


class HotspotService:
    def __init__(self):
        pass

    def predict(self, features: List[Dict[str, Any]]):
        """Call the ML hotspot predictor and adapt output to expected format.

        Returns list of dicts with at least the `score` key.
        """
        # ml_hotspot.predict_cells expects feature dicts aligned to training FEATURE_COLS
        results = ml_hotspot.predict_cells(features)
        # Convert to simple {"score": p_hotspot, ...}
        output = []
        for r in results:
            output.append({"score": float(r.get("p_hotspot", 0.0)), **r})
        return output
