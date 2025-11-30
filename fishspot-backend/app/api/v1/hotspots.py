from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException
from datetime import datetime
import numpy as np

from app.schemas.hotspot import GridCell, BatchPrediction, RegionPredictRequest, RegionPredictResponse
from app.services.hotspot_service import HotspotService
from app.services.enhanced_hotspot_service import EnhancedHotspotService

router = APIRouter()


@router.post("/predict", response_model=BatchPrediction)
def predict(
    cells: List[GridCell],
    use_weather_data: bool = Query(True, description="Fetch real-time oceanographic data from Copernicus"),
    date: Optional[str] = Query(None, description="Date in format YYYY-MM-DD (defaults to yesterday)")
):
    """
    Predict hotspot scores for a list of grid cells.
    
    Args:
        cells: List of grid cells with lat/lon coordinates
        use_weather_data: If True, fetches SST, SSH, Chlorophyll from Copernicus Marine
        date: Optional date for historical data (format: YYYY-MM-DD)
    
    Returns:
        Batch predictions with hotspot scores and oceanographic data
    """
    
    if use_weather_data:
        # Use enhanced service with real oceanographic data
        enhanced_svc = EnhancedHotspotService()
        features = [{"lat": c.lat, "lon": c.lon} for c in cells]
        
        try:
            preds = enhanced_svc.predict_with_weather_data(features, date=date)
        except Exception as e:
            print(f"⚠️ Enhanced prediction failed: {e}, falling back to simple prediction")
            preds = enhanced_svc.predict_simple(features)
    else:
        # Use simple service with default values
        svc = HotspotService()
        features = [{"lat": c.lat, "lon": c.lon} for c in cells]
        preds = svc.predict(features)
    
    # Normalize into BatchPrediction schema
    predictions = []
    for c, p in zip(cells, preds):
        predictions.append({
            "cell": {"lat": c.lat, "lon": c.lon}, 
            "score": float(p.get("score", 0.0)),
            "sst": p.get("SST"),
            "ssh": p.get("SSH"),
            "chlorophyll": p.get("CHLO"),
            "hotspot_level": p.get("hotspot_level", "no_hotspot")
        })

    return {"predictions": predictions}


@router.post("/predict-region", response_model=RegionPredictResponse)
async def predict_region(request: RegionPredictRequest):
    """
    Predict hotspots for a geographic region using bounding box.
    
    Generates a grid of cells within the bbox, fetches oceanographic data,
    and returns predictions sorted by hotspot score.
    
    Args:
        request: Contains bbox, date, species, threshold, and top_k parameters
    
    Returns:
        Top K hotspot predictions with oceanographic data
    """
    try:
        # Parse date from YYYYMMDD to YYYY-MM-DD
        date_str = request.date
        if len(date_str) == 8:
            formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        else:
            formatted_date = None
        
        # Generate grid cells within bbox (0.25 degree resolution ~27km spacing)
        grid_resolution = 0.25  # degrees (reduced from 0.1 for faster processing)
        lat_range = np.arange(request.bbox.min_lat, request.bbox.max_lat, grid_resolution)
        lon_range = np.arange(request.bbox.min_lon, request.bbox.max_lon, grid_resolution)
        
        # Create grid of lat/lon pairs
        grid_cells = []
        for lat in lat_range:
            for lon in lon_range:
                grid_cells.append({"lat": float(lat), "lon": float(lon)})
        
        print(f"🗺️ Generated {len(grid_cells)} cells for region {request.bbox.dict()}")
        
        # Use enhanced service to get predictions with real weather data
        enhanced_svc = EnhancedHotspotService()
        
        try:
            preds = enhanced_svc.predict_with_weather_data(grid_cells, date=formatted_date)
        except Exception as e:
            print(f"⚠️ Weather data fetch failed: {e}, using simple prediction")
            preds = enhanced_svc.predict_simple(grid_cells)
        
        # Build prediction results
        predictions = []
        for cell, p in zip(grid_cells, preds):
            score = float(p.get("score", 0.0))
            
            # Apply threshold filter
            if score >= request.threshold:
                predictions.append({
                    "cell": {"lat": cell["lat"], "lon": cell["lon"]},
                    "score": score,
                    "sst": p.get("SST"),
                    "ssh": p.get("SSH"),
                    "chlorophyll": p.get("CHLO"),
                    "hotspot_level": p.get("hotspot_level", "no_hotspot")
                })
        
        # Sort by score descending and take top K
        predictions.sort(key=lambda x: x["score"], reverse=True)
        top_predictions = predictions[:request.top_k]
        
        print(f"✅ Returning {len(top_predictions)} hotspots (threshold: {request.threshold})")
        
        return {
            "predictions": top_predictions,
            "total_cells": len(grid_cells),
            "date": request.date,
            "species": request.species
        }
        
    except Exception as e:
        print(f"❌ Error in predict_region: {e}")
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")
