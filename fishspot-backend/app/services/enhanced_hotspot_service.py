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
        print(f"⏳ Fetching oceanographic data (this may take 2-3 minutes)...")
        
        # Fetch oceanographic data for the entire bbox
        ocean_data = self.copernicus.get_ocean_data_for_bbox(
            lat_min=bbox['lat_min'],
            lat_max=bbox['lat_max'],
            lon_min=bbox['lon_min'],
            lon_max=bbox['lon_max'],
            date=date
        )
        
        # Enrich each cell with oceanographic data
        enriched_cells = []
        for cell in cells:
            lat = cell['lat']
            lon = cell['lon']
            
            # Extract values at this specific point
            sst = self.copernicus.extract_value_at_point(
                ocean_data['sst'], lat, lon, 'thetao'
            ) if ocean_data['sst'] is not None else None
            
            ssh = self.copernicus.extract_value_at_point(
                ocean_data['ssh'], lat, lon, 'zos'
            ) if ocean_data['ssh'] is not None else None
            
            chlo = self.copernicus.extract_value_at_point(
                ocean_data['chlorophyll'], lat, lon, 'chl'
            ) if ocean_data['chlorophyll'] is not None else None
            
            # Convert SST from Kelvin to Celsius if needed
            if sst is not None and sst > 100:  # Likely in Kelvin
                sst = sst - 273.15
            
            # Get current date components
            now = datetime.now()
            year = now.year
            month = now.month
            
            # Classify monsoon pattern for this location and month
            monsoon_features = classify_monsoon(lat, lon, month)
            
            # Build feature dict for ML model
            # Model expects: year, month, lat, lon, depth, sss, ssd, sst, ssh, chlo,
            #                month_sin, month_cos, depth_abs, SPECIES_CODE, monsoon
            import numpy as np
            
            # Calculate cyclical month features
            month_sin = np.sin(2 * np.pi * month / 12)
            month_cos = np.cos(2 * np.pi * month / 12)
            
            enriched_cell = {
                'YEAR': year,
                'MONTH': month,
                'LAT': lat,
                'LON': lon,
                'DEPTH': -100.0,  # Typical depth for pelagic fish (negative = below surface)
                'SSS': 35.0,  # Default salinity for Indian Ocean
                'SSD': 0.5,  # Sea surface density (typical value)
                'SST': sst if sst is not None else 28.0,  # Sea surface temperature
                'SSH': ssh if ssh is not None else 0.5,  # Sea surface height
                'CHLO': chlo if chlo is not None else 0.1,  # Chlorophyll
                'MONTH_SIN': month_sin,
                'MONTH_COS': month_cos,
                'DEPTH_ABS': 100.0,  # Absolute value of depth
                'SPECIES_CODE': 'YFT',  # Yellowfin Tuna (can be parameterized later)
                'MONSOON': monsoon_features.get('monsoon', 'IO_NE_monsoon')  # From classification
            }
            
            enriched_cells.append(enriched_cell)
        
        print(f"✅ Enriched {len(enriched_cells)} cells with oceanographic data")
        print(f"🤖 Running ML predictions...")
        
        # Run ML predictions
        predictions = ml_hotspot.predict_cells(enriched_cells)
        
        print(f"✅ Predictions complete!")
        
        # Add additional metadata to results
        for pred in predictions:
            pred['data_source'] = 'copernicus_marine'
            pred['data_date'] = ocean_data['date']
        
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
            
            enriched_cell = {
                'YEAR': now.year,
                'MONTH': now.month,
                'LAT': cell['lat'],
                'LON': cell['lon'],
                'DEPTH': -100.0,
                'SSS': 35.0,  # Default salinity
                'SSD': 0.5,  # Default sea surface density
                'SST': 28.0,  # Default SST
                'SSH': 0.5,  # Default SSH
                'CHLO': 0.1,  # Default chlorophyll
                'MONTH_SIN': month_sin,
                'MONTH_COS': month_cos,
                'DEPTH_ABS': 100.0,
                'SPECIES_CODE': 'YFT',
                'MONSOON': monsoon_features.get('monsoon', 'IO_NE_monsoon')
            }
            enriched_cells.append(enriched_cell)
        
        return ml_hotspot.predict_cells(enriched_cells)
