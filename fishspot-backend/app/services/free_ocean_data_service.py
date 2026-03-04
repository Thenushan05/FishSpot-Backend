"""
Free Real-Time Ocean Data Service
===================================
Fetches Chlorophyll-a (CHLO), Sea Surface Salinity (SSS),
Sea Surface Density (SSD), Depth, SSH, and SST using only
free, public data sources (no API key required except Copernicus,
for which credentials are in .env).

Source hierarchy:

Source map:
  NOAA CoastWatch ERDDAP  → SST, SSS, Chlorophyll-a
  Copernicus Marine API   → SSH, SSD

  SST (Sea Surface Temperature, °C):
    1. PRIMARY  — NOAA CoastWatch ERDDAP: noaacwBLENDEDsstDaily  (analysed_sst, 0.01°/daily)
    2. FALLBACK — NASA/JPL MUR NRT 0.01° daily      [jplMURSST41 @ PFEG ERDDAP]
    3. FALLBACK — NOAA OISST v2.1 NRT 0.25°         [ncdcOisst21NrtAgg @ PFEG]
    4. FALLBACK — NOAA OISST v2.1 full archive 0.25° [ncdcOisst21Agg @ PFEG]
    5. FALLBACK — AVHRR Pathfinder SST 0.04° daily  [erdATssta1day @ PFEG]
    6. FALLBACK — NOAA CoralTemp NRT 0.05°           [NOAA_DHW @ OceanWatch]
    7. LAST RESORT — hint value from Open-Meteo / default 28°C

  SSS (Sea Surface Salinity, PSU):
    1. PRIMARY  — NOAA CoastWatch ERDDAP: noaacwSMAPsssDaily  (sss)
    2. FALLBACK — NOAA CoastWatch SMOS  [noaacwSMOSsss3day / Daily]
    3. FALLBACK — OceanWatch RSS SMOS L3 8-day / 2-day blended
    4. FALLBACK — SMOS wide-tier retry (up to 28 days, ±10°)
    5. LAST RESORT — Geographic climatology (WOA-2018 annual means)

  CHLO (Chlorophyll-a, mg/m³):
    1. PRIMARY  — NOAA CoastWatch ERDDAP: noaacwNPPVIIRSchlaDaily  (chlor_a)
    2. FALLBACK — NOAA CoastWatch VIIRS gapfilled + NOAA-20 [PFEG ERDDAP]
    3. FALLBACK — Sentinel-3A OLCI + OceanWatch VIIRS-SNPP
    4. FALLBACK — CoastWatch NOAA-20 VIIRS chl_oci daily
    5. FALLBACK — Copernicus Marine OC NRT gap-free L4 + L3 multi-sensor
    6. FALLBACK — Wide-tier retry (up to 28 days, ±7°)
    7. LAST RESORT — Geographic climatology (WOA/SeaWiFS annual means)

  SSH (Sea Surface Height, m):
    1. PRIMARY  — Copernicus Marine NRT: SEALEVEL_GLO_PHY_L4_NRT_008_046  (adt, 0.25°/daily)
    2. FALLBACK — Copernicus Marine NRT ocean physics (zos, 0.083°/daily)
                  product: cmems_mod_glo_phy_anfc_0.083deg_P1D-m
    3. FALLBACK — Copernicus DUACS L3 NRT along-track sla_filtered (~5 km, 1 Hz)
    4. FALLBACK — ERDDAP-served AVISO SLA (PFEG / OceanWatch, no credentials)

  SSD (Sea Surface Density, kg/m³):
    1. PRIMARY  — Copernicus Marine: MULTIOBS_GLO_PHY_S_SURFACE_MYNRT_015_013  (sos → TEOS-10 density)
    2. FALLBACK — Copernicus Marine NRT ocean physics (sos from cmems_mod_glo_phy_anfc)
    3. FALLBACK — TEOS-10 gsw from locally-fetched SSS + SST (no HTTP)

  Depth (metres):
    Source: GEBCO 2025 sub-ice NetCDF  (local file)
"""

from __future__ import annotations

import csv
import math
import os
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Ensure stdout/stderr can handle Unicode (emojis, arrows, degree symbols) on
# Windows where the default console encoding is cp1252.
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ---------------------------------------------------------------------------
# ERDDAP server base URLs
# ---------------------------------------------------------------------------
_COASTWATCH = "https://coastwatch.noaa.gov/erddap/griddap"
_OCEANWATCH  = "https://oceanwatch.pifsc.noaa.gov/erddap/griddap"
_PFEG        = "https://coastwatch.pfeg.noaa.gov/erddap/griddap"

# ---------------------------------------------------------------------------
# GEBCO 2025 bathymetry file  (depth source)
# ---------------------------------------------------------------------------
_GEBCO_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "depth", "GEBCO_2025_sub_ice.nc")
)

# ---------------------------------------------------------------------------
# Dataset catalogue — each entry: (dataset_id, erddap_base, variable, has_alt_dim)
# has_alt_dim=True → insert [(0):(0)] after the time constraint in the query
# ---------------------------------------------------------------------------

# CHLO primary: NOAA CoastWatch VIIRS SNPP NRT daily (noaacwNPPVIIRSchlaDaily)
# Preferred source per source map; has_alt=True (CoastWatch dataset)
_CHLO_PRIMARY = [
    ("noaacwNPPVIIRSchlaDaily",                     _COASTWATCH, "chlor_a", True),  # CoastWatch VIIRS-SNPP NRT daily PRIMARY
    ("nesdisVHNnoaaSNPPnoaa20NRTchlaGapfilledDaily", _PFEG,       "chlor_a", True),  # NRT gapfilled SNPP+N20 daily (fallback)
    ("nesdisVHNnoaa20chlaDaily",                    _PFEG,       "chlor_a", True),  # NOAA-20 daily (fallback)
]

# CHLO fallback 1: CoastWatch S3A OLCI + OceanWatch VIIRS-SNPP
# Confirmed has_alt=True, valid Indian Ocean data 2-9 days ago
_CHLO_FALLBACK = [
    ("noaacwS3AOLCIchlaDaily",  _COASTWATCH, "chlor_a", True),   # Sentinel-3A OLCI daily (193 non-NaN, d-4)
    ("noaa_snpp_chla_daily",    _OCEANWATCH, "chlor_a", True),   # VIIRS-SNPP 4 km daily (2 non-NaN, d-9)
    ("noaa_snpp_chla_weekly",   _OCEANWATCH, "chlor_a", True),   # VIIRS-SNPP weekly composite
    ("nesdisVHNchlaDaily",      _PFEG,       "chlor_a", True),   # SNPP daily (has data, cloud-dependent)
]

# CHLO fallback 2: CoastWatch NOAA-20 VIIRS + PFEG VIIRS
# noaacwNPPN20VIIRSchlociDaily uses var chl_oci (CoastWatch-specific)
# NOTE: MODIS-Aqua/Terra removed — both satellites decommissioned Oct 2025
_CHLO_FALLBACK2 = [
    ("noaacwNPPN20VIIRSchlociDaily", _COASTWATCH, "chl_oci", True),   # NOAA-20 VIIRS chl_oci daily
    ("erdVHNchla1day", _PFEG, "chla", False),   # VIIRS NOAA-20/JPSS-1 1-day 0.1 deg
]

# CHLO fallback 3: OceanWatch VIIRS-SNPP weekly (replaces MODIS-Aqua archive which ended 2022)
_CHLO_FALLBACK3 = [
    ("noaa_snpp_chla_weekly",   _OCEANWATCH, "chlor_a", True),   # VIIRS-SNPP 4 km weekly composite
]

# CHLO fallback 4: OceanWatch hosted Sentinel-3A/B OLCI (may need has_alt=True)
_CHLO_NASA_OBDAAC = [
    ("noaa_s3a_olci_chla_daily", _OCEANWATCH, "chlor_a", True),   # Sentinel-3A OLCI daily
    ("noaa_s3b_olci_chla_daily", _OCEANWATCH, "chlor_a", True),   # Sentinel-3B OLCI daily
    ("noaa_s3_olci_chla_8day",   _OCEANWATCH, "chlor_a", True),   # OLCI 8-day composite
]

# Copernicus Marine Ocean Colour product IDs (via copernicusmarine Python library, requires credentials)
_CHLO_CMEMS_L4  = "cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D"  # gap-free L4, var CHL
_CHLO_CMEMS_L3  = "cmems_obs-oc_glo_bgc-plankton_nrt_l3-multi-4km_P1D"           # L3 NRT multi-sensor

# Copernicus Marine — SSH and SSD primary products (per source map)
# SSH  : product SEALEVEL_GLO_PHY_L4_NRT_008_046  — dataset below, var adt
_CMEMS_SSH_L4_DS = "cmems_obs-sl_glo_phy-ssh_nrt_allsat-l4-duacs-0.25deg_P1D"   # DUACS L4 NRT adt 0.25°
# SSD/SSS: product MULTIOBS_GLO_PHY_S_SURFACE_MYNRT_015_013 — NRT daily multi-satellite SSS, var sos
_CMEMS_MULTIOBS_SSD_DS = "cmems_obs-mob_glo_phy-sss_nrt_multi_P1D"   # confirmed: has sos, extends to ~d-7
# Archive fallback (longer record, same variables)
_CMEMS_MULTIOBS_MY_DS  = "cmems_obs-mob_glo_phy-sss_my_multi_P1D"    # MyOcean archive backup

# SSS primary: NOAA CoastWatch SMAP NRT
# Confirmed has_alt=True, 7 non-NaN for Sri Lanka (d-6), variable='sss'
_SSS_PRIMARY = [
    ("noaacwSMAPsssDaily",  _COASTWATCH, "sss", True),   # SMAP L3 NRT daily, 2015-present
]

# SSS fallback 1: NOAA CoastWatch SMOS
# Confirmed has_alt=True, variable='sss' (may be NaN-heavy in Indian Ocean)
_SSS_FALLBACK = [
    ("noaacwSMOSsss3day",  _COASTWATCH, "sss", True),   # SMOS 3-day composite, 2010-present
    ("noaacwSMOSsssDaily", _COASTWATCH, "sss", True),   # SMOS daily
]

# SSS fallback 2: OceanWatch RSS SMOS blended (moved up — Aquarius ended 2015, removed)
_SSS_FALLBACK2 = [
    ("RSS_smos_SSS_L3_8day", _OCEANWATCH, "sss", False),  # RSS SMOS 8-day blended
    ("RSS_smos_SSS_L3_2day", _OCEANWATCH, "sss", False),  # RSS SMOS 2-day composite
]

# SSS fallback 3: SMOS wide-tier (moved up; was FB4)
_SSS_FALLBACK3 = [
    ("noaacwSMOSsss3day",  _COASTWATCH, "sss", True),   # SMOS 3-day composite retry
]

# ---------------------------------------------------------------------------
# Progressive search tiers — (max_day_back, bbox_pad_degrees)
# As days increase past each threshold the bbox widens to find nearby swath data.
#
# SSS tiers (SMAP orbits repeat every ~3 days; orbital gaps resolved by widening):
#   Days  1-7  : ±2.0°   — local area, recent pass
#   Days  8-14 : ±4.0°   — regional nearby area
#   Days 15-20 : ±6.0°   — broad nearby area (same ocean province)
#
# CHLO tiers (cloud gaps common in tropical Indian Ocean):
#   Days  1-7  : ±0.25°  — exact location
#   Days  8-15 : ±1.5°   — nearby region
#   Days 16-20 : ±3.0°   — broad region
# ---------------------------------------------------------------------------
_SSS_TIERS       = [(5, 2.0), (10, 4.0), (15, 6.0)]   # normal range: up to 15 days
_SSS_TIERS_WIDE  = [(15, 6.0), (21, 8.0), (28, 10.0)] # last-resort: up to 28 days, ±10°
_CHLO_TIERS      = [(5, 0.25), (10, 1.5), (15, 2.5)]  # normal range: up to 15 days
_CHLO_TIERS_WIDE = [(15, 2.5), (21, 4.0), (28, 7.0)]  # last-resort: up to 28 days, ±7°

_CHLO_BBOX_PAD = 0.25   # kept for public API default
_SSS_BBOX_PAD  = 2.0    # kept for public API default


# ---------------------------------------------------------------------------
# Geographic climatology — absolute last resort when ALL satellite sources fail
# Based on World Ocean Atlas 2018 annual means for the Indian Ocean basin
# ---------------------------------------------------------------------------

def _sss_climatology(lat: float, lon: float) -> float:
    """
    Regional climatological SSS estimate for the Indian Ocean / Bay of Bengal.
    Used ONLY when all satellite and reanalysis sources are exhausted.
    Values from WOA-2018 annual means.
    """
    # Bay of Bengal — strongly freshened by river discharge (Ganges, Brahmaputra, Irrawaddy)
    if 5.0 <= lat <= 23.0 and 78.0 <= lon <= 100.0:
        # Northern Bay of Bengal even fresher
        if lat > 15.0:
            return 30.0
        return 32.5
    # Arabian Sea — high evaporation, saltier surface layer
    if 5.0 <= lat <= 26.0 and 50.0 <= lon <= 77.0:
        return 36.5
    # Equatorial Indian Ocean (mixed, moderate salinity)
    if -5.0 <= lat <= 5.0 and 55.0 <= lon <= 100.0:
        return 34.2
    # South Indian Ocean (subtropical gyre — high salinity zone)
    if -30.0 <= lat <= -5.0 and 30.0 <= lon <= 110.0:
        return 35.5
    # Mozambique Channel / SW Indian Ocean
    if -30.0 <= lat <= -10.0 and 30.0 <= lon <= 50.0:
        return 35.2
    # Global open ocean default
    return 34.5


def _chlo_climatology(lat: float, lon: float) -> float:
    """
    Regional climatological chlorophyll-a estimate.
    Used ONLY when all satellite sources are exhausted.
    Values from SeaWiFS/MODIS climatological composites.
    """
    # Coastal Sri Lanka / SW Bay of Bengal — seasonal upwelling, moderate-high
    if 5.0 <= lat <= 12.0 and 78.0 <= lon <= 85.0:
        return 0.35
    # Bay of Bengal open water — moderate productivity
    if 5.0 <= lat <= 22.0 and 80.0 <= lon <= 100.0:
        return 0.22
    # Arabian Sea — high seasonal productivity from SW monsoon upwelling
    if 8.0 <= lat <= 25.0 and 55.0 <= lon <= 77.0:
        return 0.40
    # Somalia / NW Indian Ocean upwelling zone
    if 3.0 <= lat <= 14.0 and 43.0 <= lon <= 55.0:
        return 0.55
    # Equatorial Indian Ocean — oligotrophic, very low
    if -5.0 <= lat <= 8.0 and 60.0 <= lon <= 95.0:
        return 0.08
    # South Indian Ocean sub-tropical gyre — oligotrophic
    if -35.0 <= lat <= -10.0 and 30.0 <= lon <= 110.0:
        return 0.10
    # Default tropical open ocean
    return 0.15

# ---------------------------------------------------------------------------
# Simple in-memory cache  {key: {'value': float, 'ts': float}}
# ---------------------------------------------------------------------------
_cache: Dict[str, dict] = {}
_CACHE_TTL = 3600  # seconds


def _ck(*parts) -> str:
    return "|".join(str(p) for p in parts)


def _cget(key: str) -> Optional[float]:
    e = _cache.get(key)
    if e and (time.monotonic() - e["ts"]) < _CACHE_TTL:
        return e["value"]
    return None


def _cset(key: str, v: float) -> None:
    _cache[key] = {"value": v, "ts": time.monotonic()}


# ---------------------------------------------------------------------------
# ERDDAP griddap CSV helper
# ---------------------------------------------------------------------------

def _erddap_fetch(
    base: str,
    dataset: str,
    variable: str,
    date_str: str,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    has_alt: bool = False,
    timeout: int = 8,
    time_of_day: str = "12:00:00",
) -> Optional[List[dict]]:
    """
    Fetch one ERDDAP griddap CSV slice.
    Returns list of row dicts (may be empty if all NaN), or None on HTTP/network error.
    has_alt=True inserts [(0):(0)] after the time constraint for datasets with an
    altitude dimension [time][altitude][lat][lon].
    time_of_day overrides the HH:MM:SS used in the time constraint (default 12:00:00).
    """
    alt = "[(0):(0)]" if has_alt else ""
    t = time_of_day
    q = (
        f"?{variable}"
        f"[({date_str}T{t}Z):({date_str}T{t}Z)]"
        f"{alt}"
        f"[({lat_min:.4f}):({lat_max:.4f})]"
        f"[({lon_min:.4f}):({lon_max:.4f})]"
    )
    url = f"{base}/{dataset}.csv{q}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FishSpot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None

    lines = [l for l in text.splitlines() if l.strip() and not l.startswith("#")]
    if not lines:
        return []
    return list(csv.DictReader(lines))


def _mean_valid(rows: List[dict], variable: str) -> Optional[float]:
    """Average non-NaN positive values from ERDDAP CSV rows."""
    if not rows:
        return None
    coord_cols = {"time", "latitude", "longitude", "altitude", "depth"}
    target = [k for k in rows[0] if k.lower().startswith(variable.lower())]
    if not target:
        target = [k for k in rows[0] if k.lower() not in coord_cols]
    if not target:
        return None

    vals = []
    for row in rows:
        for col in target:
            try:
                v = float(row[col])
                if not math.isnan(v) and v > -9e9 and v > 0:
                    vals.append(v)
                    break
            except (ValueError, TypeError):
                continue
    return float(sum(vals) / len(vals)) if vals else None


def _nearest_valid(
    rows: List[dict],
    variable: str,
    target_lat: float,
    target_lon: float,
) -> Optional[float]:
    """
    Return the value of the valid pixel *closest* to (target_lat, target_lon).

    Strategy:
      1. Find the row whose (latitude, longitude) is nearest to the target.
      2. If that pixel is valid (non-NaN, > -9e9), return it immediately.
      3. Otherwise return the next-closest valid pixel — so cloud gaps never
         force a fallback to a different day or dataset.
    This gives a true point-sample rather than a spatial average.
    """
    if not rows:
        return None
    coord_cols = {"time", "latitude", "longitude", "altitude", "depth"}
    target_cols = [k for k in rows[0] if k.lower().startswith(variable.lower())]
    if not target_cols:
        target_cols = [k for k in rows[0] if k.lower() not in coord_cols]
    if not target_cols:
        return None

    # Build list of (distance², value_or_None)
    candidates: list = []
    for row in rows:
        try:
            rlat = float(row.get("latitude", target_lat))
            rlon = float(row.get("longitude", target_lon))
            dist2 = (rlat - target_lat) ** 2 + (rlon - target_lon) ** 2
        except (ValueError, TypeError):
            dist2 = float("inf")
        val = None
        for col in target_cols:
            try:
                v = float(row[col])
                if not math.isnan(v) and v > -9e9 and v > 0:
                    val = v
                    break
            except (ValueError, TypeError):
                continue
        candidates.append((dist2, val))

    # Sort by proximity; return first valid pixel encountered
    candidates.sort(key=lambda x: x[0])
    for _, val in candidates:
        if val is not None:
            return round(val, 4)
    return None


# ---------------------------------------------------------------------------
# Session-level blacklist: datasets that returned HTTP 404 this session
# are skipped on subsequent requests to avoid wasting time.
# ---------------------------------------------------------------------------
_ds_blacklist: set = set()  # keys: (base, dataset_id)


# ---------------------------------------------------------------------------
# Internal: scan datasets with progressive bbox widening
# ---------------------------------------------------------------------------

def _bbox_pad_for_day(days_back: int, tiers: list) -> float:
    """
    Return the bbox pad (degrees) for the given days-back value.
    tiers: list of (threshold_day, pad) sorted ascending by threshold.
    The last tier is used for anything beyond the last threshold.
    """
    for threshold, pad in tiers:
        if days_back <= threshold:
            return pad
    return tiers[-1][1]  # use widest pad for anything beyond last tier


def _erddap_fetch_tracked(
    base: str, dataset: str, variable: str,
    date_str: str,
    lat_min: float, lat_max: float, lon_min: float, lon_max: float,
    has_alt: bool = False, time_of_day: str = "12:00:00", timeout: int = 8,
) -> Optional[List[dict]]:
    """
    Wrapper around _erddap_fetch that records 404 datasets in the session
    blacklist so they are skipped on future calls.
    """
    bk = (base, dataset)
    if bk in _ds_blacklist:
        return None

    alt = "[(0):(0)]" if has_alt else ""
    t = time_of_day
    q = (
        f"?{variable}"
        f"[({date_str}T{t}Z):({date_str}T{t}Z)]"
        f"{alt}"
        f"[({lat_min:.4f}):({lat_max:.4f})]"
        f"[({lon_min:.4f}):({lon_max:.4f})]"
    )
    url = f"{base}/{dataset}.csv{q}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FishSpot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            _ds_blacklist.add(bk)  # permanent 404 → blacklist for this session
        return None
    except Exception:
        return None

    lines = [l for l in text.splitlines() if l.strip() and not l.startswith("#")]
    if not lines:
        return []
    return list(csv.DictReader(lines))


def _try_datasets(
    label: str,
    datasets: list,
    centre_lat: float,
    centre_lon: float,
    tiers: list,
) -> Tuple[Optional[float], Optional[str]]:
    """
    Try datasets day by day (most-recent first), returning as soon as any
    dataset yields valid data. This gives real-time data when available and
    falls back gracefully up to max_days without wasting time on later days
    when earlier ones succeed.
    """
    max_days = tiers[-1][0]
    today = date.today()

    for days_back in range(1, max_days + 1):
        pad = _bbox_pad_for_day(days_back, tiers)
        d = (today - timedelta(days=days_back)).isoformat()
        lat_min, lat_max = centre_lat - pad, centre_lat + pad
        lon_min, lon_max = centre_lon - pad, centre_lon + pad

        # Check cache first — if any dataset has a cached hit for this day, return it
        for ds_id, base, var, has_alt in datasets:
            ck = _ck(label, ds_id, d, round(lat_min, 1), round(lon_min, 1))
            cached = _cget(ck)
            if cached is not None:
                return cached, f"{ds_id} (cached {d}, pad={pad} deg)"

        # Filter non-blacklisted datasets
        active = [(ds_id, base, var, has_alt) for ds_id, base, var, has_alt in datasets
                  if (base, ds_id) not in _ds_blacklist]
        if not active:
            continue

        # Try all active datasets for this day in parallel
        def _worker(ds_id, base, var, has_alt, d=d,
                    lat_min=lat_min, lat_max=lat_max,
                    lon_min=lon_min, lon_max=lon_max, pad=pad):
            rows = _erddap_fetch_tracked(base, ds_id, var, d, lat_min, lat_max,
                                         lon_min, lon_max, has_alt=has_alt, timeout=8)
            if rows is None:
                return None
            val = _mean_valid(rows, var)
            if val is not None:
                ck = _ck(label, ds_id, d, round(lat_min, 1), round(lon_min, 1))
                _cset(ck, val)
                return (val, ds_id, d, pad)
            return None

        hits = []
        with ThreadPoolExecutor(max_workers=min(len(active), 4)) as ex:
            futures = [ex.submit(_worker, ds_id, base, var, has_alt)
                       for ds_id, base, var, has_alt in active]
            for fut in as_completed(futures):
                r = fut.result()
                if r is not None:
                    hits.append(r)

        if hits:
            # All hits are for same days_back; pick any (first is fine)
            val, ds_id, d, pad = hits[0]
            note = " [nearby area]" if pad > tiers[0][1] else ""
            return val, f"{ds_id} | {d}{note} (+-{pad} deg)"

    return None, None


# ---------------------------------------------------------------------------# Per-point helpers: single bbox request → nearest-neighbour per (lat, lon)
# ---------------------------------------------------------------------------

def _nearest_val_per_point(
    rows: List[dict],
    lats: List[float],
    lons: List[float],
    variable: str,
) -> List[Optional[float]]:
    """
    From ERDDAP griddap rows, assign the nearest-neighbour grid value to each
    target (lat, lon).  Returns a list of float|None, same length as lats.
    """
    if not rows:
        return [None] * len(lats)

    coord_cols = {"time", "latitude", "longitude", "altitude", "depth"}
    # Find the value column (prefer columns whose name starts with the variable name)
    val_cols = [k for k in rows[0] if k.lower().startswith(variable.lower())]
    if not val_cols:
        val_cols = [k for k in rows[0] if k.lower() not in coord_cols]
    if not val_cols:
        return [None] * len(lats)
    vcol = val_cols[0]

    # Parse all valid (rlat, rlon, value) triples from the grid response
    grid_pts: List[Tuple[float, float, float]] = []
    for row in rows:
        try:
            rlat = float(row.get("latitude") or row.get("lat") or "nan")
            rlon = float(row.get("longitude") or row.get("lon") or "nan")
            v    = float(row[vcol])
            if math.isnan(rlat) or math.isnan(rlon) or math.isnan(v) or v <= 0 or v < -9e9:
                continue
            grid_pts.append((rlat, rlon, v))
        except (ValueError, TypeError, KeyError):
            continue

    if not grid_pts:
        return [None] * len(lats)

    # Nearest-neighbour (Euclidean in degree-space, fine at 10-km scale)
    result: List[Optional[float]] = []
    for lat, lon in zip(lats, lons):
        best_v, best_d = None, float("inf")
        for rlat, rlon, v in grid_pts:
            d = (rlat - lat) ** 2 + (rlon - lon) ** 2
            if d < best_d:
                best_d, best_v = d, v
        result.append(best_v)
    return result


def _try_datasets_per_point(
    label: str,
    datasets: list,
    lats: List[float],
    lons: List[float],
    tiers: list,
) -> Tuple[Optional[List[float]], Optional[str]]:
    """
    Issue ONE bbox request per (dataset, date) that covers ALL target points,
    searching day by day (most-recent first) and returning as soon as any
    dataset yields values for at least half the target points.

    Returns (list_of_values, source_str) or (None, None) if nothing found.
    """
    lat_min_pts, lat_max_pts = min(lats), max(lats)
    lon_min_pts, lon_max_pts = min(lons), max(lons)
    centre_lat = (lat_min_pts + lat_max_pts) / 2.0
    centre_lon = (lon_min_pts + lon_max_pts) / 2.0
    max_days = tiers[-1][0]
    today = date.today()
    min_valid = max(1, len(lats) // 2)

    for days_back in range(1, max_days + 1):
        pad = _bbox_pad_for_day(days_back, tiers)
        lat_min = min(lat_min_pts, centre_lat - pad)
        lat_max = max(lat_max_pts, centre_lat + pad)
        lon_min = min(lon_min_pts, centre_lon - pad)
        lon_max = max(lon_max_pts, centre_lon + pad)
        d = (today - timedelta(days=days_back)).isoformat()

        active = [(ds_id, base, var, has_alt) for ds_id, base, var, has_alt in datasets
                  if (base, ds_id) not in _ds_blacklist]
        if not active:
            continue

        def _worker_pp(ds_id, base, var, has_alt, d=d,
                       lat_min=lat_min, lat_max=lat_max,
                       lon_min=lon_min, lon_max=lon_max, pad=pad):
            rows = _erddap_fetch_tracked(base, ds_id, var, d, lat_min, lat_max,
                                          lon_min, lon_max, has_alt=has_alt, timeout=6)
            if rows is None:
                return None
            vals = _nearest_val_per_point(rows, lats, lons, var)
            valid_count = sum(1 for v in vals if v is not None)
            if valid_count < min_valid:
                return None
            return (vals, ds_id, d, pad, valid_count)

        hits = []
        with ThreadPoolExecutor(max_workers=min(len(active), 4)) as ex:
            futures = [ex.submit(_worker_pp, ds_id, base, var, has_alt)
                       for ds_id, base, var, has_alt in active]
            for fut in as_completed(futures):
                r = fut.result()
                if r is not None:
                    hits.append(r)

        if hits:
            # Pick result with most valid points; all are for same days_back
            vals, ds_id, d, pad, valid_count = max(hits, key=lambda x: x[4])
            # Fill any remaining None with the mean of valid values
            valid_vals = [v for v in vals if v is not None]
            fill = sum(valid_vals) / len(valid_vals)
            vals_filled = [v if v is not None else fill for v in vals]
            note = " [nearby area]" if pad > tiers[0][1] else ""
            return vals_filled, f"{ds_id} | {d}{note} per-point (+-{pad} deg)"

    return None, None


# ---------------------------------------------------------------------------# CHLO: NOAA CoastWatch NRT VIIRS  →  NASA Ocean Color fallback
# ---------------------------------------------------------------------------

def _fetch_chlo_copernicus(lat: float, lon: float) -> Tuple[Optional[float], str]:
    """
    Copernicus Marine Ocean Colour NRT — gap-free L4 then L3 multi-sensor.
    Products: cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D  (preferred)
              cmems_obs-oc_glo_bgc-plankton_nrt_l3-multi-4km_P1D          (fallback)
    Variable: CHL  (chlorophyll-a, mg/m³)
    Requires CMEMS_USERNAME / CMEMS_PASSWORD in environment.
    """
    username = os.environ.get("CMEMS_USERNAME", "") or os.environ.get("COPERNICUS_USERNAME", "")
    password = os.environ.get("CMEMS_PASSWORD", "") or os.environ.get("COPERNICUS_PASSWORD", "")
    if not username or not password:
        return None, "Copernicus credentials not configured"
    try:
        import copernicusmarine  # type: ignore
    except ImportError:
        return None, "copernicusmarine package not installed"

    for prod_id in (_CHLO_CMEMS_L4, _CHLO_CMEMS_L3):
        val, src = _cmems_fetch_scalar(
            prod_id, "CHL", lat, lon, "chlo_cmems", username, password, pad=0.25
        )
        if val is not None:
            return val, f"Copernicus Marine OC | {prod_id}"
    return None, "Copernicus Marine OC: all products returned no data"


def _fetch_chlo_cmems_wider(lat: float, lon: float) -> Tuple[Optional[float], str]:
    """
    Last-resort CHLO: Copernicus gap-free L4 with a wider bbox (2.0°) to guarantee
    finding at least one gap-filled pixel. This product has 100% spatial coverage.
    """
    username = os.environ.get("CMEMS_USERNAME", "") or os.environ.get("COPERNICUS_USERNAME", "")
    password = os.environ.get("CMEMS_PASSWORD", "") or os.environ.get("COPERNICUS_PASSWORD", "")
    if not username or not password:
        return None, "Copernicus credentials not configured"
    try:
        import copernicusmarine  # type: ignore
    except ImportError:
        return None, "copernicusmarine package not installed"
    # Gap-free L4 first (always has data), then L3 multi-sensor
    for prod_id in (_CHLO_CMEMS_L4, _CHLO_CMEMS_L3):
        val, src = _cmems_fetch_scalar(
            prod_id, "CHL", lat, lon, "chlo_cmems_wide", username, password, pad=2.0
        )
        if val is not None:
            return val, f"Copernicus Marine OC gap-free L4 (wide bbox) | {prod_id} | {src.split('|')[-1].strip()}"
    return None, "Copernicus Marine OC wide: no data"


def _fetch_sss_cmems_model(lat: float, lon: float) -> Tuple[Optional[float], str]:
    """
    Last-resort SSS: Copernicus Marine MULTIOBS NRT multi-satellite SSS fusion.
    cmems_obs-mob_glo_phy-sss_nrt_multi_P1D has near-global coverage via SMAP + SMOS + Argo.
    Fallback: MyOcean reanalysis archive (cmems_obs-mob_glo_phy-sss_my_multi_P1D).
    """
    username = os.environ.get("CMEMS_USERNAME", "") or os.environ.get("COPERNICUS_USERNAME", "")
    password = os.environ.get("CMEMS_PASSWORD", "") or os.environ.get("COPERNICUS_PASSWORD", "")
    if not username or not password:
        return None, "Copernicus credentials not configured"
    try:
        import copernicusmarine  # type: ignore
    except ImportError:
        return None, "copernicusmarine package not installed"
    # NRT (lags ~7 days)
    val, src = _cmems_fetch_scalar(
        _CMEMS_MULTIOBS_SSD_DS, "sos",
        lat, lon, "sss_multiobs_nrt", username, password, pad=0.5, max_days_back=14,
    )
    if val is not None:
        return val, f"Copernicus MULTIOBS NRT SSS (sos) | {src.split('|')[-1].strip()}"
    # Archive fallback (identical variables, longer record)
    val, src = _cmems_fetch_scalar(
        _CMEMS_MULTIOBS_MY_DS, "sos",
        lat, lon, "sss_multiobs_my", username, password, pad=0.5, max_days_back=30,
    )
    if val is not None:
        return val, f"Copernicus MULTIOBS MyOcean SSS (sos) | {src.split('|')[-1].strip()}"
    return None, "Copernicus MULTIOBS SSS: no data"


def _fetch_chlo(centre_lat: float, centre_lon: float) -> Tuple[Optional[float], str]:
    """
    Fetch chlorophyll-a with progressive bbox widening and primary/fallback logging.

    Fallback chain:
      1. PRIMARY  — NOAA CoastWatch NRT VIIRS-SNPP / NOAA-20
      2. FALLBACK1 — NASA Ocean Color MODIS-Aqua + ESA OC-CCI (wider tiers)
      3. FALLBACK2 — PFEG ERDDAP VIIRS / MODIS Aqua / MODIS Terra (0.025° products)
      4. FALLBACK3 — PACE/OCI NRT + MODIS monthly (broadest time window)
      5. FALLBACK4 — NASA OB.DAAC Sentinel-3 OLCI 300 m (OceanWatch ERDDAP)
      6. FALLBACK5 — Copernicus Marine OC NRT gap-free L4 (copernicusmarine)
      7. FALLBACK6 — Wider tiers on PFEG products (up to 28 days, ±7°)
      8. LAST RESORT — Geographic climatology from WOA/SeaWiFS means
    """
    print("   🌿 [CHLO] PRIMARY: NOAA CoastWatch NRT VIIRS-SNPP / NOAA-20 (progressive search)...")
    val, src = _try_datasets("chlo_primary", _CHLO_PRIMARY, centre_lat, centre_lon, _CHLO_TIERS)
    if val is not None:
        print(f"   ✅ [CHLO PRIMARY] {val:.4f} mg/m³  [{src}]")
        return val, f"NOAA CoastWatch NRT VIIRS | {src}"

    print("   ⚠️  [CHLO FB1] No data — NASA Ocean Color (MODIS-Aqua / ESA OC-CCI)...")
    val, src = _try_datasets("chlo_fallback1", _CHLO_FALLBACK, centre_lat, centre_lon, [(7, 1.5), (14, 3.0)])
    if val is not None:
        print(f"   ✅ [CHLO FB1] {val:.4f} mg/m³  [{src}]")
        return val, f"NASA Ocean Color / ESA OC-CCI | {src}"

    print("   ⚠️  [CHLO FB2] No data — PFEG ERDDAP VIIRS / MODIS Aqua / Terra...")
    val, src = _try_datasets("chlo_fallback2", _CHLO_FALLBACK2, centre_lat, centre_lon, [(7, 1.5), (14, 3.0)])
    if val is not None:
        print(f"   ✅ [CHLO FB2] {val:.4f} mg/m³  [{src}]")
        return val, f"PFEG ERDDAP VIIRS/MODIS | {src}"

    print("   ⚠️  [CHLO FB3] No data — PACE/OCI NRT + MODIS monthly composite...")
    val, src = _try_datasets("chlo_fallback3", _CHLO_FALLBACK3, centre_lat, centre_lon, [(14, 3.0), (21, 5.0)])
    if val is not None:
        print(f"   ✅ [CHLO FB3] {val:.4f} mg/m³  [{src}]")
        return val, f"PACE/OCI or MODIS monthly | {src}"

    print("   ⚠️  [CHLO FB4] No data — NASA OB.DAAC Sentinel-3 OLCI 300 m (OceanWatch)...")
    val, src = _try_datasets("chlo_fallback4", _CHLO_NASA_OBDAAC, centre_lat, centre_lon, [(7, 1.5), (15, 3.0)])
    if val is not None:
        print(f"   ✅ [CHLO FB4] {val:.4f} mg/m³  [{src}]")
        return val, f"NASA OB.DAAC Sentinel-3 OLCI 300m | {src}"

    print("   ⚠️  [CHLO FB5] No data — Copernicus Marine OC NRT gap-free L4...")
    val, src = _fetch_chlo_copernicus(centre_lat, centre_lon)
    if val is not None:
        print(f"   ✅ [CHLO FB5] {val:.4f} mg/m³  [{src}]")
        return val, src

    print("   ⚠️  [CHLO FB6] No data — PFEG wide-tier retry (up to 28 days, ±7°)...")
    val, src = _try_datasets("chlo_fallback6", _CHLO_FALLBACK2, centre_lat, centre_lon, _CHLO_TIERS_WIDE)
    if val is not None:
        print(f"   ✅ [CHLO FB6-wide] {val:.4f} mg/m³  [{src}]")
        return val, f"PFEG ERDDAP VIIRS/MODIS wide-tile | {src}"

    print("   ⚠️  [CHLO FB7] All ERDDAP sources exhausted — Copernicus gap-free L4 (wide bbox 2°)...")
    val, src = _fetch_chlo_cmems_wider(centre_lat, centre_lon)
    if val is not None:
        print(f"   ✅ [CHLO FB7] {val:.4f} mg/m³  [{src}]")
        return val, src
    print("   ❌ [CHLO] All sources failed — no data available")
    return None, "No CHLO data available (all satellite + Copernicus sources failed)"


# ---------------------------------------------------------------------------
# SSS: NOAA CoastWatch SMAP NRT  →  NOAA CoastWatch SMOS fallback
# ---------------------------------------------------------------------------

def _fetch_sss(centre_lat: float, centre_lon: float) -> Tuple[Optional[float], str]:
    """
    Fetch SSS with extended fallback chain:
      1. PRIMARY  — NOAA CoastWatch SMAP NRT daily / 8-day
      2. FALLBACK1 — NOAA CoastWatch SMOS 3-day / daily / weekly
      3. FALLBACK2 — OceanWatch RSS SMOS L3 8-day / 2-day blended
      4. FALLBACK3 — Wide-tier retry on SMOS 3-day
      5. FALLBACK4 — Wide-tier retry on SMOS (up to 28 days, ±10°)
      6. FALLBACK5 — Copernicus Marine NRT physics model sos (cmems_mod_glo_phy_anfc)
    """
    print("   🌊 [SSS] PRIMARY: NOAA CoastWatch SMAP NRT daily (progressive search)...")
    val, src = _try_datasets("sss_primary", _SSS_PRIMARY, centre_lat, centre_lon, _SSS_TIERS)
    if val is not None:
        print(f"   ✅ [SSS PRIMARY] {val:.3f} PSU  [{src}]")
        return val, f"NOAA CoastWatch SMAP NRT | {src}"

    print("   ⚠️  [SSS FB1] SMAP exhausted — NOAA CoastWatch SMOS...")
    val, src = _try_datasets("sss_fallback1", _SSS_FALLBACK, centre_lat, centre_lon, _SSS_TIERS)
    if val is not None:
        print(f"   ✅ [SSS FB1] {val:.3f} PSU  [{src}]")
        return val, f"NOAA CoastWatch SMOS | {src}"

    print("   ⚠️  [SSS FB2] SMOS failed — OceanWatch RSS SMOS L3 blended...")
    val, src = _try_datasets("sss_fallback2", _SSS_FALLBACK2, centre_lat, centre_lon, [(14, 4.0), (21, 6.0)])
    if val is not None:
        print(f"   ✅ [SSS FB2] {val:.3f} PSU  [{src}]")
        return val, f"RSS SMOS L3 blended (OceanWatch) | {src}"

    print("   ⚠️  [SSS FB3] RSS SMOS failed — SMOS 3-day wide-tier retry...")
    val, src = _try_datasets("sss_fallback3", _SSS_FALLBACK3, centre_lat, centre_lon, [(14, 5.0), (21, 8.0)])
    if val is not None:
        print(f"   ✅ [SSS FB3] {val:.3f} PSU  [{src}]")
        return val, f"NOAA CoastWatch SMOS wide | {src}"

    print("   ⚠️  [SSS FB4] RSS SMOS failed — wide-tier retry on SMOS (28 days, ±10°)...")
    val, src = _try_datasets("sss_fallback4", _SSS_FALLBACK, centre_lat, centre_lon, _SSS_TIERS_WIDE)
    if val is not None:
        print(f"   ✅ [SSS FB4-wide] {val:.3f} PSU  [{src}]")
        return val, f"NOAA CoastWatch SMOS wide-tile | {src}"

    print("   ⚠️  [SSS FB5] All satellite sources failed — Copernicus Marine NRT physics model (sos)...")
    val, src = _fetch_sss_cmems_model(centre_lat, centre_lon)
    if val is not None:
        print(f"   ✅ [SSS FB5] {val:.3f} PSU  [{src}]")
        return val, src
    print("   ❌ [SSS] All sources failed — no data available")
    return None, "No SSS data available (all satellite + Copernicus sources failed)"


# ---------------------------------------------------------------------------
# DEPTH: from GEBCO 2025 sub-ice NetCDF file
# ---------------------------------------------------------------------------

def _fetch_depth_gebco(lat: float, lon: float) -> Tuple[float, str]:
    """
    Read ocean depth (positive metres) from GEBCO_2025_sub_ice.nc.
    GEBCO stores elevation; depth = -elevation for ocean cells.
    """
    print("   🏔️  [DEPTH] Reading from GEBCO 2025 NetCDF...")
    try:
        import xarray as xr  # type: ignore
        ds = xr.open_dataset(_GEBCO_PATH)

        # Detect coordinate names  (GEBCO uses 'lat'/'lon')
        lat_dim = "lat" if "lat" in ds.coords else "latitude"
        lon_dim = "lon" if "lon" in ds.coords else "longitude"

        # Detect elevation variable name
        elev_var = None
        for v in ds.data_vars:
            vl = v.lower()
            if "elev" in vl or "depth" in vl or vl == "z" or vl == "Band1":
                elev_var = v
                break
        if elev_var is None:
            elev_var = list(ds.data_vars.keys())[0]

        elev = float(
            ds[elev_var].sel({lat_dim: lat, lon_dim: lon}, method="nearest").values
        )
        ds.close()

        depth = -elev  # negative elevation → positive depth for ocean
        if elev >= 0:
            note = f"land (+{elev:.1f} m above sea level)"
            depth = 0.0
        else:
            note = f"{depth:.1f} m deep"
        print(f"   ✅ [DEPTH] {note}  [GEBCO 2025]")
        return depth, f"GEBCO 2025 | {note}"
    except Exception as e:
        print(f"   ⚠️  [DEPTH] GEBCO read failed: {e}")
        return 0.0, f"GEBCO failed: {str(e)[:60]}"


# ---------------------------------------------------------------------------
# SST datasets (free ERDDAP, no auth required)
# ---------------------------------------------------------------------------
#  PRIMARY  : NOAA CoastWatch ERDDAP — BLENDED SST NRT daily     (noaacwBLENDEDsstDaily, analysed_sst)
#  FALLBACK1: PFEG ERDDAP — NASA/JPL MUR NRT 0.01° daily        (jplMURSST41, T09Z)       ← GHRSST L4
#  FALLBACK2: PFEG ERDDAP — NOAA OISST v2.1 NRT 0.25°          (ncdcOisst21NrtAgg, T12Z)
#  FALLBACK3: PFEG ERDDAP — NOAA OISST v2.1 full archive 0.25°  (ncdcOisst21Agg)    — stable non-NRT
#  FALLBACK4: PFEG ERDDAP — AVHRR Pathfinder SST 0.04° daily   (erdATssta1day)
#  FALLBACK5: OceanWatch ERDDAP — CoralTemp NRT SST v3.1 0.05°  (NOAA_DHW)
#  FALLBACK6: Copernicus Marine NRT — thetao 0.083°             (cmems_mod_glo_phy_anfc_0.083deg_P1D-m)
#  LAST RESORT: Open-Meteo SST hint (from caller)

_BLENDED_SST   = ("noaacwBLENDEDsstDaily",  _COASTWATCH,  "analysed_sst", False, "12:00:00")
_MUR_DATASET   = ("jplMURSST41",            _PFEG,         "analysed_sst", False, "09:00:00")
_OISST_NRT     = ("ncdcOisst21NrtAgg",      _PFEG,         "sst",          True,  "12:00:00")
_OISST_ARC     = ("ncdcOisst21Agg",         _PFEG,         "sst",          True,  "12:00:00")
_AVHRR_SST     = ("erdATssta1day",          _PFEG,         "sst",          False, "12:00:00")
_CORALTEMP_SST = ("NOAA_DHW",               _OCEANWATCH,   "CRW_SST",      False, "12:00:00")
# Kept for backward-compat reference
_OISST_DATASET = _OISST_NRT


def _fetch_sst_erddap(
    datasets: list,
    lat: float,
    lon: float,
    pad: float = 0.1,
    max_days: int = 15,
) -> Tuple[Optional[float], str]:
    """ERDDAP griddap SST fetch — goes back max_days and returns first valid mean."""
    today = date.today()
    for days_back in range(1, max_days + 1):
        d = (today - timedelta(days=days_back)).isoformat()
        for ds_id, base, var, has_alt, t_of_day in datasets:
            ck = _ck("sst", ds_id, d, round(lat, 2), round(lon, 2))
            cached = _cget(ck)
            if cached is not None:
                # Convert any Kelvin values that may have been cached in earlier runs
                if cached > 200:
                    cached = round(cached - 273.15, 4)
                return cached, f"{ds_id} (cached {d})"
            rows = _erddap_fetch(
                base, ds_id, var, d,
                lat - pad, lat + pad, lon - pad, lon + pad,
                has_alt=has_alt, time_of_day=t_of_day,
            )
            if rows is None:
                continue
            # Use nearest valid pixel to the exact coordinate (not a spatial mean)
            val = _nearest_valid(rows, var, lat, lon)
            if val is not None:
                # GHRSST products (analysed_sst) are in Kelvin; convert to °C
                if val > 200:
                    val = round(val - 273.15, 4)
                _cset(ck, val)
                return val, f"{ds_id} | {d}"
    return None, "no data"


def _fetch_sst(lat: float, lon: float, hint: Optional[float] = None) -> Tuple[Optional[float], str]:
    """
    Fetch SST (sea surface temperature, °C).

      1. PRIMARY   — NOAA CoastWatch BLENDED SST NRT (noaacwBLENDEDsstDaily, analysed_sst)
      2. FALLBACK1 — NASA/JPL MUR NRT 0.01° daily (PFEG ERDDAP) [jplMURSST41]  ← GHRSST L4
      3. FALLBACK2 — NOAA OISST v2.1 NRT 0.25°          (PFEG)   [ncdcOisst21NrtAgg]
      4. FALLBACK3 — NOAA OISST v2.1 full archive 0.25°  (PFEG)   [ncdcOisst21Agg]
      5. FALLBACK4 — AVHRR Pathfinder SST 0.04° daily    (PFEG)   [erdATssta1day]
      6. FALLBACK5 — NOAA CoralTemp NRT 0.05°            (OceanWatch) [NOAA_DHW]
      7. FALLBACK6 — Copernicus Marine NRT thetao 0.083°  (cmems_mod_glo_phy_anfc)
      8. LAST RESORT — Open-Meteo hint (if provided by caller)
    """
    print("   🌡️  [SST] PRIMARY: NOAA CoastWatch BLENDED SST (noaacwBLENDEDsstDaily)...")
    val, src = _fetch_sst_erddap([_BLENDED_SST], lat, lon, pad=0.1)
    if val is not None:
        full_src = f"NOAA CoastWatch BLENDED SST NRT | {src}"
        print(f"   ✅ [SST PRIMARY] {val:.2f} °C  [{full_src}]")
        return val, full_src

    print("   ⚠️  [SST FB1] BLENDED failed — NASA/JPL MUR NRT 0.01° (jplMURSST41, PFEG)...")
    val, src = _fetch_sst_erddap([_MUR_DATASET], lat, lon, pad=0.1)
    if val is not None:
        full_src = f"NASA/JPL MUR NRT 0.01° | {src}"
        print(f"   ✅ [SST FB1] {val:.2f} °C  [{full_src}]")
        return val, full_src

    print("   ⚠️  [SST FB2] MUR exhausted — NOAA OISST v2.1 NRT 0.25°...")
    val, src = _fetch_sst_erddap([_OISST_NRT], lat, lon, pad=0.3)
    if val is not None:
        full_src = f"NOAA OISST v2.1 NRT 0.25° | {src}"
        print(f"   ✅ [SST FB2] {val:.2f} °C  [{full_src}]")
        return val, full_src

    print("   ⚠️  [SST FB3] OISST NRT failed — NOAA OISST v2.1 full archive 0.25°...")
    val, src = _fetch_sst_erddap([_OISST_ARC], lat, lon, pad=0.3, max_days=15)
    if val is not None:
        full_src = f"NOAA OISST v2.1 archive 0.25° | {src}"
        print(f"   ✅ [SST FB3] {val:.2f} °C  [{full_src}]")
        return val, full_src

    print("   ⚠️  [SST FB4] OISST archive failed — AVHRR Pathfinder SST 0.04°...")
    val, src = _fetch_sst_erddap([_AVHRR_SST], lat, lon, pad=0.1, max_days=15)
    if val is not None:
        full_src = f"AVHRR Pathfinder SST 0.04° (PFEG) | {src}"
        print(f"   ✅ [SST FB4] {val:.2f} °C  [{full_src}]")
        return val, full_src

    print("   ⚠️  [SST FB5] AVHRR failed — NOAA CoralTemp NRT 0.05° (OceanWatch)...")
    val, src = _fetch_sst_erddap([_CORALTEMP_SST], lat, lon, pad=0.15, max_days=15)
    if val is not None:
        full_src = f"NOAA CoralTemp NRT 0.05° (OceanWatch) | {src}"
        print(f"   ✅ [SST FB5] {val:.2f} °C  [{full_src}]")
        return val, full_src

    print("   ⚠️  [SST FB6] All ERDDAP sources failed — Copernicus Marine NRT physics model (thetao)...")
    _cmems_user = os.getenv("COPERNICUS_USERNAME")
    _cmems_pass = os.getenv("COPERNICUS_PASSWORD")
    if _cmems_user and _cmems_pass:
        val, src = _cmems_fetch_scalar(
            "cmems_mod_glo_phy-thetao_anfc_0.083deg_P1D-m", "thetao",
            lat, lon, "sst_cmems", _cmems_user, _cmems_pass, pad=0.2,
        )
        if val is not None:
            full_src = f"Copernicus Marine NRT cmems_mod_glo_phy_anfc thetao | {src.split('|')[-1].strip()}"
            print(f"   ✅ [SST FB6] {val:.2f} °C  [{full_src}]")
            return val, full_src
    if hint is not None:
        print(f"   ⚠️  [SST] Copernicus unavailable — Open-Meteo hint {hint:.1f} °C")
        return hint, f"Open-Meteo SST hint {hint:.1f} °C"
    print("   ❌ [SST] All sources failed — no SST data available")
    return None, "No SST data available (all ERDDAP + Copernicus sources failed)"


# ---------------------------------------------------------------------------
# SSH: Copernicus Marine NRT (zos)  →  AVISO CMEMS DUACS NRT (adt)
#    →  Copernicus L3 NRT along-track (sla_filtered)  →  PFEG ERDDAP AVISO
# ---------------------------------------------------------------------------

def _fetch_ssh_erddap_aviso(
    lat: float, lon: float,
) -> Tuple[Optional[float], str]:
    """
    ERDDAP-served AVISO along-track SSH — no Copernicus credentials needed.
    Tries several PFEG/CoastWatch ERDDAP datasets that hold SSH / sea-level anomaly.
    """
    sla_datasets = [
        # PFEG ERDDAP: AVISO NRT along-track sea-level anomaly
        ("erdTAgeo1day",         _PFEG,        "sla",    False, "12:00:00"),
        ("erdTAgeo8day",         _PFEG,        "sla",    False, "12:00:00"),
        # OceanWatch: SSH / SLA blended products
        ("hawaii_soest_d749_a206_cd7a", _OCEANWATCH, "sea_level_anomaly", False, "12:00:00"),
    ]
    today = date.today()
    for days_back in range(1, 10):
        d = (today - timedelta(days=days_back)).isoformat()
        for ds_id, base, var, has_alt, t_of_day in sla_datasets:
            rows = _erddap_fetch(
                base, ds_id, var, d,
                lat - 1.5, lat + 1.5, lon - 1.5, lon + 1.5,
                has_alt=has_alt, time_of_day=t_of_day,
            )
            if rows is None:
                continue
            val = _mean_valid(rows, var)
            if val is not None:
                return val, f"{ds_id} | {d}"
    return None, "no data"

def _cmems_fetch_scalar(
    dataset_id: str,
    variable: str,
    lat: float,
    lon: float,
    label: str,
    username: str,
    password: str,
    pad: float = 0.1,
    max_days_back: int = 10,
) -> Tuple[Optional[float], str]:
    """
    Generic Copernicus Marine subset → scalar mean for a single 2-D surface variable.
    Tries multiple days back (1 → 3 → 7 → 10) to handle datasets with varying latency:
      - SSH L4 / CHLO L4:  ~1-2 day lag
      - MULTIOBS SSS:       ~7-8 day lag
    """
    try:
        import tempfile, copernicusmarine  # type: ignore
        import xarray as xr  # type: ignore
        for days_back in [1, 3, 7, 10]:
            if days_back > max_days_back:
                break
            nrt_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    out = f"{tmp}/{label}_{days_back}.nc"
                    copernicusmarine.subset(
                        dataset_id=dataset_id,
                        variables=[variable],
                        minimum_latitude=lat - pad,
                        maximum_latitude=lat + pad,
                        minimum_longitude=lon - pad,
                        maximum_longitude=lon + pad,
                        start_datetime=f"{nrt_date}T00:00:00",
                        end_datetime=f"{nrt_date}T23:59:59",
                        output_filename=out,
                        username=username,
                        password=password,
                    )
                    with xr.open_dataset(out) as ds:
                        vkey = variable if variable in ds else list(ds.data_vars.keys())[0]
                        var_data = ds[vkey]
                        if "depth" in var_data.dims:
                            var_data = var_data.isel(depth=0)
                        vals = var_data.values.flatten()
                        vals = vals[~(vals != vals)]  # drop NaN
                        if len(vals) == 0:
                            continue  # try older date
                        return float(vals.mean()), f"{dataset_id} {variable} | {nrt_date}"
            except Exception as inner_e:
                err = str(inner_e)
                # Date out-of-range → retry with older date
                if "exceed" in err.lower() or "time" in err.lower():
                    continue
                return None, err[:100]  # real error, stop retrying
    except Exception as e:
        return None, str(e)[:100]
    return None, f"{dataset_id} {variable} — no data in last {max_days_back} days"


def _fetch_ssh(lat: float, lon: float) -> Tuple[Optional[float], str]:
    """
    SSH (sea surface height, metres).

      1. PRIMARY   — Copernicus Marine NRT: SEALEVEL_GLO_PHY_L4_NRT_008_046  (adt, 0.25°/daily)
      2. FALLBACK1 — Copernicus Marine NRT ocean physics (zos, 0.083°)
                     cmems_mod_glo_phy_anfc_0.083deg_P1D-m
      3. FALLBACK2 — Copernicus DUACS L3 NRT along-track (~5 km, 1 Hz)
                     Sentinel-6 / Jason-3 / SWOT nadir, sla_filtered
      4. FALLBACK3 — ERDDAP-served AVISO SLA products (no credentials)
                     PFEG / OceanWatch  (erdTAgeo1day, hawaii_soest_* etc.)
    """
    try:
        import copernicusmarine  # type: ignore
    except ImportError:
        print("   ⚠️  [SSH] copernicusmarine not installed — trying ERDDAP fallback")
        val, src = _fetch_ssh_erddap_aviso(lat, lon)
        if val is not None:
            return val, f"ERDDAP AVISO SLA (PFEG/OceanWatch) | {src}"
        return None, "copernicusmarine not installed; ERDDAP fallback also failed"

    username = os.getenv("COPERNICUS_USERNAME")
    password = os.getenv("COPERNICUS_PASSWORD")
    if not username or not password:
        print("   ⚠️  [SSH] credentials not set — trying ERDDAP fallback")
        val, src = _fetch_ssh_erddap_aviso(lat, lon)
        if val is not None:
            return val, f"ERDDAP AVISO SLA (no credentials needed) | {src}"
        return None, "credentials not set; ERDDAP fallback also failed"

    nrt_date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")

    # --- PRIMARY: SEALEVEL_GLO_PHY_L4_NRT_008_046 (adt, 0.25°) ---------------
    print(f"   🔵 [SSH] PRIMARY: Copernicus SEALEVEL_GLO_PHY_L4_NRT_008_046 adt ({nrt_date})...")
    val, src = _cmems_fetch_scalar(
        _CMEMS_SSH_L4_DS, "adt",
        lat, lon, "ssh_adt", username, password, pad=0.25,
    )
    if val is not None:
        full_src = f"Copernicus SEALEVEL_GLO_PHY_L4_NRT_008_046 adt 0.25° | {src.split('|')[-1].strip()}"
        print(f"   ✅ [SSH PRIMARY] {val:.4f} m  [{full_src}]")
        return val, full_src
    print(f"   ⚠️  [SSH FB1] SEALEVEL L4 adt failed: {src}")

    # --- FALLBACK1: Copernicus NRT ocean physics (zos, 0.083°) ---------------
    print(f"   🔵 [SSH FB1] Copernicus Marine NRT zos 0.083° ({nrt_date})...")
    val, src = _cmems_fetch_scalar(
        "cmems_mod_glo_phy_anfc_0.083deg_P1D-m", "zos",
        lat, lon, "ssh_zos", username, password, pad=0.1,
    )
    if val is not None:
        full_src = f"Copernicus Marine NRT cmems_mod_glo_phy_anfc zos 0.083° | {src.split('|')[-1].strip()}"
        print(f"   ✅ [SSH FB1] {val:.4f} m  [{full_src}]")
        return val, full_src
    print(f"   ⚠️  [SSH FB2] Copernicus zos failed: {src}")

    # --- FALLBACK2: Copernicus DUACS L3 NRT along-track (~5 km, 1 Hz) --------
    print(f"   🔵 [SSH FB2] Copernicus DUACS L3 along-track sla_filtered (~5 km, 1 Hz)...")
    _l3_ids = [
        "cmems_obs-sl_glo_phy-ssh_nrt_al-l3-duacs_PT1S",      # Jason-3 / Sentinel-6 1 Hz
        "cmems_obs-sl_glo_phy-ssh_nrt_s6a-lr-l3-duacs_PT1S",  # Sentinel-6A low-rate 1 Hz
        "cmems_obs-sl_glo_phy-ssh_nrt_swon-l3-duacs_PT1S",    # SWOT nadir-track 1 Hz
    ]
    for l3id in _l3_ids:
        val, src = _cmems_fetch_scalar(
            l3id, "sla_filtered",
            lat, lon, "ssh_l3", username, password, pad=0.5,
        )
        if val is not None:
            full_src = f"Copernicus DUACS L3 along-track sla_filtered | {l3id} | {src.split('|')[-1].strip()}"
            print(f"   ✅ [SSH FB2] {val:.4f} m  [{full_src}]")
            return val, full_src
    print(f"   ⚠️  [SSH FB3] All Copernicus L3 along-track attempts failed")

    # --- FALLBACK3: ERDDAP-served AVISO SLA (no credentials needed) ----------
    print(f"   🔵 [SSH FB3] ERDDAP-served AVISO SLA (PFEG / OceanWatch, no credentials)...")
    val, src = _fetch_ssh_erddap_aviso(lat, lon)
    if val is not None:
        full_src = f"ERDDAP AVISO SLA (PFEG/OceanWatch) | {src}"
        print(f"   ✅ [SSH FB3] {val:.4f} m  [{full_src}]")
        return val, full_src

    print(f"   ❌ [SSH] All sources failed — SSH unavailable for ({lat:.3f}, {lon:.3f})")
    return None, "SSH unavailable (Copernicus NRT + DUACS L4/L3 + ERDDAP all failed)"


# ---------------------------------------------------------------------------
# SSD: Copernicus Marine NRT  →  gsw/linear from SSS+SST
# ---------------------------------------------------------------------------

def _density_from_sss_sst(sss: float, sst: float, lat: float, lon: float) -> float:
    """Compute density (kg/m³) via TEOS-10 gsw or simplified linear formula."""
    try:
        import gsw  # type: ignore
        p = 0.0
        SA = gsw.SA_from_SP(sss, p, lon, lat)
        CT = gsw.CT_from_t(SA, sst, p)
        return float(gsw.rho(SA, CT, p))
    except Exception:
        return 1025.0 + 0.8 * (sss - 35.0) - 0.2 * (sst - 25.0)


def _fetch_ssd_copernicus(lat: float, lon: float, sst: float) -> Tuple[Optional[float], Optional[str]]:
    """
    PRIMARY SSD source: Copernicus MULTIOBS NRT SSS → TEOS-10 density.
      1. PRIMARY  — cmems_obs-mob_glo_phy-sss_nrt_multi_P1D  (NRT, ~7-day lag)
      2. FALLBACK — cmems_obs-mob_glo_phy-sss_my_multi_P1D   (MyOcean archive, deeper history)
    Both have variable 'sos' (sea surface salinity, PSU).
    """
    username = os.getenv("COPERNICUS_USERNAME") or os.getenv("CMEMS_USERNAME", "")
    password = os.getenv("COPERNICUS_PASSWORD") or os.getenv("CMEMS_PASSWORD", "")
    if not username or not password:
        print("   ⚠️  [SSD] COPERNICUS_USERNAME/PASSWORD not set")
        return None, None
    try:
        import copernicusmarine  # type: ignore
    except ImportError:
        print("   ⚠️  [SSD] copernicusmarine not installed")
        return None, None

    # --- PRIMARY: MULTIOBS NRT (lags ~7 days) ---------------------------------
    print(f"   🔵 [SSD PRIMARY] Copernicus MULTIOBS NRT SSS ({_CMEMS_MULTIOBS_SSD_DS})...")
    sos_val, sos_src = _cmems_fetch_scalar(
        _CMEMS_MULTIOBS_SSD_DS, "sos",
        lat, lon, "ssd_sos_nrt", username, password, pad=0.3, max_days_back=14,
    )
    if sos_val is not None:
        rho = _density_from_sss_sst(sos_val, sst, lat, lon)
        src = f"Copernicus MULTIOBS NRT SSS→density | {sos_src.split('|')[-1].strip()}"
        print(f"   ✅ [SSD PRIMARY] sos={sos_val:.3f} PSU → ρ={rho:.4f} kg/m³")
        return rho, src
    print(f"   ⚠️  [SSD FB1] NRT failed: {sos_src[:80]}")

    # --- FALLBACK: MULTIOBS MyOcean archive (longer record) ------------------
    print(f"   🔵 [SSD FB1] Copernicus MULTIOBS MyOcean archive ({_CMEMS_MULTIOBS_MY_DS})...")
    sos_val, sos_src = _cmems_fetch_scalar(
        _CMEMS_MULTIOBS_MY_DS, "sos",
        lat, lon, "ssd_sos_my", username, password, pad=0.3, max_days_back=30,
    )
    if sos_val is not None:
        rho = _density_from_sss_sst(sos_val, sst, lat, lon)
        src = f"Copernicus MULTIOBS MyOcean SSS→density | {sos_src.split('|')[-1].strip()}"
        print(f"   ✅ [SSD FB1] sos={sos_val:.3f} PSU → ρ={rho:.4f} kg/m³")
        return rho, src
    print(f"   ⚠️  [SSD FB1] Archive also failed: {sos_src[:80]}")
    return None, None


def _fetch_ssd(lat: float, lon: float, sss: Optional[float], sst: float) -> Tuple[float, str]:
    """
    Compute SSD (sea surface density, kg/m³).

      1. PRIMARY   — Copernicus MULTIOBS_GLO_PHY_S_SURFACE_MYNRT_015_013 (sos → TEOS-10 density)
      2. FALLBACK  — Copernicus Marine NRT cmems_mod_glo_phy_anfc sos → TEOS-10 density
      3. LAST RESORT — TEOS-10 gsw from locally-fetched SSS + SST (no HTTP)
    """
    # ---------- PRIMARY / FB: Copernicus live sos → density ----------
    rho_cmems, src_cmems = _fetch_ssd_copernicus(lat, lon, sst if sst is not None else 28.0)
    if rho_cmems is not None and src_cmems is not None:
        print(f"   ✅ [SSD] {rho_cmems:.4f} kg/m³  [{src_cmems}]")
        return rho_cmems, src_cmems

    # ---------- LAST RESORT: TEOS-10 from already-fetched SSS + SST ----------
    eff_sss = sss if sss is not None else 34.5
    note    = "TEOS-10 gsw from SMAP/SMOS SSS + SST" if sss is not None else "TEOS-10 gsw from default 34.5 PSU + SST"
    rho = _density_from_sss_sst(eff_sss, sst if sst is not None else 28.0, lat, lon)
    src = f"TEOS-10 gsw: {note}"
    print(f"   ✅ [SSD] {rho:.4f} kg/m³  [{src}]")
    return rho, src


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class FreeOceanDataService:
    """
    Fetches real-time CHLO, SSS, SSD, Depth, SSH and SST for ML model predictions.

    Source map:
      NOAA CoastWatch ERDDAP  →  SST, SSS, Chlorophyll-a
      Copernicus Marine API   →  SSH, SSD

      SST   : 1) NOAA CoastWatch BLENDED SST NRT (noaacwBLENDEDsstDaily)  ← PRIMARY
              2) NASA/JPL MUR NRT 0.01° (jplMURSST41 @ PFEG)              ← GHRSST L4
              3) NOAA OISST v2.1 NRT 0.25° (ncdcOisst21NrtAgg @ PFEG)
              4) NOAA OISST v2.1 full archive 0.25° (ncdcOisst21Agg @ PFEG)
              5) AVHRR Pathfinder SST 0.04° (erdATssta1day @ PFEG)
              6) NOAA CoralTemp NRT 0.05° (NOAA_DHW @ OceanWatch)
              7) Copernicus Marine NRT thetao (cmems_mod_glo_phy_anfc_0.083deg_P1D-m)
              8) Open-Meteo hint (if available) — last resort
      SSS   : 1) NOAA CoastWatch SMAP NRT daily (noaacwSMAPsssDaily)  ← PRIMARY
              2) NOAA CoastWatch SMOS 3-day / daily
              3) OceanWatch RSS SMOS L3 8-day / 2-day blended
              4) SMOS wide-tier retry (28 days, ±10°)
              5) Copernicus Marine NRT physics model sos (cmems_mod_glo_phy_anfc)
      CHLO  : 1) NOAA CoastWatch VIIRS-SNPP NRT (noaacwNPPVIIRSchlaDaily)  ← PRIMARY
              2) NASA Ocean Color MODIS-Aqua / ESA OC-CCI (PFEG ERDDAP)
              3) PFEG NRT gapfilled VIIRS + NOAA-20
              4) PACE/OCI NRT + MODIS monthly composite
              5) NASA OB.DAAC Sentinel-3 OLCI 300 m (OceanWatch)
              6) Copernicus Marine OC NRT gap-free L4/L3
              7) Copernicus gap-free L4 wide bbox 2° (last resort, no orbital gaps)
      SSH   : 1) Copernicus SEALEVEL_GLO_PHY_L4_NRT_008_046 adt 0.25°  ← PRIMARY
              2) Copernicus Marine NRT zos 0.083° (cmems_mod_glo_phy_anfc)
              3) Copernicus DUACS L3 along-track sla_filtered (~5 km, 1 Hz)
              4) ERDDAP-served AVISO SLA (PFEG/OceanWatch, no credentials needed)
      SSD   : 1) Copernicus MULTIOBS_GLO_PHY_S_SURFACE_MYNRT_015_013 sos → TEOS-10  ← PRIMARY
              2) Copernicus Marine NRT cmems_mod_glo_phy_anfc sos → TEOS-10 density
              3) TEOS-10 gsw from locally-fetched SSS + SST (no HTTP)
      Depth : GEBCO 2025 sub-ice NetCDF  (local file, per-point)
    """

    def get_ocean_vars(
        self,
        lats: List[float],
        lons: List[float],
        sst_values: Optional[List[Optional[float]]] = None,
    ) -> List[Dict]:
        """
        Fetch CHLO / SSS / SSD for a list of (lat, lon) points — all per-point.

        Strategy:
          CHLO  — per-point bbox (VIIRS-SNPP primary), falls back through NASA OC, PFEG ERDDAP,
                  PACE/OCI, NASA OLCI, Copernicus OC L4, Copernicus wide-bbox last-resort.
          SSS   — per-point bbox (SMAP primary), falls back through SMOS ERDDAP, RSS SMOS,
                  SMOS wide-tier, Copernicus model last-resort.
          SSD   — Copernicus MULTIOBS sos +TEOS-10 density; falls back to TEOS-10 from SSS+SST.
          SST/SSH/Depth — fetched by caller (Open-Meteo + GEBCO), passed in via sst_values.

        CHLO and SSS bbox fetches run concurrently via ThreadPoolExecutor.
        """
        if not lats:
            return []

        n = len(lats)

        # Build per-point SST list (fed in from Open-Meteo results in caller)
        if sst_values is None:
            sst_values = [28.0] * n
        sst_per_point = [(v if v is not None else 28.0) for v in sst_values]
        while len(sst_per_point) < n:
            sst_per_point.append(28.0)

        centre_lat = (min(lats) + max(lats)) / 2.0
        centre_lon = (min(lons) + max(lons)) / 2.0

        # ── CHLO per-point (parallel fetch over bbox covering all points) ──────
        def _fetch_chlo_pp():
            print("   [CHLO] Trying per-point bbox (VIIRS primary | NOAA-20 | VIIRS-SNPP)...")
            vals, src = _try_datasets_per_point(
                "chlo_pp_primary", _CHLO_PRIMARY, lats, lons, _CHLO_TIERS)
            if vals is not None:
                print(f"   [CHLO] Per-point VIIRS OK: {[round(v,4) for v in vals[:3]]}...")
                return vals, f"NOAA CoastWatch NRT VIIRS | {src}"

            print("   [CHLO FB1] Fallback: NASA Ocean Color (MODIS-Aqua / ESA OC-CCI) per-point...")
            vals, src = _try_datasets_per_point(
                "chlo_pp_fb1", _CHLO_FALLBACK, lats, lons, [(7, 1.5), (14, 3.0)])
            if vals is not None:
                print(f"   [CHLO FB1] Per-point NASA OK: {[round(v,4) for v in vals[:3]]}...")
                return vals, f"NASA Ocean Color / ESA OC-CCI | {src}"

            print("   [CHLO FB2] Fallback: PFEG ERDDAP VIIRS/MODIS Aqua/Terra per-point...")
            vals, src = _try_datasets_per_point(
                "chlo_pp_fb2", _CHLO_FALLBACK2, lats, lons, [(7, 1.5), (14, 3.0)])
            if vals is not None:
                print(f"   [CHLO FB2] Per-point PFEG OK: {[round(v,4) for v in vals[:3]]}...")
                return vals, f"PFEG ERDDAP VIIRS/MODIS | {src}"

            print("   [CHLO FB3] Fallback: PACE/OCI + MODIS monthly per-point (wide tiers)...")
            vals, src = _try_datasets_per_point(
                "chlo_pp_fb3", _CHLO_FALLBACK3, lats, lons, [(14, 3.0), (21, 5.0)])
            if vals is not None:
                print(f"   [CHLO FB3] Per-point PACE OK: {[round(v,4) for v in vals[:3]]}...")
                return vals, f"PACE/OCI or MODIS monthly | {src}"

            print("   [CHLO FB4] Fallback: NASA OB.DAAC Sentinel-3 OLCI 300 m per-point...")
            vals, src = _try_datasets_per_point(
                "chlo_pp_fb4", _CHLO_NASA_OBDAAC, lats, lons, [(7, 1.5), (15, 3.0)])
            if vals is not None:
                print(f"   [CHLO FB4] Per-point NASA OLCI OK: {[round(v,4) for v in vals[:3]]}...")
                return vals, f"NASA OB.DAAC Sentinel-3 OLCI 300m | {src}"

            print("   [CHLO FB5] Fallback: Copernicus Marine OC NRT gap-free L4 (per 0.25\u00b0 cell)...")
            _cmems_u = os.environ.get("CMEMS_USERNAME", "") or os.environ.get("COPERNICUS_USERNAME", "")
            _cmems_p = os.environ.get("CMEMS_PASSWORD", "") or os.environ.get("COPERNICUS_PASSWORD", "")
            if _cmems_u and _cmems_p:
                def _chlo_cell_key(la, lo, res=0.25):
                    return (round(la / res) * res, round(lo / res) * res)
                unique_chlo_cells = {}
                for la, lo in zip(lats, lons):
                    k = _chlo_cell_key(la, lo)
                    unique_chlo_cells[k] = (k[0], k[1])
                def _fetch_chlo_cell(cell_lat, cell_lon):
                    for prod_id in (_CHLO_CMEMS_L4, _CHLO_CMEMS_L3):
                        v, s = _cmems_fetch_scalar(
                            prod_id, "CHL", cell_lat, cell_lon,
                            "chlo_cmems_pp", _cmems_u, _cmems_p, pad=0.25)
                        if v is not None:
                            return v, s
                    return None, None
                with ThreadPoolExecutor(max_workers=min(len(unique_chlo_cells), 5)) as _ex:
                    _futs = {k: _ex.submit(_fetch_chlo_cell, clat, clon)
                             for k, (clat, clon) in unique_chlo_cells.items()}
                    chlo_by_cell = {}
                    for k, fut in _futs.items():
                        v, s = fut.result()
                        if v is not None:
                            chlo_by_cell[k] = v
                if chlo_by_cell:
                    def _nearest_chlo(la, lo):
                        k = _chlo_cell_key(la, lo)
                        if k in chlo_by_cell:
                            return chlo_by_cell[k]
                        best = min(chlo_by_cell.keys(), key=lambda c: (c[0]-la)**2+(c[1]-lo)**2)
                        return chlo_by_cell[best]
                    chlo_pp_vals = [_nearest_chlo(la, lo) for la, lo in zip(lats, lons)]
                    src_tag = "Copernicus Marine OC L4 (per-cell)"
                    print(f"   [CHLO FB5] per-cell: {[round(v,4) for v in chlo_pp_vals[:5]]}")
                    return chlo_pp_vals, src_tag

            print("   [CHLO FB6] Fallback: PFEG wide-tier retry (28 days, \u00b17\u00b0) per-point...")
            vals, src = _try_datasets_per_point(
                "chlo_pp_fb6", _CHLO_FALLBACK2, lats, lons, _CHLO_TIERS_WIDE)
            if vals is not None:
                print(f"   [CHLO FB6] Per-point PFEG wide OK: {[round(v,4) for v in vals[:3]]}...")
                return vals, f"PFEG ERDDAP VIIRS/MODIS wide-tile | {src}"

            # Last resort: Copernicus gap-free L4 per unique 0.25\u00b0 cell
            print("   [CHLO] All ERDDAP sources failed \u2014 Copernicus gap-free L4 (per 0.25\u00b0 cell)...")
            _cmems_u2 = os.environ.get("CMEMS_USERNAME", "") or os.environ.get("COPERNICUS_USERNAME", "")
            _cmems_p2 = os.environ.get("CMEMS_PASSWORD", "") or os.environ.get("COPERNICUS_PASSWORD", "")
            if _cmems_u2 and _cmems_p2:
                def _chlo_cell_key2(la, lo, res=0.25):
                    return (round(la/res)*res, round(lo/res)*res)
                unique_cells2 = {}
                for la, lo in zip(lats, lons):
                    k = _chlo_cell_key2(la, lo)
                    unique_cells2[k] = (k[0], k[1])
                def _fetch_wide_cell(cell_lat, cell_lon):
                    v, s = _fetch_chlo_cmems_wider(cell_lat, cell_lon)
                    return v, s
                chlo_wide_by_cell = {}
                wide_src = ""
                with ThreadPoolExecutor(max_workers=min(len(unique_cells2), 5)) as _ex2:
                    _futs2 = {k: _ex2.submit(_fetch_wide_cell, clat, clon)
                              for k, (clat, clon) in unique_cells2.items()}
                    for k, fut in _futs2.items():
                        v, s = fut.result()
                        if v is not None:
                            chlo_wide_by_cell[k] = v
                            wide_src = f"Copernicus OC gap-free L4 (wide, per-cell)"
                if chlo_wide_by_cell:
                    def _nn_chlo_wide(la, lo):
                        k = _chlo_cell_key2(la, lo)
                        if k in chlo_wide_by_cell:
                            return chlo_wide_by_cell[k]
                        best = min(chlo_wide_by_cell.keys(), key=lambda c: (c[0]-la)**2+(c[1]-lo)**2)
                        return chlo_wide_by_cell[best]
                    chlo_wide_vals = [_nn_chlo_wide(la, lo) for la, lo in zip(lats, lons)]
                    print(f"   [CHLO] gap-free wide per-cell: {[round(v,4) for v in chlo_wide_vals[:5]]}")
                    return chlo_wide_vals, wide_src
            print("   [CHLO] All sources failed \u2014 no CHLO data available")
            return [None] * n, "No CHLO data available (all satellite + Copernicus sources failed)"

        # ── SSS per-point (parallel fetch over bbox covering all points) ──────
        def _fetch_sss_pp():
            print("   [SSS] Trying per-point bbox (SMAP primary)...")
            vals, src = _try_datasets_per_point(
                "sss_pp_primary", _SSS_PRIMARY, lats, lons, _SSS_TIERS)
            if vals is not None:
                print(f"   [SSS] Per-point SMAP OK: {[round(v,3) for v in vals[:3]]}...")
                return vals, f"NOAA CoastWatch SMAP NRT | {src}"

            print("   [SSS FB1] Fallback: SMOS per-point bbox...")
            vals, src = _try_datasets_per_point(
                "sss_pp_fb1", _SSS_FALLBACK, lats, lons, _SSS_TIERS)
            if vals is not None:
                print(f"   [SSS FB1] Per-point SMOS OK: {[round(v,3) for v in vals[:3]]}...")
                return vals, f"NOAA CoastWatch SMOS | {src}"

            print("   [SSS FB2] Fallback: OceanWatch RSS SMOS L3 blended per-point...")
            vals, src = _try_datasets_per_point(
                "sss_pp_fb2", _SSS_FALLBACK2, lats, lons, [(14, 4.0), (21, 6.0)])
            if vals is not None:
                print(f"   [SSS FB2] Per-point RSS SMOS OK: {[round(v,3) for v in vals[:3]]}...")
                return vals, f"RSS SMOS L3 blended (OceanWatch) | {src}"

            print("   [SSS FB3] Fallback: SMOS 3-day wide-tier retry per-point...")
            vals, src = _try_datasets_per_point(
                "sss_pp_fb3", _SSS_FALLBACK3, lats, lons, [(14, 5.0), (21, 8.0)])
            if vals is not None:
                print(f"   [SSS FB3] Per-point SMOS wide OK: {[round(v,3) for v in vals[:3]]}...")
                return vals, f"NOAA CoastWatch SMOS wide | {src}"

            print("   [SSS FB4] Fallback: SMOS wide-tier retry (28 days, \u00b110\u00b0) per-point...")
            vals, src = _try_datasets_per_point(
                "sss_pp_fb4", _SSS_FALLBACK, lats, lons, _SSS_TIERS_WIDE)
            if vals is not None:
                print(f"   [SSS FB4] Per-point SMOS wide OK: {[round(v,3) for v in vals[:3]]}...")
                return vals, f"NOAA CoastWatch SMOS wide-tile | {src}"

            # Last resort: Copernicus Marine NRT physics model (sos) — per unique 0.25\u00b0 cell
            print("   [SSS] All satellite sources failed \u2014 Copernicus Marine NRT sos (per 0.25\u00b0 cell)...")
            _cmems_uu = os.environ.get("CMEMS_USERNAME", "") or os.environ.get("COPERNICUS_USERNAME", "")
            _cmems_pp = os.environ.get("CMEMS_PASSWORD", "") or os.environ.get("COPERNICUS_PASSWORD", "")
            sss_cmems_src = ""
            if _cmems_uu and _cmems_pp:
                def _sss_cell_key(la, lo, res=0.25):
                    return (round(la/res)*res, round(lo/res)*res)
                unique_sss_cells = {}
                for la, lo in zip(lats, lons):
                    k = _sss_cell_key(la, lo)
                    unique_sss_cells[k] = (k[0], k[1])
                def _fetch_sss_cell(cell_lat, cell_lon):
                    v, s = _cmems_fetch_scalar(
                        _CMEMS_MULTIOBS_SSD_DS, "sos",
                        cell_lat, cell_lon, "sss_multiobs_pp",
                        _cmems_uu, _cmems_pp, pad=0.5, max_days_back=14)
                    if v is not None:
                        return v, s
                    v, s = _cmems_fetch_scalar(
                        _CMEMS_MULTIOBS_MY_DS, "sos",
                        cell_lat, cell_lon, "sss_multiobs_pp_my",
                        _cmems_uu, _cmems_pp, pad=0.5, max_days_back=30)
                    return v, s
                sss_by_cell = {}
                with ThreadPoolExecutor(max_workers=min(len(unique_sss_cells), 5)) as _ex3:
                    _futs3 = {k: _ex3.submit(_fetch_sss_cell, clat, clon)
                              for k, (clat, clon) in unique_sss_cells.items()}
                    for k, fut in _futs3.items():
                        v, s = fut.result()
                        if v is not None:
                            sss_by_cell[k] = v
                            sss_cmems_src = f"Copernicus MULTIOBS NRT SSS sos (per-cell)"
                if sss_by_cell:
                    def _nearest_sss(la, lo):
                        k = _sss_cell_key(la, lo)
                        if k in sss_by_cell:
                            return sss_by_cell[k]
                        best = min(sss_by_cell.keys(), key=lambda c: (c[0]-la)**2+(c[1]-lo)**2)
                        return sss_by_cell[best]
                    sss_pp_vals = [_nearest_sss(la, lo) for la, lo in zip(lats, lons)]
                    print(f"   [SSS] per-cell: {[round(v,3) for v in sss_pp_vals[:5]]}")
                    return sss_pp_vals, sss_cmems_src
            print("   [SSS] All sources failed \u2014 no SSS data available")
            return [None] * n, "No SSS data available (all satellite + Copernicus sources failed)"

        # ── Run CHLO and SSS concurrently ─────────────────────────────────────
        print("\n[CHLO+SSS] Fetching per-point in parallel...")
        with ThreadPoolExecutor(max_workers=2) as ex:
            chlo_fut = ex.submit(_fetch_chlo_pp)
            sss_fut  = ex.submit(_fetch_sss_pp)
            chlo_list, chlo_src = chlo_fut.result()
            sss_list,  sss_src  = sss_fut.result()

        chlo_valid = [v for v in chlo_list if v is not None]
        sss_valid  = [v for v in sss_list  if v is not None]
        if chlo_valid:
            print(f"   CHLO range: {min(chlo_valid):.4f} – {max(chlo_valid):.4f} mg/m3 ({len(chlo_valid)}/{n} points valid)")
        else:
            print("   CHLO: no valid data for any point")
        if sss_valid:
            print(f"   SSS  range: {min(sss_valid):.3f} – {max(sss_valid):.3f} PSU ({len(sss_valid)}/{n} points valid)")
        else:
            print("   SSS: no valid data for any point")

        # ── SSD per-point using each point's own SSS + SST (TEOS-10, no HTTP) ──
        results = []
        for i, (lat, lon) in enumerate(zip(lats, lons)):
            sss_pt = sss_list[i]
            sst_pt = sst_per_point[i]
            ssd_val, ssd_src = _fetch_ssd(lat, lon, sss_pt, sst_pt)

            # ── Climatology last resort when ALL NRT sources returned None ──
            chlo_val = chlo_list[i]
            chlo_src_pt = chlo_src
            if chlo_val is None:
                chlo_val = _chlo_climatology(lat, lon)
                chlo_src_pt = f"WOA/SeaWiFS climatology ({round(lat,1)}\u00b0N {round(lon,1)}\u00b0E)"

            sss_val = sss_pt
            sss_src_pt = sss_src
            if sss_val is None:
                sss_val = _sss_climatology(lat, lon)
                sss_src_pt = f"WOA-2018 climatology ({round(lat,1)}\u00b0N / {round(lon,1)}\u00b0E)"

            results.append({
                "chlo":        chlo_val,
                "sss":         sss_val,
                "ssd":         ssd_val,
                "chlo_source": chlo_src_pt,
                "sss_source":  sss_src_pt,
                "ssd_source":  ssd_src,
            })

        return results

    def get_ocean_vars_point(
        self,
        lat: float,
        lon: float,
        sst: Optional[float] = None,
    ) -> Dict:
        """Single-point convenience wrapper."""
        res = self.get_ocean_vars([lat], [lon], [sst])
        return res[0] if res else {}


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_instance: Optional[FreeOceanDataService] = None


def get_service() -> FreeOceanDataService:
    global _instance
    if _instance is None:
        _instance = FreeOceanDataService()
    return _instance


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    # Load .env so credentials are available when running the script directly
    _env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    _env_path = os.path.normpath(_env_path)
    if os.path.exists(_env_path):
        with open(_env_path) as _ef:
            for _line in _ef:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _, _v = _line.partition("=")
                    os.environ.setdefault(_k.strip(), _v.strip())
        print(f"  Loaded env from {_env_path}")

    # Default to open ocean east of Sri Lanka (Bay of Bengal, 7.5°N 82.0°E)
    LAT = float(sys.argv[1]) if len(sys.argv) > 1 else 7.5
    LON = float(sys.argv[2]) if len(sys.argv) > 2 else 82.0
    SST = float(sys.argv[3]) if len(sys.argv) > 3 else 28.5

    print(f"\n{'='*60}")
    print(f"  FreeOceanDataService self-test")
    print(f"  Location : LAT={LAT}  LON={LON}  SST_hint={SST} °C")
    print(f"{'='*60}\n")

    svc = FreeOceanDataService()
    result = svc.get_ocean_vars_point(lat=LAT, lon=LON, sst=SST)

    print("\n" + "="*60)
    print("  FINAL VALUES")
    print("="*60)
    fields = [
        ("CHLO",  "chlo",  "mg/m³",  "chlo_source"),
        ("SSS",   "sss",   "PSU",    "sss_source"),
        ("SSD",   "ssd",   "kg/m³",  "ssd_source"),
        ("Depth", "depth", "m",      "depth_source"),
        ("SSH",   "ssh",   "m",      "ssh_source"),
        ("SST",   "sst",   "°C",     "sst_source"),
    ]
    for label, key, unit, src_key in fields:
        val = result.get(key)
        src = result.get(src_key, "")
        val_str = f"{val:.4f}" if isinstance(val, float) else str(val)
        print(f"  {label:<6} : {val_str:>10} {unit:<6}  |  {src}")
    print("="*60)
