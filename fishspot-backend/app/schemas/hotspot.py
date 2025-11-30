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
    sst: float = None
    ssh: float = None
    chlorophyll: float = None
    hotspot_level: str = "no_hotspot"


class BatchPrediction(BaseModel):
    predictions: List[Prediction]


# New bbox-based request for region predictions
class BBox(BaseModel):
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


class RegionPredictRequest(BaseModel):
    date: str  # Format: YYYYMMDD
    species: str = "YFT"
    threshold: float = 0.6
    top_k: int = 200
    bbox: BBox
    overrides: dict = {}


class RegionPredictResponse(BaseModel):
    predictions: List[Prediction]
    total_cells: int
    date: str
    species: str
