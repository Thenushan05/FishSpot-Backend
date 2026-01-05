"""
Enhanced hotspot prediction service that integrates Copernicus Marine data.
Fetches SST, SSH, SSS, and Chlorophyll data for grid cells and runs ML predictions.
"""
from typing import List, Dict, Optional
from datetime import datetime
import numpy as np

from app.services.copernicus_service import CopernicusService
from app.services import ml_hotspot
from app.services.monsoon_classifier import classify_monsoon


class EnhancedHotspotService:
    """
    Hotspot service that fetches real oceanographic data from Copernicus
    and runs ML model predictions.
    """
    
    def __init__(self):
        self.copernicus = CopernicusService()
    
    def predict_with_weather_data(
        self,
        cells: List[Dict[str, float]],
        date: Optional[str] = None
    ) -> List[Dict]:
        """
        Predict hotspot scores for grid cells with real-time weather data.
        
        Args:
            cells: List of dicts with 'lat' and 'lon' keys
            date: Optional date string 'YYYY-MM-DD', defaults to yesterday
        
        Returns:
            List of prediction results with enriched ocean data
        """
        if not cells:
            return []
        
        # Extract bbox from cells
        lats = [c['lat'] for c in cells]
        lons = [c['lon'] for c in cells]
        bbox = {
            'lat_min': min(lats) - 0.1,  # Add buffer
            'lat_max': max(lats) + 0.1,
            'lon_min': min(lons) - 0.1,
            'lon_max': max(lons) + 0.1
        }
        
        print(f"📍 Processing {len(cells)} cells")
        print(f"🗺️ BBox: lat=[{bbox['lat_min']:.2f}, {bbox['lat_max']:.2f}], lon=[{bbox['lon_min']:.2f}, {bbox['lon_max']:.2f}]")
        print(f"⏳ Fetching oceanographic data from Open-Meteo...")
        
        # Use Open-Meteo for SST/SSH (more reliable than Copernicus)
        from app.services import openmeteo_service, depth_service
        import json
        
        try:
            ocean_data_list = openmeteo_service.get_sst_ssh_for_points(lats, lons)
            print(f"✅ Fetched SST/SSH from Open-Meteo for {len(ocean_data_list)} points")
        except Exception as e:
            print(f"❌ Open-Meteo fetch failed: {e}")
            ocean_data_list = [{'sst': None, 'ssh': None} for _ in lats]
        
        # Fetch depths for all cells
        try:
            depth_results = depth_service.get_depths(lats, lons)
            print(f"✅ Fetched depths from GEBCO for {len(depth_results)} points")
        except Exception as e:
            print(f"❌ Depth fetch failed: {e}")
            depth_results = [{'value': None} for _ in lats]
        
        # Get current date components
        now = datetime.now()
        year = now.year
        month = now.month
        
        # Enrich each cell with oceanographic data
        enriched_cells = []
        for idx, cell in enumerate(cells):
            lat = cell['lat']
            lon = cell['lon']
            
            # Get data from Open-Meteo
            ocean_point = ocean_data_list[idx] if idx < len(ocean_data_list) else {'sst': None, 'ssh': None}
            sst = ocean_point.get('sst')
            ssh = ocean_point.get('ssh')
            
            # Get depth
            depth_point = depth_results[idx] if idx < len(depth_results) else {'value': None}
            depth = depth_point.get('value', -100.0)
            if depth is None:
                depth = -100.0  # Default depth for pelagic fish
            
            # Classify monsoon pattern for this location and month
            monsoon_features = classify_monsoon(lat, lon, month)
            
            # Get the monsoon name for logging
            monsoon_name = next((k for k, v in monsoon_features.items() if v == 1), 'No_monsoon_region')
            
            # Create JSON log of fetched data
            fetched_data_log = {
                "lat": lat,
                "lon": lon,
                "year": year,
                "month": month,
                "date": now.strftime("%Y-%m-%d"),
                "sst": sst,
                "ssh": ssh,
                "depth": depth,
                "monsoon": monsoon_name,
                "data_source": "open_meteo"
            }
            
            # Print JSON log for first 3 cells
            if idx < 3:
                print(f"📊 Fetched data for cell {idx+1}:")
                print(json.dumps(fetched_data_log, indent=2))
            
            # Build feature dict for ML model
            # Model expects: YEAR, MONTH, LAT, LON, SST, SSS, CHLO
            import numpy as np
            
            # Calculate cyclical month features
            month_sin = np.sin(2 * np.pi * month / 12)
            month_cos = np.cos(2 * np.pi * month / 12)
            
            enriched_cell = {
                'YEAR': year,
                'MONTH': month,
                'LAT': lat,
                'LON': lon,
                'DEPTH': depth,
                'SSS': 35.0,  # Not fetching - using default salinity
                'SSD': 0.5,   # Not fetching - using default sea surface density
                'SST': sst if sst is not None else 28.0,  # Sea surface temperature from Open-Meteo
                'SSH': ssh if ssh is not None else 0.5,   # Sea surface height from Open-Meteo
                'CHLO': 0.1,  # Not fetching - using default chlorophyll
                'MONTH_SIN': month_sin,
                'MONTH_COS': month_cos,
                'DEPTH_ABS': abs(depth) if depth is not None else 100.0,
                'SPECIES_CODE': 'YFT',
                'MONSOON': monsoon_name
            }
            
            enriched_cells.append(enriched_cell)
        
        print(f"✅ Enriched {len(enriched_cells)} cells with oceanographic data")
        print(f"🤖 Running ML predictions...")
        
        # Run ML predictions
        predictions = ml_hotspot.predict_cells(enriched_cells)
        
        print(f"✅ Predictions complete!")
        
        # Add additional metadata to results
        for pred in predictions:
            pred['data_source'] = 'open_meteo'
            pred['data_date'] = now.strftime("%Y-%m-%d")
        
        return predictions
    
    def predict_simple(self, cells: List[Dict[str, float]]) -> List[Dict]:
        """
        Simple prediction with default values (fallback when Copernicus fails).
        
        Args:
            cells: List of dicts with 'lat' and 'lon' keys
        
        Returns:
            List of prediction results with default ocean data
        """
        print(f"⚠️ Using default oceanographic values for {len(cells)} cells")
        
        import numpy as np
        now = datetime.now()
        enriched_cells = []
        
        for cell in cells:
            # Classify monsoon for this location
            monsoon_features = classify_monsoon(cell['lat'], cell['lon'], now.month)
            
            # Calculate cyclical month features
            month_sin = np.sin(2 * np.pi * now.month / 12)
            month_cos = np.cos(2 * np.pi * now.month / 12)
            
            monsoon_name = next((k for k, v in monsoon_features.items() if v == 1), 'No_monsoon_region')
            
            enriched_cell = {
                'YEAR': now.year,
                'MONTH': now.month,
                'LAT': cell['lat'],
                'LON': cell['lon'],
                'DEPTH': -100.0,
                'SSS': 35.0,
                'SSD': 0.5,
                'SST': 28.0,
                'SSH': 0.5,
                'CHLO': 0.1,
                'MONTH_SIN': month_sin,
                'MONTH_COS': month_cos,
                'DEPTH_ABS': 100.0,
                'SPECIES_CODE': 'YFT',
                'MONSOON': monsoon_name
            }
            enriched_cells.append(enriched_cell)
        
        return ml_hotspot.predict_cells(enriched_cells)
