from fastapi import APIRouter, Query, HTTPException
from typing import Optional
from datetime import datetime

from app.services.predict import predict_hotspots
from pydantic import BaseModel
from typing import Optional
from app.services.predict import predict_hotspots_region


class RegionRequest(BaseModel):
    date: Optional[str] = None
    species: str = "YFT"
    threshold: float = 0.6
    top_k: Optional[int] = None
    bbox: Optional[dict] = None
    overrides: Optional[dict] = None

router = APIRouter()


@router.get("/today")
def hotspots_today(
    species: str = Query("YFT", description="Species code"),
    threshold: float = Query(0.6, ge=0.0, le=1.0, description="Probability threshold"),
    top_k: Optional[int] = Query(100, description="Top K hotspots to return (optional)"),
):
    # Default date selection: today in YYYYMMDD. Replace with real date logic if needed.
    date_str = datetime.utcnow().strftime("%Y%m%d")
    try:
        result = predict_hotspots(date=date_str, species_code=species, threshold=threshold, top_k=top_k)
        return result
    except FileNotFoundError as e:
        # helpful error when CSV missing
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-date")
def hotspots_by_date(
    date: str = Query(..., description="Date in YYYYMMDD format"),
    species: str = Query("YFT", description="Species code"),
    threshold: float = Query(0.6, ge=0.0, le=1.0, description="Probability threshold"),
    top_k: Optional[int] = Query(None, description="Top K hotspots to return (optional)"),
):
    # Basic date validation
    if len(date) != 8:
        raise HTTPException(status_code=400, detail="date must be YYYYMMDD")
    try:
        result = predict_hotspots(date=date, species_code=species, threshold=threshold, top_k=top_k)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/region")
def hotspots_region(req: RegionRequest):
    # date: if not provided use today
    if req.date is None:
        date = datetime.utcnow().strftime("%Y%m%d")
    else:
        date = req.date

    # bbox expected as dict: {min_lat, max_lat, min_lon, max_lon}
    bbox = None
    if req.bbox:
        try:
            bbox = (float(req.bbox.get("min_lat")), float(req.bbox.get("max_lat")), float(req.bbox.get("min_lon")), float(req.bbox.get("max_lon")))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid bbox format")

    try:
        res = predict_hotspots_region(date=date, species_code=req.species, threshold=req.threshold, top_k=req.top_k, bbox=bbox, overrides=req.overrides)
        return res
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
def health():
    return {"status": "ok"}
