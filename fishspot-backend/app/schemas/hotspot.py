# app/schemas/hotspot.py

from pydantic import BaseModel
from typing import List

class GridCellIn(BaseModel):
    YEAR: int
    MONTH: int
    LAT: float
    LON: float
    SST: float
    SSS: float
    CHLO: float

class HotspotPrediction(BaseModel):
    YEAR: int
    MONTH: int
    LAT: float
    LON: float
    SST: float
    SSS: float
    CHLO: float
    p_hotspot: float
    hotspot_level: str

class BatchPredictRequest(BaseModel):
    cells: List[GridCellIn]

class BatchPredictResponse(BaseModel):
    predictions: List[HotspotPrediction]


# Compatibility models used by other endpoints (simple lat/lon + score)
class GridCell(BaseModel):
    lat: float
    lon: float


class Prediction(BaseModel):
    cell: GridCell
    score: float


class BatchPrediction(BaseModel):
    predictions: List[Prediction]
