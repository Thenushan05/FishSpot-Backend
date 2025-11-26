# app/api/v1/hotspots.py

from fastapi import APIRouter
from typing import List

from app.schemas.hotspot import (
    BatchPredictRequest,
    BatchPredictResponse,
    HotspotPrediction,
)
from app.services.ml_hotspot import predict_cells

router = APIRouter()

@router.post("/predict-batch", response_model=BatchPredictResponse)
def predict_batch(request: BatchPredictRequest):
    cells = [cell.dict() for cell in request.cells]
    preds = predict_cells(cells)

    out_items: List[HotspotPrediction] = [
        HotspotPrediction(**p) for p in preds
    ]

    return BatchPredictResponse(predictions=out_items)
