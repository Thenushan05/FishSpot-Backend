"""Prediction service: loads model pipeline and produces GeoJSON hotspots.

Change `MODEL_PATH` below to point to your `.joblib` file if different.
"""
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import joblib
import pandas as pd
import json

from app.services.env_loader import load_env_grid
from app.services import depth_service
try:
    import gsw
    _HAS_GSW = True
except Exception:
    _HAS_GSW = False

# Default model path - change if your model is elsewhere
MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "fish_hotspot_xgb_species.joblib"


def _load_pipeline():
    if MODEL_PATH.exists():
        pipeline = joblib.load(MODEL_PATH)
    else:
        # Fallback: try to find any installed pipeline in app.ml
        try:
            from app.services import ml_hotspot

            # ml_hotspot uses a raw joblib model expecting numpy features;
            # wrap into a tiny adapter object that implements predict_proba
            class _Wrapper:
                def predict_proba(self, X):
                    # ml_hotspot expects list of dict features; try to invert
                    if isinstance(X, pd.DataFrame):
                        records = X.to_dict(orient="records")
                    else:
                        # assume numpy array with columns in known FEATURE_COLS
                        records = [dict(enumerate(row)) for row in X]
                    res = ml_hotspot.predict_cells(records)
                    probs = np.array([r.get("p_hotspot", 0.0) for r in res])
                    return np.vstack([1 - probs, probs]).T

            pipeline = _Wrapper()
        except Exception:
            raise RuntimeError(f"Model file not found at {MODEL_PATH} and fallback failed")
    return pipeline


_PIPELINE = _load_pipeline()


def _select_feature_columns(pipeline, df: pd.DataFrame) -> List[str]:
    # Try pipeline.feature_names_in_
    cols: List[str] = []
    if hasattr(pipeline, "feature_names_in_"):
        cols = [c for c in pipeline.feature_names_in_ if c in df.columns]
    else:
        # reasonable defaults used when training; include common engineered/date/depth features
        candidates = [
            "lat",
            "lon",
            "date",
            "year",
            "YEAR",
            "month",
            "MONTH",
            "sst",
            "sss",
            "ssh",
            "chlo",
            "chlo_phytoplankton",
            "depth",
            "depth_abs",
            "ssd",
            "month_sin",
            "month_cos",
            "SPECIES_CODE",
        ]
        cols = [c for c in candidates if c in df.columns]
    if not cols:
        # fallback to all numeric columns except date
        cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    return cols


def predict_hotspots(date: str, species_code: str = "YFT", threshold: float = 0.6, top_k: Optional[int] = 100) -> Dict[str, Any]:
    """Main entry: loads env grid, predicts probs, filters and returns summary + geojson.

    - `date`: YYYYMMDD string matching filenames `env_grid_<date>.csv`
    - `species_code`: species label to inject
    - `threshold`: probability threshold (0-1)
    - `top_k`: optional number of top cells to keep (overrides threshold if provided)
    """
    df = load_env_grid(date)
    total_cells = len(df)

    # attach species
    df = df.copy()
    df["SPECIES_CODE"] = species_code

    # Prepare features to pass to pipeline
    feat_cols = _select_feature_columns(_PIPELINE, df)
    if isinstance(df, pd.DataFrame):
        X = df[feat_cols]
    else:
        X = df[feat_cols].values

    # Compute probabilities
    try:
        probs = _PIPELINE.predict_proba(X)[:, 1]
    except Exception as e:
        # last attempt: convert X to numpy
        probs = _PIPELINE.predict_proba(np.asarray(X))[:, 1]

    df["prob"] = probs.astype(float)

    # Ensure uppercase column variants exist for fallback pipeline implementations
    # that expect keys like 'LAT', 'LON', 'YEAR', etc.
    try:
        for c in list(df.columns):
            up = c.upper()
            if up not in df.columns:
                df[up] = df[c]
    except Exception:
        pass

    # Derived numeric features required by the model
    # month_sin / month_cos
    try:
        df["month_sin"] = np.sin(2 * np.pi * df["month"].astype(float) / 12.0)
        df["month_cos"] = np.cos(2 * np.pi * df["month"].astype(float) / 12.0)
    except Exception:
        df["month_sin"] = np.nan
        df["month_cos"] = np.nan

    # Ensure sst/sss/ssh/chlo columns exist
    for col in ["sst", "sss", "ssh", "chlo"]:
        if col not in df.columns:
            df[col] = np.nan

    # Depth lookup using GEBCO netcdf (vectorized over unique coords)
    if "depth" not in df.columns:
        df["depth"] = np.nan
    try:
        coords = df[["lat", "lon"]].drop_duplicates()
        depth_map = {}
        for _, r in coords.iterrows():
            latv = float(r["lat"])
            lonv = float(r["lon"])
            try:
                dres = depth_service.get_depth(latv, lonv)
                depth_map[(latv, lonv)] = dres.get("value")
            except Exception:
                depth_map[(latv, lonv)] = np.nan
        df["depth"] = df.apply(lambda row: depth_map.get((float(row["lat"]), float(row["lon"])), np.nan) if pd.isna(row.get("depth")) else row.get("depth"), axis=1)
    except Exception:
        df["depth"] = df.get("depth", pd.Series([np.nan] * len(df)))

    # depth_abs
    try:
        df["depth_abs"] = df["depth"].abs()
    except Exception:
        df["depth_abs"] = np.nan

    # Compute sea surface density (ssd) using gsw when possible
    if "ssd" not in df.columns:
        df["ssd"] = np.nan
    if _HAS_GSW:
        try:
            # convert columns to numeric arrays
            sp = pd.to_numeric(df.get("sss", pd.Series([np.nan] * len(df))), errors="coerce").to_numpy(dtype=float)
            t = pd.to_numeric(df.get("sst", pd.Series([np.nan] * len(df))), errors="coerce").to_numpy(dtype=float)
            lats = df["lat"].to_numpy(dtype=float)
            lons = df["lon"].to_numpy(dtype=float)
            p = np.zeros(len(df))
            for i in range(len(df)):
                try:
                    if not np.isnan(sp[i]) and not np.isnan(t[i]):
                        SA = gsw.SA_from_SP(sp[i], p[i], lons[i], lats[i])
                        CT = gsw.CT_from_t(SA, t[i], p[i])
                        dens = gsw.rho(SA, CT, p[i])
                        df.at[df.index[i], "ssd"] = float(dens)
                except Exception:
                    df.at[df.index[i], "ssd"] = np.nan
        except Exception:
            pass

    # monsoon categorical (simple heuristic)
    def _monsoon_fn(m):
        try:
            mi = int(m)
        except Exception:
            return "UNK"
        if mi in (12, 1, 2):
            return "NE"
        if 5 <= mi <= 9:
            return "SW"
        return "INTER"

    try:
        df["monsoon"] = df["month"].apply(_monsoon_fn)
    except Exception:
        df["monsoon"] = "UNK"

    # Apply filter: top_k or threshold
    if top_k is not None:
        df_sorted = df.sort_values("prob", ascending=False).head(top_k)
    else:
        df_sorted = df[df["prob"] >= float(threshold)].copy()

    hotspot_count = len(df_sorted)
    max_prob = float(df_sorted["prob"].max()) if hotspot_count > 0 else 0.0
    avg_prob = float(df_sorted["prob"].mean()) if hotspot_count > 0 else 0.0

    # Build GeoJSON FeatureCollection
    features: List[Dict[str, Any]] = []
    for _, row in df_sorted.iterrows():
        lat = float(row["lat"])
        lon = float(row["lon"])
        props = {
            "prob": float(row["prob"]),
            "species_code": str(species_code),
            "sst": float(row.get("sst", np.nan)) if pd.notna(row.get("sst")) else None,
            "sss": float(row.get("sss", np.nan)) if pd.notna(row.get("sss")) else None,
            "ssh": float(row.get("ssh", np.nan)) if pd.notna(row.get("ssh")) else None,
            "chl": float(row.get("chl", np.nan)) if pd.notna(row.get("chl")) else None,
            "lat": lat,
            "lon": lon,
        }
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        })

    geojson = {"type": "FeatureCollection", "features": features}

    summary = {
        "total_cells": int(total_cells),
        "hotspot_count": int(hotspot_count),
        "max_prob": round(max_prob, 6),
        "avg_prob": round(avg_prob, 6),
    }

    return {
        "date": date,
        "species": species_code,
        "threshold": float(threshold),
        "summary": summary,
        "geojson": geojson,
    }


def predict_hotspots_region(
    date: str,
    species_code: str = "YFT",
    threshold: float = 0.6,
    top_k: Optional[int] = 100,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Predict hotspots for a region defined by bbox = (min_lat, max_lat, min_lon, max_lon).

    `overrides` can contain keys like 'sst' or 'ssh' with numeric values to replace those columns
    in the env grid before prediction.
    """
    try:
        df = load_env_grid(date)
        total_cells = len(df)
    except FileNotFoundError:
        # If env grid CSV doesn't exist, but a bbox is provided, synthesize
        # a small regular grid inside the bbox so frontend can send
        # `overrides` (sst/ssh) and get predictions without precomputed CSVs.
        if bbox is None:
            raise
        min_lat, max_lat, min_lon, max_lon = bbox
        # choose resolution: aim for ~50x50 cells but clamp
        lat_span = max_lat - min_lat
        lon_span = max_lon - min_lon
        # compute number of points proportional to bbox size, but bounded
        nx = min(max(int(lon_span / 0.02), 10), 80)
        ny = min(max(int(lat_span / 0.02), 10), 80)
        lats = np.linspace(min_lat, max_lat, ny)
        lons = np.linspace(min_lon, max_lon, nx)
        rows = []
        for lat in lats:
            for lon in lons:
                rows.append({
                    "lat": float(lat),
                    "lon": float(lon),
                    "sst": np.nan,
                    "sss": np.nan,
                    "ssh": np.nan,
                    "chl": np.nan,
                })
        df = pd.DataFrame(rows)
        # attach date column so feature transformers expecting date/YEAR work
        try:
            df["date"] = str(date)
            # common engineered features some pipelines use
            df["YEAR"] = int(str(date)[:4])
        except Exception:
            pass
        total_cells = len(df)

    # apply bbox filter if provided
    if bbox is not None:
        min_lat, max_lat, min_lon, max_lon = bbox
        df = df[(df["lat"] >= min_lat) & (df["lat"] <= max_lat) & (df["lon"] >= min_lon) & (df["lon"] <= max_lon)].copy()

    filtered_total = len(df)

    # attach species
    df["SPECIES_CODE"] = species_code

    # apply overrides
    if overrides:
        for k, v in overrides.items():
            if k in df.columns and v is not None:
                try:
                    df[k] = float(v)
                except Exception:
                    # if conversion fails, skip
                    pass
    # Ensure `year` and `month` columns (lowercase) for model
    try:
        year_int = int(str(date)[:4])
        month_int = int(str(date)[4:6])
    except Exception:
        now = pd.Timestamp.utcnow()
        year_int = int(now.year)
        month_int = int(now.month)
    df["year"] = year_int
    df["month"] = month_int
    # also provide uppercase variants some pipelines expect
    df["YEAR"] = year_int
    df["MONTH"] = month_int
    # Ensure pipeline-required columns exist (some pipelines expect engineered date fields)
    if hasattr(_PIPELINE, "feature_names_in_"):
        for req_col in _PIPELINE.feature_names_in_:
            if req_col not in df.columns:
                try:
                    rc = req_col.upper()
                    if rc == "YEAR" and date is not None:
                        df[req_col] = int(str(date)[:4])
                    elif rc == "MONTH" and date is not None:
                        df[req_col] = int(str(date)[4:6])
                    elif rc == "DAY" and date is not None:
                        df[req_col] = int(str(date)[6:8])
                    else:
                        df[req_col] = np.nan
                except Exception:
                    df[req_col] = np.nan

    # Prepare and predict similarly to predict_hotspots
    feat_cols = _select_feature_columns(_PIPELINE, df)
    X = df[feat_cols]
    try:
        probs = _PIPELINE.predict_proba(X)[:, 1]
    except Exception:
        probs = _PIPELINE.predict_proba(np.asarray(X))[:, 1]

    df["prob"] = probs.astype(float)

    if top_k is not None:
        df_sorted = df.sort_values("prob", ascending=False).head(top_k)
    else:
        df_sorted = df[df["prob"] >= float(threshold)].copy()

    hotspot_count = len(df_sorted)
    max_prob = float(df_sorted["prob"].max()) if hotspot_count > 0 else 0.0
    avg_prob = float(df_sorted["prob"].mean()) if hotspot_count > 0 else 0.0

    features: List[Dict[str, Any]] = []
    for _, row in df_sorted.iterrows():
        lat = float(row["lat"])
        lon = float(row["lon"])
        props = {
            "prob": float(row["prob"]),
            "species_code": str(species_code),
            "sst": float(row.get("sst", np.nan)) if pd.notna(row.get("sst")) else None,
            "sss": float(row.get("sss", np.nan)) if pd.notna(row.get("sss")) else None,
            "ssh": float(row.get("ssh", np.nan)) if pd.notna(row.get("ssh")) else None,
            "chl": float(row.get("chl", np.nan)) if pd.notna(row.get("chl")) else None,
            "lat": lat,
            "lon": lon,
        }
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        })

    geojson = {"type": "FeatureCollection", "features": features}

    summary = {
        "total_cells": int(filtered_total),
        "hotspot_count": int(hotspot_count),
        "max_prob": round(max_prob, 6),
        "avg_prob": round(avg_prob, 6),
    }

    return {
        "date": date,
        "species": species_code,
        "threshold": float(threshold),
        "summary": summary,
        "geojson": geojson,
    }
