from fastapi import APIRouter, Query, HTTPException
from typing import Optional

from app.services.depth_service import get_depth

router = APIRouter()


@router.get("/")
def depth(lat: float = Query(...), lon: float = Query(...)):
    """Return depth/elevation at nearest grid point from GEBCO NetCDF.

    Query params: `lat` and `lon` (floats).
    """
    try:
        res = get_depth(lat=float(lat), lon=float(lon))
        return res
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
