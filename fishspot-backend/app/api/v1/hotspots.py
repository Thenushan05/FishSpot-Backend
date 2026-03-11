from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException
from datetime import datetime
import numpy as np
import math

from pydantic import BaseModel
from app.schemas.hotspot import GridCell, BatchPrediction, RegionPredictRequest, RegionPredictResponse
from app.services.hotspot_service import HotspotService
from app.services.enhanced_hotspot_service import EnhancedHotspotService


class PredictFromPointRequest(BaseModel):
    lat: float
    lon: float
    species: str = "YFT"
    threshold: float = 0.4
    n_points: int = 20
    radius_km: float = 10.0
    date: Optional[str] = None


def _generate_sample_points(lat: float, lon: float, radius_km: float, n: int) -> list:
    """
    Generate n lat/lon points within radius_km using the sunflower (Fermat's spiral) pattern.
    This gives uniform area coverage with predictable inter-point spacing:
        spacing ≈ radius_km * 1.41 / sqrt(n)   [km]
    All 360° are covered so the full circle is sampled evenly.
    """
    R = 6371.0
    GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))  # ≈ 2.399 radians ≈ 137.5°
    pts = []
    for i in range(n):
        # Radius: scale as sqrt((i+0.5)/n) for uniform area distribution
        r_frac = math.sqrt((i + 0.5) / n)
        dist_km = r_frac * radius_km
        bearing_rad = i * GOLDEN_ANGLE          # rotates by golden angle each time
        d = dist_km / R
        lat1 = math.radians(lat)
        lon1 = math.radians(lon)
        lat2 = math.asin(
            math.sin(lat1) * math.cos(d) +
            math.cos(lat1) * math.sin(d) * math.cos(bearing_rad)
        )
        lon2 = lon1 + math.atan2(
            math.sin(bearing_rad) * math.sin(d) * math.cos(lat1),
            math.cos(d) - math.sin(lat1) * math.sin(lat2)
        )
        pts.append({
            "lat": round(math.degrees(lat2), 5),
            "lon": round(math.degrees(lon2), 5)
        })
    return pts

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
            "hotspot_level": p.get("hotspot_level", "no_hotspot"),
            "spawn_probability": p.get("spawn_probability"),
            "spawning": p.get("spawning"),
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
                    "hotspot_level": p.get("hotspot_level", "no_hotspot"),
                    "spawn_probability": p.get("spawn_probability"),
                    "spawning": p.get("spawning"),
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


@router.post("/predict-from-point")
async def predict_from_point(request: PredictFromPointRequest):
    """
    1. Generate n_points * 5 candidate lat/lon within radius_km (front/left/right 270° arc).
    2. Filter candidates to ocean-only using GEBCO depth (elevation < 0; None = ocean).
    3. Auto-retry at 2× radius if fewer than n_points ocean points survive filtering.
    4. Fetch real oceanographic data (SST, SSH, CHLO, SSS, SSD, Depth) via EnhancedHotspotService.
    5. Run ML hotspot model, return per-point predictions with confidence scores.
    """
    from app.services import depth_service as _depth_svc

    _MULTIPLIER = 5  # generate 5× candidates so plenty survive GEBCO filtering

    def _filter_ocean(cand_list):
        """Run GEBCO filter; treat None elevation as ocean (open water, lookup miss)."""
        nonlocal land_filtered
        try:
            clats = [c["lat"] for c in cand_list]
            clons = [c["lon"] for c in cand_list]
            dchecks = _depth_svc.get_depths(clats, clons)
            ok = []
            for cell, dc in zip(cand_list, dchecks):
                elev = dc.get("value")
                if elev is not None and elev >= 0:
                    # Confirmed land / above sea level — exclude
                    land_filtered += 1
                    print(f"   🏝️  Land ({cell['lat']:.4f},{cell['lon']:.4f}) elev={elev:.1f}m")
                else:
                    # None (lookup miss) or negative (ocean depth) — keep
                    cell["_gebco_depth_m"] = round(abs(elev), 1) if elev is not None else None
                    ok.append(cell)
            return ok
        except Exception as e:
            print(f"⚠️ GEBCO filter error: {e} — treating all as ocean")
            return cand_list

    # ── Step 1: Generate 5× candidates ───────────────────────────────────────
    land_filtered = 0
    candidates = _generate_sample_points(
        request.lat, request.lon,
        request.radius_km, request.n_points * _MULTIPLIER
    )
    print(f"🎯 predict-from-point: {len(candidates)} candidate points around ({request.lat:.4f}, {request.lon:.4f})")

    # ── Step 2: Filter to ocean points (GEBCO elevation < 0 or None) ─────────
    ocean_cells = _filter_ocean(candidates)
    print(f"🌊 {len(ocean_cells)} ocean / {land_filtered} land-excluded from {len(candidates)} candidates")

    # ── Step 2b: Auto-retry at 2× radius if not enough ocean points ──────────
    if len(ocean_cells) < request.n_points:
        wider_radius = request.radius_km * 2.0
        print(f"⚡ Only {len(ocean_cells)}/{request.n_points} ocean points found — retrying at {wider_radius:.1f} km radius...")
        extra = _generate_sample_points(
            request.lat, request.lon,
            wider_radius, request.n_points * _MULTIPLIER
        )
        extra_ocean = _filter_ocean(extra)
        # Deduplicate by rounding to 3 dp
        existing_keys = {(round(c["lat"], 3), round(c["lon"], 3)) for c in ocean_cells}
        for c in extra_ocean:
            key = (round(c["lat"], 3), round(c["lon"], 3))
            if key not in existing_keys:
                ocean_cells.append(c)
                existing_keys.add(key)
        print(f"🌊 After wider-radius retry: {len(ocean_cells)} ocean points")

    # Limit to requested n_points
    cells = ocean_cells[: request.n_points]
    if not cells:
        raise HTTPException(status_code=422, detail="No valid ocean points found within radius. Try a larger radius or a different starting location.")

    print(f"✅ Sending {len(cells)} ocean-confirmed points to model")

    # ── Step 3: Fetch ocean data + run ML model ───────────────────────────────
    enhanced_svc = EnhancedHotspotService()
    try:
        preds = enhanced_svc.predict_with_weather_data(cells, date=request.date, species=request.species)
    except Exception as e:
        print(f"⚠️ predict-from-point enhanced failed: {e}, using fallback")
        preds = enhanced_svc.predict_simple(cells)

    # ── Step 4: Build response ────────────────────────────────────────────────
    results = []
    for cell, p in zip(cells, preds):
        score = float(p.get("score", 0.0))
        # DEPTH from EnhancedHotspotService (from depth_service) or cached GEBCO value
        model_depth = p.get("DEPTH")
        gebco_depth = cell.get("_gebco_depth_m")  # positive metres, pre-verified ocean
        depth_to_use = model_depth if model_depth is not None else ((-gebco_depth) if gebco_depth is not None else None)
        results.append({
            "lat": cell["lat"],
            "lon": cell["lon"],
            "score": round(score, 4),
            "confidence_pct": round(score * 100, 1),
            "hotspot_level": p.get("hotspot_level", "no_hotspot"),
            "sst":   p.get("SST"),
            "ssh":   p.get("SSH"),
            "chlo":  p.get("CHLO"),
            "sss":   p.get("SSS"),
            "ssd":   p.get("SSD"),
            "depth": depth_to_use,
            "gebco_depth_m": gebco_depth,          # positive metres — proof it's ocean
            "ocean_verified": gebco_depth is not None,  # True = GEBCO confirmed ocean
            "spawn_probability": p.get("spawn_probability"),
            "spawning": p.get("spawning"),
            "chlo_source": p.get("chlo_source", ""),
            "sss_source":  p.get("sss_source",  ""),
            "ssd_source":  p.get("ssd_source",  ""),
            "sst_source":  p.get("sst_source",  ""),
            "data_date":   p.get("data_date",   ""),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    high     = sum(1 for r in results if r["score"] >= 0.7)
    moderate = sum(1 for r in results if 0.4 <= r["score"] < 0.7)
    low      = sum(1 for r in results if r["score"] < 0.4)
    mean_conf = round(sum(r["score"] for r in results) / len(results) * 100, 1) if results else 0.0
    best_conf = round(results[0]["score"] * 100, 1) if results else 0.0
    # Approximate inter-point spacing for uniform sunflower grid
    n_actual = len(results)
    mean_spacing_km = round(request.radius_km * 1.41 / math.sqrt(max(n_actual, 1)), 2)
    ocean_verified_count = sum(1 for r in results if r.get("ocean_verified"))

    print(f"✅ {len(results)} results | {ocean_verified_count} GEBCO-verified ocean | {land_filtered} land excluded | mean spacing ~{mean_spacing_km} km")

    return {
        "start_point": {"lat": request.lat, "lon": request.lon},
        "radius_km": request.radius_km,
        "total_points": len(results),
        "candidates_generated": len(candidates),
        "land_filtered": land_filtered,
        "ocean_verified_count": ocean_verified_count,
        "predictions": results,
        "summary": {
            "high": high,
            "moderate": moderate,
            "low": low,
            "mean_confidence_pct": mean_conf,
            "best_confidence_pct": best_conf,
            "mean_spacing_km": mean_spacing_km,
        },
    }
