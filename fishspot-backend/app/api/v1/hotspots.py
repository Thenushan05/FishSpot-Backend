from typing import List
from fastapi import APIRouter

from app.schemas.hotspot import GridCell, BatchPrediction
from app.services.hotspot_service import HotspotService

router = APIRouter()


@router.post("/predict", response_model=BatchPrediction)
def predict(cells: List[GridCell]):
    """Predict hotspot scores for a list of grid cells."""
    svc = HotspotService()
    features = [{"lat": c.lat, "lon": c.lon} for c in cells]
    preds = svc.predict(features)
    # normalize into BatchPrediction schema
    predictions = []
    for c, p in zip(cells, preds):
        predictions.append({"cell": {"lat": c.lat, "lon": c.lon}, "score": float(p.get("score", 0.0))})

    return {"predictions": predictions}
