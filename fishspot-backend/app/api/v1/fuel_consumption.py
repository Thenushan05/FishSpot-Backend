"""
Fuel consumption calculation API for vessel trips.
"""
import math
import csv
import os
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, validator

router = APIRouter()


class FuelCalculationRequest(BaseModel):
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    vessel_id: Optional[str] = None  # If not provided, use average
    
    @validator('start_lat', 'end_lat')
    def validate_latitude(cls, v):
        if not -90 <= v <= 90:
            raise ValueError('Latitude must be between -90 and 90')
        return v
    
    @validator('start_lon', 'end_lon')
    def validate_longitude(cls, v):
        if not -180 <= v <= 180:
            raise ValueError('Longitude must be between -180 and 180')
        return v


class FuelCalculationResponse(BaseModel):
    distance_km: float
    estimated_trip_duration_hours: float
    fuel_consumption_liters: float
    vessel_used: str
    fuel_cost_usd: float


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on the earth (in kilometers).
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Radius of earth in kilometers
    r = 6371
    
    return c * r


def load_vessel_data():
    """
    Load vessel data from CSV file.
    """
    csv_path = os.path.join(os.path.dirname(__file__), "../../../data/vessel/vessels.csv")
    vessels = {}
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                vessels[row['vessel_id']] = {
                    'fuel_consumption': float(row['fuel_consumption']),  # liters per day
                    'fuel_cost_usd_per_day': float(row['fuel_cost_usd_per_day']),
                    'hp': float(row['hp']),
                    'vessel_type': row['vessel_type'],
                    'engine_type': row['engine_type']
                }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading vessel data: {str(e)}")
    
    return vessels


def get_average_vessel_data(vessels):
    """
    Calculate average fuel consumption and cost from all vessels.
    """
    if not vessels:
        return None
    
    total_consumption = sum(v['fuel_consumption'] for v in vessels.values())
    total_cost = sum(v['fuel_cost_usd_per_day'] for v in vessels.values())
    count = len(vessels)
    
    return {
        'fuel_consumption': total_consumption / count,
        'fuel_cost_usd_per_day': total_cost / count,
        'hp': sum(v['hp'] for v in vessels.values()) / count,
        'vessel_type': 'Average',
        'engine_type': 'Average'
    }


@router.post("/calculate-fuel-consumption", response_model=FuelCalculationResponse)
async def calculate_fuel_consumption(request: FuelCalculationRequest):
    """
    Calculate fuel consumption for a trip between two coordinates.
    
    The calculation considers:
    1. Distance between start and end points (Haversine formula)
    2. Estimated trip duration based on average vessel speed
    3. Fuel consumption based on vessel specifications
    """
    # Load vessel data
    vessels = load_vessel_data()
    
    if not vessels:
        raise HTTPException(status_code=500, detail="No vessel data available")
    
    # Select vessel data
    if request.vessel_id and request.vessel_id in vessels:
        vessel_data = vessels[request.vessel_id]
        vessel_used = request.vessel_id
    else:
        vessel_data = get_average_vessel_data(vessels)
        vessel_used = "Average Vessel"
    
    if not vessel_data:
        raise HTTPException(status_code=400, detail="Invalid vessel selection")
    
    # Calculate distance
    distance_km = haversine_distance(
        request.start_lat, request.start_lon,
        request.end_lat, request.end_lon
    )
    
    # Estimate trip duration
    # Assume average fishing vessel speed: 12 knots = ~22 km/h
    average_speed_kmh = 22.0
    trip_duration_hours = distance_km / average_speed_kmh
    
    # Calculate fuel consumption
    # vessel fuel_consumption is in liters per day (24 hours)
    fuel_consumption_per_hour = vessel_data['fuel_consumption'] / 24
    trip_fuel_consumption = fuel_consumption_per_hour * trip_duration_hours
    
    # Calculate fuel cost
    fuel_cost_per_hour = vessel_data['fuel_cost_usd_per_day'] / 24
    trip_fuel_cost = fuel_cost_per_hour * trip_duration_hours
    
    return FuelCalculationResponse(
        distance_km=round(distance_km, 2),
        estimated_trip_duration_hours=round(trip_duration_hours, 2),
        fuel_consumption_liters=round(trip_fuel_consumption, 2),
        vessel_used=vessel_used,
        fuel_cost_usd=round(trip_fuel_cost, 2)
    )


@router.get("/vessels")
async def list_vessels():
    """
    Get list of available vessels for fuel calculation.
    """
    vessels = load_vessel_data()
    
    vessel_list = []
    for vessel_id, data in vessels.items():
        vessel_list.append({
            "vessel_id": vessel_id,
            "vessel_type": data['vessel_type'],
            "engine_type": data['engine_type'],
            "hp": data['hp'],
            "fuel_consumption_per_day": data['fuel_consumption'],
            "fuel_cost_usd_per_day": data['fuel_cost_usd_per_day']
        })
    
    return {
        "vessels": vessel_list,
        "total_count": len(vessel_list)
    }


@router.get("/vessels/{vessel_id}")
async def get_vessel_details(vessel_id: str):
    """
    Get details for a specific vessel.
    """
    vessels = load_vessel_data()
    
    if vessel_id not in vessels:
        raise HTTPException(status_code=404, detail=f"Vessel {vessel_id} not found")
    
    return {
        "vessel_id": vessel_id,
        **vessels[vessel_id]
    }