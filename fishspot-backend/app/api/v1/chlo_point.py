from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from io import StringIO
import datetime

import pandas as pd
import requests

router = APIRouter()

ERDDAP_BASE = (
    "https://coastwatch.noaa.gov/erddap/griddap/noaacwNPPVIIRSchlaDaily.csv"
)

# Earliest date available in this NRT dataset (do not call ERDDAP for older dates)
DATASET_START = datetime.date(2024, 11, 1)


class ChloRequest(BaseModel):
    date: str  # "2023-01-01"
    lat: float
    lon: float


class ChloResponse(BaseModel):
    date: str
    lat: float
    lon: float
    chlo: Optional[float]


@router.post("/point", response_model=ChloResponse)
def get_chlo_at_point(req: ChloRequest):
    # parse requested date
    try:
        req_date = datetime.date.fromisoformat(req.date)
    except Exception:
        # invalid date format -> return NaN
        return ChloResponse(date=req.date, lat=req.lat, lon=req.lon, chlo=float("nan"))

    # If requested date is earlier than the dataset's earliest date,
    # do not call the NRT ERDDAP dataset (it contains no data for older dates).
    if req_date < DATASET_START:
        return ChloResponse(date=req.date, lat=req.lat, lon=req.lon, chlo=float("nan"))
    # 1) Build a small lat/lon box (±0.1° around the point)
    lat_min = req.lat - 0.1
    lat_max = req.lat + 0.1
    lon_min = req.lon - 0.1
    lon_max = req.lon + 0.1

    # 2) ERDDAP query: time range is the same day (start = end)
    query = (
        f"?chlor_a[({req.date}T12:00:00Z):({req.date}T12:00:00Z)]"
        f"[({lat_min}):({lat_max})]"
        f"[({lon_min}):({lon_max})]"
    )

    url = ERDDAP_BASE + query

    # 3) Download CSV
    r = requests.get(url)
    r.raise_for_status()

    df = pd.read_csv(StringIO(r.text))

    if df.empty:
        # No data found (e.g. land / missing)
        return ChloResponse(date=req.date, lat=req.lat, lon=req.lon, chlo=float("nan"))

    # 4) Pick nearest grid cell to requested lat/lon
    df["dist2"] = (df["latitude"] - req.lat) ** 2 + (df["longitude"] - req.lon) ** 2
    row = df.loc[df["dist2"].idxmin()]

    return ChloResponse(
        date=req.date,
        lat=float(row["latitude"]),
        lon=float(row["longitude"]),
        chlo=float(row["chlor_a"]),
    )
