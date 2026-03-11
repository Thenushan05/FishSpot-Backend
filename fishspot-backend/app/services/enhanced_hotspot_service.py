"""
Enhanced hotspot prediction service that integrates Copernicus Marine data.
Fetches SST, SSH, SSS, and Chlorophyll data for grid cells and runs ML predictions.
"""
from typing import List, Dict, Optional
from datetime import datetime
import math
import numpy as np

from app.services.free_ocean_data_service import FreeOceanDataService, _fetch_sst, _fetch_ssh
from app.services.copernicus_service import CopernicusService
from app.services import ml_hotspot
from app.services.monsoon_classifier import classify_monsoon


class EnhancedHotspotService:
    """
    Hotspot service that fetches real oceanographic data from Copernicus
    and runs ML model predictions.  SSS, SSD, and Chlorophyll-a are now
    fetched in real-time from free NOAA CoastWatch ERDDAP APIs (SMAP/SMOS/VIIRS).
    """
    
    def __init__(self):
        self.copernicus = CopernicusService()
        self.free_ocean = FreeOceanDataService()
    
    def predict_with_weather_data(
        self,
        cells: List[Dict[str, float]],
        date: Optional[str] = None,
        species: str = "YFT",
    ) -> List[Dict]:
        """
        Predict hotspot scores for grid cells with real-time weather data.
        
        Args:
            cells: List of dicts with 'lat' and 'lon' keys
            date:  Optional date string 'YYYY-MM-DD', defaults to yesterday
            species: Species code (YFT, BET, SWO, BLM …) passed to ML model
        
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
        print(f"\u23f3 Fetching oceanographic data (SST/SSH via NRT satellite sources)...")
        
        from app.services import depth_service
        from concurrent.futures import ThreadPoolExecutor as _TPE
        import json

        # ── SST per-point via NRT satellite (same sources as test_5points.py) ──
        try:
            with _TPE(max_workers=min(len(lats), 5)) as ex:
                sst_futures = [ex.submit(_fetch_sst, lat, lon) for lat, lon in zip(lats, lons)]
                sst_results = [f.result() for f in sst_futures]
            print(f"\u2705 Fetched SST from NRT satellite for {len(sst_results)} points")
        except Exception as e:
            print(f"\u274c SST NRT fetch failed: {e}")
            sst_results = [(None, 'fetch_error') for _ in lats]

        # ── SSH per unique 0.25° grid cell (parallel), fallback to centre ──
        # Points within 10 km are likely in 1-2 cells at 0.25° resolution.
        # Fetch each unique cell once in parallel, assign nearest value to each point.
        def _grid_key(lat, lon, res=0.25):
            return (round(lat / res) * res, round(lon / res) * res)

        centre_lat = (min(lats) + max(lats)) / 2.0
        centre_lon = (min(lons) + max(lons)) / 2.0

        unique_cells = {}
        for lat, lon in zip(lats, lons):
            key = _grid_key(lat, lon)
            unique_cells[key] = key  # (cell_lat, cell_lon)

        print(f"\u23f3 Fetching SSH for {len(unique_cells)} unique 0.25\u00b0 grid cell(s)...")
        try:
            with _TPE(max_workers=min(len(unique_cells), 4)) as ex:
                ssh_futures = {
                    key: ex.submit(_fetch_ssh, clat, clon)
                    for key, (clat, clon) in unique_cells.items()
                }
                ssh_by_cell = {key: fut.result() for key, fut in ssh_futures.items()}
            # Fall back to centre if any cell returned None
            centre_key = _grid_key(centre_lat, centre_lon)
            if centre_key not in ssh_by_cell or ssh_by_cell[centre_key][0] is None:
                if any(v[0] is not None for v in ssh_by_cell.values()):
                    # Use any successful cell value for centre
                    for key, (val, src) in ssh_by_cell.items():
                        if val is not None:
                            ssh_by_cell[centre_key] = (val, src)
                            break
                else:
                    # All failed — fetch centre as last resort
                    ssh_by_cell[centre_key] = _fetch_ssh(centre_lat, centre_lon)
            for key, (val, src) in ssh_by_cell.items():
                if val is not None:
                    print(f"\u2705 SSH cell {key}: {val:.4f} m  [{src[:60]}]")
        except Exception as e:
            print(f"\u274c SSH fetch failed: {e}")
            ssh_by_cell = {_grid_key(centre_lat, centre_lon): (None, 'fetch_error')}

        def _ssh_for_point(lat, lon):
            key = _grid_key(lat, lon)
            if key in ssh_by_cell:
                return ssh_by_cell[key]
            # nearest cell fallback
            best = min(ssh_by_cell.keys(), key=lambda k: (k[0]-lat)**2 + (k[1]-lon)**2)
            return ssh_by_cell[best]

        ocean_data_list = [
            {
                'sst': sst_results[i][0],
                'ssh': _ssh_for_point(lats[i], lons[i])[0],
                'sst_source': sst_results[i][1],
                'ssh_source': _ssh_for_point(lats[i], lons[i])[1],
            }
            for i in range(len(lats))
        ]
        
        # Fetch depths for all cells
        try:
            depth_results = depth_service.get_depths(lats, lons)
            print(f"✅ Fetched depths from GEBCO for {len(depth_results)} points")
        except Exception as e:
            print(f"❌ Depth fetch failed: {e}")
            depth_results = [{'value': None} for _ in lats]

        # --- Fetch real-time Chlorophyll-a, SSS, SSD from free NOAA ERDDAP ---
        sst_list = [
            (ocean_data_list[i].get('sst') if i < len(ocean_data_list) else None)
            for i in range(len(lats))
        ]
        try:
            free_ocean_results = self.free_ocean.get_ocean_vars(lats, lons, sst_list)
            print(f"✅ Fetched Chlo/SSS/SSD from free NOAA ERDDAP for {len(free_ocean_results)} points")
            # Log what was actually retrieved (shared values come from centre point)
            if free_ocean_results:
                r0 = free_ocean_results[0]
                sst0 = ocean_data_list[0].get('sst') if ocean_data_list else None
                print(f"   🌿 CHLO : {r0.get('chlo')}  [{r0.get('chlo_source','?')}]")
                print(f"   🌊 SSS  : {r0.get('sss')}   [{r0.get('sss_source','?')}]")
                print(f"   🔵 SSD  : {r0.get('ssd')}   [{r0.get('ssd_source','?')}]")
                print(f"   🌡️  SST  : {sst0}   [{ocean_data_list[0].get('sst_source','?') if ocean_data_list else '?'}]")
                print(f"   📡 SSH  : {ocean_data_list[0].get('ssh')}   [{ocean_data_list[0].get('ssh_source','?') if ocean_data_list else '?'}]")
        except Exception as e:
            print(f"❌ Free ocean data fetch failed: {e}")
            free_ocean_results = [
                {'chlo': 0.1, 'sss': 35.0, 'ssd': 1025.0,
                 'chlo_source': 'default', 'sss_source': 'default'}
                for _ in lats
            ]
        
        # Get current date components
        now = datetime.now()
        year = now.year
        month = now.month
        
        # Enrich each cell with oceanographic data
        enriched_cells = []
        for idx, cell in enumerate(cells):
            lat = cell['lat']
            lon = cell['lon']
            
            # Get SST/SSH from NRT satellite sources
            ocean_point = ocean_data_list[idx] if idx < len(ocean_data_list) else {'sst': None, 'ssh': None}
            sst = ocean_point.get('sst')
            ssh = ocean_point.get('ssh')
            sst_src = ocean_point.get('sst_source', '')
            ssh_src_pt = ocean_point.get('ssh_source', '')

            # Get real-time chlo / sss / ssd (None-safe: fallback to defaults if still None)
            free_pt = free_ocean_results[idx] if idx < len(free_ocean_results) else {}
            chlo_rt = free_pt.get('chlo')
            if chlo_rt is None:
                chlo_rt = 0.15
            sss_rt = free_pt.get('sss')
            if sss_rt is None:
                sss_rt = 34.5
            ssd_rt = free_pt.get('ssd')
            if ssd_rt is None:
                ssd_rt = 1025.0
            
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
                "chlo": chlo_rt,
                "sss": sss_rt,
                "ssd": ssd_rt,
                "chlo_source": free_pt.get('chlo_source', 'unknown'),
                "sss_source":  free_pt.get('sss_source',  'unknown'),
                "ssd_source":  free_pt.get('ssd_source',  'unknown'),
                "sst_source":  sst_src,
                "ssh_source":  ssh_src_pt,
                "monsoon": monsoon_name,
                "data_source": "nrt_satellite+copernicus"
            }
            
            # Print JSON log for first 3 cells
            if idx < 3:
                print(f"📊 Fetched data for cell {idx+1}:")
                print(json.dumps(fetched_data_log, indent=2))
            
            # ── Build the 23-feature dict the Pipeline's ColumnTransformer expects ──
            sst_v  = sst if sst is not None else 28.0
            ssh_v  = ssh if ssh is not None else 0.5
            chlo_v = max(float(chlo_rt), 1e-6)  # guard log(0)
            sss_v  = float(sss_rt)
            ssd_v  = float(ssd_rt)
            dep_abs = abs(depth) if depth is not None else 100.0

            month_sin = np.sin(2 * np.pi * month / 12)
            month_cos = np.cos(2 * np.pi * month / 12)
            lat_sin   = math.sin(math.radians(lat))
            lat_cos   = math.cos(math.radians(lat))
            lon_sin   = math.sin(math.radians(lon))
            lon_cos   = math.cos(math.radians(lon))

            enriched_cell = {
                # ── 23 model features (exact names verified from ColumnTransformer) ──
                'month':       month,
                'depth_abs':   dep_abs,
                'sss':         sss_v,
                'ssd':         ssd_v,
                'sst':         sst_v,
                'ssh':         ssh_v,
                'chlo':        chlo_v,
                'month_sin':   month_sin,
                'month_cos':   month_cos,
                'sst_x_chlo':  sst_v * chlo_v,
                'ssh_x_chlo':  ssh_v * chlo_v,
                'sst_x_ssh':   sst_v * ssh_v,
                'depth_x_sst': dep_abs * sst_v,
                'depth_x_chlo':dep_abs * chlo_v,
                'sst_squared': sst_v ** 2,
                'chlo_log':    np.log(chlo_v + 1e-6),
                'sss_x_sst':   sss_v * sst_v,
                'lat_sin':     lat_sin,
                'lat_cos':     lat_cos,
                'lon_sin':     lon_sin,
                'lon_cos':     lon_cos,
                'SPECIES_CODE': species,
                'monsoon':     monsoon_name,
                # ── Uppercase originals kept for response building in hotspots.py ──
                'SST':   sst_v,
                'SSH':   ssh_v,
                'CHLO':  chlo_v,
                'SSS':   sss_v,
                'SSD':   ssd_v,
                'DEPTH': depth,
                'LAT':   lat,
                'LON':   lon,
            }
            
            enriched_cells.append(enriched_cell)
        
        print(f"✅ Enriched {len(enriched_cells)} cells with oceanographic data")
        print(f"🤖 Running ML predictions...")
        
        # Run ML predictions
        predictions = ml_hotspot.predict_cells(enriched_cells)
        
        print(f"✅ Predictions complete!")
        
        # Add per-cell metadata to results (each prediction gets its own sources)
        for i, pred in enumerate(predictions):
            free_pt_i = free_ocean_results[i] if i < len(free_ocean_results) else (free_ocean_results[0] if free_ocean_results else {})
            ocean_pt_i = ocean_data_list[i] if i < len(ocean_data_list) else (ocean_data_list[0] if ocean_data_list else {})
            pred['data_source'] = 'nrt_satellite+copernicus'
            pred['data_date']   = now.strftime("%Y-%m-%d")
            pred['chlo_source'] = free_pt_i.get('chlo_source', 'unknown')
            pred['sss_source']  = free_pt_i.get('sss_source',  'unknown')
            pred['ssd_source']  = free_pt_i.get('ssd_source',  'unknown')
            pred['sst_source']  = ocean_pt_i.get('sst_source', 'unknown')
            pred['ssh_source']  = ocean_pt_i.get('ssh_source', 'unknown')
        
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
            
            _lat, _lon = cell['lat'], cell['lon']
            _sst, _ssh, _chlo = 28.0, 0.5, 0.1
            _sss, _ssd, _dep_abs = 35.0, 1025.0, 100.0
            _lat_sin = math.sin(math.radians(_lat))
            _lat_cos = math.cos(math.radians(_lat))
            _lon_sin = math.sin(math.radians(_lon))
            _lon_cos = math.cos(math.radians(_lon))
            enriched_cell = {
                # 23 model features
                'month':        now.month,
                'depth_abs':    _dep_abs,
                'sss':          _sss,
                'ssd':          _ssd,
                'sst':          _sst,
                'ssh':          _ssh,
                'chlo':         _chlo,
                'month_sin':    month_sin,
                'month_cos':    month_cos,
                'sst_x_chlo':   _sst * _chlo,
                'ssh_x_chlo':   _ssh * _chlo,
                'sst_x_ssh':    _sst * _ssh,
                'depth_x_sst':  _dep_abs * _sst,
                'depth_x_chlo': _dep_abs * _chlo,
                'sst_squared':  _sst ** 2,
                'chlo_log':     np.log(_chlo + 1e-6),
                'sss_x_sst':    _sss * _sst,
                'lat_sin':      _lat_sin,
                'lat_cos':      _lat_cos,
                'lon_sin':      _lon_sin,
                'lon_cos':      _lon_cos,
                'SPECIES_CODE': 'YFT',
                'monsoon':      monsoon_name,
                # originals for response
                'SST': _sst, 'SSH': _ssh, 'CHLO': _chlo,
                'SSS': _sss, 'SSD': _ssd, 'DEPTH': -100.0,
                'LAT': _lat, 'LON': _lon,
            }
            enriched_cells.append(enriched_cell)
        
        return ml_hotspot.predict_cells(enriched_cells)
