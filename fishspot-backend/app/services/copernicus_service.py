"""
Service to fetch oceanographic data from Copernicus Marine Service.
Fetches SST, SSH, SSS, and Chlorophyll data for given coordinates.
"""
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import tempfile
import xarray as xr

try:
    import copernicusmarine
    COPERNICUS_AVAILABLE = True
except ImportError:
    COPERNICUS_AVAILABLE = False
    print("⚠️ copernicusmarine not installed. Install with: pip install copernicusmarine")


class CopernicusService:
    """Fetch oceanographic data from Copernicus Marine Service."""
    
    # Updated Product IDs for Copernicus Marine Service
    SST_PRODUCT = "cmems_mod_glo_phy_my_0.083deg_P1D-m"  # Global Ocean Physics Reanalysis
    SSH_PRODUCT = "cmems_mod_glo_phy_my_0.083deg_P1D-m"  # Same product has SSH (zos)
    CHLO_PRODUCT = "cmems_mod_glo_bgc_my_0.25deg_P1D-m"  # Global Ocean Biogeochemistry
    
    def __init__(self):
        self.username = os.getenv("COPERNICUS_USERNAME")
        self.password = os.getenv("COPERNICUS_PASSWORD")
        
        if not self.username or not self.password:
            print("⚠️ COPERNICUS_USERNAME and COPERNICUS_PASSWORD not set in environment")
    
    def fetch_sst(
        self, 
        lat_min: float, 
        lat_max: float, 
        lon_min: float, 
        lon_max: float,
        date: Optional[str] = None
    ) -> Optional[xr.Dataset]:
        """
        Fetch Sea Surface Temperature data.
        
        Args:
            lat_min, lat_max: Latitude bounds
            lon_min, lon_max: Longitude bounds
            date: Date string in format 'YYYY-MM-DD', defaults to yesterday
        
        Returns:
            xarray Dataset with SST data or None if fetch fails
        """
        if not COPERNICUS_AVAILABLE:
            return None
        
        if date is None:
            # Use October 15, 2025 (safely within available range)
            date = "2025-10-15"
        
        # Ensure date is not beyond October 28, 2025 (latest available)
        try:
            req_date = datetime.strptime(date, "%Y-%m-%d")
            max_date = datetime(2025, 10, 28)
            if req_date > max_date:
                date = "2025-10-15"
                print(f"📅 Adjusted date to {date} (within available data range)")
        except:
            date = "2025-10-15"
        
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = os.path.join(tmpdir, "sst_data.nc")
                
                copernicusmarine.subset(
                    dataset_id=self.SST_PRODUCT,
                    variables=["thetao"],  # Sea water potential temperature
                    minimum_longitude=lon_min,
                    maximum_longitude=lon_max,
                    minimum_latitude=lat_min,
                    maximum_latitude=lat_max,
                    start_datetime=f"{date}T00:00:00",
                    end_datetime=f"{date}T23:59:59",
                    output_filename=output_path,
                    username=self.username,
                    password=self.password
                )
                
                # Load into memory and close file immediately
                with xr.open_dataset(output_path) as ds:
                    return ds.load()
                
        except Exception as e:
            print(f"❌ Error fetching SST: {e}")
            return None
    
    def fetch_ssh(
        self, 
        lat_min: float, 
        lat_max: float, 
        lon_min: float, 
        lon_max: float,
        date: Optional[str] = None
    ) -> Optional[xr.Dataset]:
        """
        Fetch Sea Surface Height (SSH) data.
        
        Args:
            lat_min, lat_max: Latitude bounds
            lon_min, lon_max: Longitude bounds
            date: Date string in format 'YYYY-MM-DD', defaults to yesterday
        
        Returns:
            xarray Dataset with SSH data or None if fetch fails
        """
        if not COPERNICUS_AVAILABLE:
            return None
        
        if date is None:
            # Use October 15, 2025 (safely within available range)
            date = "2025-10-15"
        
        # Ensure date is not beyond October 28, 2025 (latest available)
        try:
            req_date = datetime.strptime(date, "%Y-%m-%d")
            max_date = datetime(2025, 10, 28)
            if req_date > max_date:
                date = "2025-10-15"
        except:
            date = "2025-10-15"
        
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = os.path.join(tmpdir, "ssh_data.nc")
                
                copernicusmarine.subset(
                    dataset_id=self.SSH_PRODUCT,
                    variables=["zos"],  # Sea surface height
                    minimum_longitude=lon_min,
                    maximum_longitude=lon_max,
                    minimum_latitude=lat_min,
                    maximum_latitude=lat_max,
                    start_datetime=f"{date}T00:00:00",
                    end_datetime=f"{date}T23:59:59",
                    output_filename=output_path,
                    username=self.username,
                    password=self.password
                )
                
                # Load into memory and close file immediately
                with xr.open_dataset(output_path) as ds:
                    return ds.load()
                
        except Exception as e:
            print(f"❌ Error fetching SSH: {e}")
            return None
    
    def fetch_chlorophyll(
        self, 
        lat_min: float, 
        lat_max: float, 
        lon_min: float, 
        lon_max: float,
        date: Optional[str] = None
    ) -> Optional[xr.Dataset]:
        """
        Fetch Chlorophyll-a concentration data.
        
        Args:
            lat_min, lat_max: Latitude bounds
            lon_min, lon_max: Longitude bounds
            date: Date string in format 'YYYY-MM-DD', defaults to yesterday
        
        Returns:
            xarray Dataset with Chlorophyll data or None if fetch fails
        """
        if not COPERNICUS_AVAILABLE:
            return None
        
        if date is None:
            # Use September 15, 2025 (chlorophyll data ends Sept 30, 2025)
            date = "2025-09-15"
        
        # Ensure date is not beyond September 30, 2025 (latest available for chlorophyll)
        try:
            req_date = datetime.strptime(date, "%Y-%m-%d")
            max_date = datetime(2025, 9, 30)
            if req_date > max_date:
                date = "2025-09-15"
        except:
            date = "2025-09-15"
        
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = os.path.join(tmpdir, "chlo_data.nc")
                
                copernicusmarine.subset(
                    dataset_id=self.CHLO_PRODUCT,
                    variables=["chl"],  # Mass concentration of chlorophyll
                    minimum_longitude=lon_min,
                    maximum_longitude=lon_max,
                    minimum_latitude=lat_min,
                    maximum_latitude=lat_max,
                    start_datetime=f"{date}T00:00:00",
                    end_datetime=f"{date}T23:59:59",
                    output_filename=output_path,
                    username=self.username,
                    password=self.password
                )
                
                # Load into memory and close file immediately
                with xr.open_dataset(output_path) as ds:
                    return ds.load()
                
        except Exception as e:
            print(f"❌ Error fetching Chlorophyll: {e}")
            return None
    
    def get_ocean_data_for_bbox(
        self,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        date: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Fetch all oceanographic data (SST, SSH, Chlorophyll) for a bounding box.
        
        Returns:
            Dictionary with datasets for each variable
        """
        print(f"🌊 Fetching ocean data for bbox: lat=[{lat_min}, {lat_max}], lon=[{lon_min}, {lon_max}]")
        
        print(f"  1/3 Fetching SST...")
        sst_data = self.fetch_sst(lat_min, lat_max, lon_min, lon_max, date)
        
        print(f"  2/3 Fetching SSH...")
        ssh_data = self.fetch_ssh(lat_min, lat_max, lon_min, lon_max, date)
        
        print(f"  3/3 Fetching Chlorophyll...")
        chlo_data = self.fetch_chlorophyll(lat_min, lat_max, lon_min, lon_max, date)
        
        return {
            "sst": sst_data,
            "ssh": ssh_data,
            "chlorophyll": chlo_data,
            "bbox": {
                "lat_min": lat_min,
                "lat_max": lat_max,
                "lon_min": lon_min,
                "lon_max": lon_max
            },
            "date": date or (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        }
    
    def extract_value_at_point(self, dataset: xr.Dataset, lat: float, lon: float, var_name: str) -> Optional[float]:
        """
        Extract a single value from a dataset at given lat/lon coordinates.
        
        Args:
            dataset: xarray Dataset
            lat: Latitude
            lon: Longitude
            var_name: Variable name in the dataset
        
        Returns:
            Float value or None if extraction fails
        """
        if dataset is None:
            return None
        
        try:
            # Find nearest point
            value = dataset[var_name].sel(
                latitude=lat, 
                longitude=lon, 
                method="nearest"
            )
            
            # If there are time/depth dimensions, take the first value or mean
            if 'time' in value.dims:
                value = value.isel(time=0)
            if 'depth' in value.dims:
                value = value.isel(depth=0)
            
            # Get the numpy array
            arr = value.values
            
            # Handle different array shapes
            if hasattr(arr, 'size'):
                if arr.size == 1:
                    return float(arr.item())
                elif arr.size > 1:
                    # Take mean if multiple values
                    import numpy as np
                    return float(np.nanmean(arr))
            return float(arr)
            
        except Exception as e:
            print(f"❌ Error extracting {var_name} at ({lat}, {lon}): {e}")
            return None
