"""Prediction helper for region hotspots.

This module provides a compact, robust `predict_hotspots_region` used by tests
and development. It attempts to load a sklearn/joblib pipeline from common
locations; if none is available it returns heuristic probabilities so the API
and frontend can be exercised without the trained model.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
import joblib

from app.services.env_loader import load_env_grid
from app.services import depth_service


# Primary and alternative model locations
MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "fish_hotspot_xgb_species.joblib"
ALT_MODEL = Path(__file__).resolve().parents[1] / "ml" / "xgb_classification_tuned.joblib"


def _load_pipeline():
    # Prefer a model in the project's `models/` directory, then repo `app/ml`.
    if MODEL_PATH.exists():
        return joblib.load(MODEL_PATH)
    if ALT_MODEL.exists():
        return joblib.load(ALT_MODEL)

    # As a last resort try to adapt the legacy `app.services.ml_hotspot` if present.
    try:
        from app.services import ml_hotspot

        class _Wrapper:
            def predict_proba(self, X):
                # Accept DataFrame or array-like. Convert to list-of-dicts expected
                # by the legacy `ml_hotspot.predict_cells` function.
                if isinstance(X, pd.DataFrame):
                    records = X.to_dict(orient="records")
                else:
                    records = [dict(enumerate(row)) for row in X]

                # Uppercase string keys to match legacy FEATURE_COLS like 'LAT','YEAR'
                def _upper_keys(rec):
                    new = {}
                    for k, v in rec.items():
                        try:
                            new_key = k.upper() if isinstance(k, str) else k
                        except Exception:
                            new_key = k
                        new[new_key] = v
                    return new

                records = [_upper_keys(r) for r in records]

                # Try to call legacy predictor
                res = ml_hotspot.predict_cells(records)
                probs = [r.get("p_hotspot", 0.0) for r in res]
                return np.vstack([1 - np.array(probs), np.array(probs)]).T

        return _Wrapper()
    except Exception:
        return None


_PIPELINE = _load_pipeline()


def _synthesize_grid(bbox: Tuple[float, float, float, float]) -> pd.DataFrame:
    min_lat, max_lat, min_lon, max_lon = bbox
    lat_span = max_lat - min_lat
    lon_span = max_lon - min_lon
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
    return pd.DataFrame(rows)


def _mock_probs(df: pd.DataFrame) -> np.ndarray:
    # simple heuristic: prefer SST near 28C and shallow depth
    sst = pd.to_numeric(df.get("sst", pd.Series([np.nan] * len(df))), errors="coerce").fillna(26.0).to_numpy(dtype=float)
    depth_abs = pd.to_numeric(df.get("depth_abs", pd.Series([np.nan] * len(df))), errors="coerce").fillna(50.0).to_numpy(dtype=float)
    sst_score = np.exp(-0.5 * ((sst - 28.0) / 2.0) ** 2)
    depth_score = 1.0 / (1.0 + (depth_abs / 50.0))
    raw = 0.6 * sst_score + 0.4 * depth_score
    return np.clip(raw, 0.0, 1.0)


def _select_feature_columns(pipeline, df: pd.DataFrame) -> List[str]:
    if pipeline is None:
        return [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    if hasattr(pipeline, "feature_names_in_"):
        return [c for c in pipeline.feature_names_in_ if c in df.columns]
    # reasonable defaults
    candidates = [
        "lat",
        "lon",
        "year",
        "month",
        "sst",
        "sss",
        "ssh",
        "chl",
        "depth",
        "depth_abs",
        "ssd",
        "month_sin",
        "month_cos",
        "SPECIES_CODE",
    ]
    return [c for c in candidates if c in df.columns]


def predict_hotspots_region(
    date: str,
    species_code: str = "YFT",
    threshold: float = 0.6,
    top_k: Optional[int] = 100,
    bbox: Optional[Tuple[float, float, float, float]] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Predict hotspots for a region; returns summary + geojson.

    If the env csv for `date` doesn't exist and `bbox` is provided, a
    synthesized regular grid inside `bbox` is produced so the API can be
    exercised without precomputed grids.
    """
    try:
        df = load_env_grid(date)
        total_cells = len(df)
    except FileNotFoundError:
        if bbox is None:
            raise
        df = _synthesize_grid(bbox)
        df["date"] = str(date)
        df["YEAR"] = int(str(date)[:4])
        total_cells = len(df)

    # bbox filter
    if bbox is not None:
        min_lat, max_lat, min_lon, max_lon = bbox
        df = df[(df["lat"] >= min_lat) & (df["lat"] <= max_lat) & (df["lon"] >= min_lon) & (df["lon"] <= max_lon)].copy()

    # attach species
    df["SPECIES_CODE"] = species_code

    # apply scalar overrides
    if overrides:
        for k, v in overrides.items():
            if k in df.columns and v is not None:
                try:
                    df[k] = float(v)
                except Exception:
                    pass

    # ensure year/month and cyclic features
    try:
        year_val = int(str(date)[:4])
        month_val = int(str(date)[4:6])
    except Exception:
        from datetime import datetime

        now = datetime.utcnow()
        year_val = now.year
        month_val = now.month

    df["year"] = df.get("year", year_val)
    df["month"] = df.get("month", month_val)
    df["YEAR"] = df.get("YEAR", year_val)
    df["MONTH"] = df.get("MONTH", month_val)
    df["month_sin"] = np.sin(2 * np.pi * df["month"].astype(float) / 12.0)
    df["month_cos"] = np.cos(2 * np.pi * df["month"].astype(float) / 12.0)

    # depth lookup for missing depths (batched)
    if "depth" not in df.columns:
        df["depth"] = np.nan
    need = df["depth"].isna()
    if need.any():
        lats = df.loc[need, "lat"].tolist()
        lons = df.loc[need, "lon"].tolist()
        try:
            depth_results = depth_service.get_depths(lats, lons)
            for idx, res in zip(df.loc[need].index.tolist(), depth_results):
                v = res.get("value")
                df.at[idx, "depth"] = float(v) if v is not None else np.nan
        except Exception:
            pass

    df["depth_abs"] = df["depth"].abs()

    # compute ssd fallback
    try:
        import gsw  # type: ignore

        p = 0
        sss_arr = df.get("sss", pd.Series([np.nan] * len(df))).to_numpy(dtype=float)
        sst_arr = df.get("sst", pd.Series([np.nan] * len(df))).to_numpy(dtype=float)
        lat_arr = df["lat"].to_numpy(dtype=float)
        lon_arr = df["lon"].to_numpy(dtype=float)
        try:
            SA = gsw.SA_from_SP(sss_arr, p, lon_arr, lat_arr)
            CT = gsw.CT_from_t(SA, sst_arr, p)
            rho = gsw.rho(SA, CT, p)
            df["ssd"] = rho
        except Exception:
            df["ssd"] = np.nan
    except Exception:
        if "sss" in df.columns and "sst" in df.columns:
            df["ssd"] = 1027.0 + 0.2 * (df["sss"].fillna(35) - 35) - 0.03 * (df["sst"].fillna(15) - 15)
        else:
            df["ssd"] = np.nan

    # monsoon categorical
    df["monsoon"] = df["month"].apply(lambda m: "SW" if m in [5, 6, 7, 8, 9] else ("NE" if m in [11, 12, 1, 2, 3] else "Inter"))

    # predict
    probs = None
    if _PIPELINE is not None:
        try:
            feat_cols = _select_feature_columns(_PIPELINE, df)
            X = df[feat_cols]
            probs = _PIPELINE.predict_proba(X)[:, 1]
        except Exception:
            probs = None

    if probs is None:
        probs = _mock_probs(df)

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
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props})

    geojson = {"type": "FeatureCollection", "features": features}

    summary = {"total_cells": int(len(df)), "hotspot_count": int(hotspot_count), "max_prob": round(max_prob, 6), "avg_prob": round(avg_prob, 6)}

    return {"date": date, "species": species_code, "threshold": float(threshold), "summary": summary, "geojson": geojson}
