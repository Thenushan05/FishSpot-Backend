"""
Local-ground spot predictor.

POST /api/v1/localground/predict
  Body: { "lat": float, "lng": float, "name": str (optional) }

Steps
-----
1. Fetch current weather from Open-Meteo (wind_speed_10m, surface_pressure,
   precipitation) for the given coordinates.
2. Derive date-cyclical features from today's UTC date.
3. Use fallback lstm_pred_kg = 0  (no time-series history available for
   a free-form spot).
4. Run the local XGBoost model and return the result.
"""

from __future__ import annotations

import math
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import joblib
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# ── Model loading ─────────────────────────────────────────────────────────────
_MODEL_PATH = Path(__file__).resolve().parents[2] / "ml" / "localground" / "xgb_model.joblib"

_model = None

def _get_model():
    global _model
    if _model is None:
        if not _MODEL_PATH.exists():
            raise RuntimeError(f"Local-ground model not found at {_MODEL_PATH}")
        print(f"[LocalGround] 📦 Loading XGBoost model from disk ...")
        print(f"[LocalGround]    Path: {_MODEL_PATH}")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            _model = joblib.load(_MODEL_PATH)
        print(f"[LocalGround] ✅ Model loaded successfully")
        print(f"[LocalGround]    Type      : {type(_model).__name__}")
        print(f"[LocalGround]    Features  : {_FEATURE_COLS}")
    else:
        print(f"[LocalGround] ♻️  Model already in memory (cached) — skipping disk load")
    return _model

# Feature column order must match training
_FEATURE_COLS = [
    "wind_speed",
    "pressure",
    "precip",
    "day_of_year_sin",
    "day_of_year_cos",
    "month_sin",
    "month_cos",
    "lstm_pred_kg",
]

# ── Router ────────────────────────────────────────────────────────────────────
router = APIRouter()


class SpotPredictRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    name: Optional[str] = Field(None, max_length=120)
    total_kg_latest: float = Field(
        0.0, ge=0,
        description="Most recent catch (kg) for this spot — used as lstm_pred_kg fallback. "
                    "Higher values push the hotspot probability up."
    )


class WeatherData(BaseModel):
    wind_speed: float
    pressure: float
    precip: float


class SpotPredictResponse(BaseModel):
    name: Optional[str]
    lat: float
    lng: float
    score: float          # 0-100
    p_hotspot: float      # 0-1
    level: str            # High | Moderate | Low
    weather: WeatherData
    features_used: dict


async def _fetch_weather(lat: float, lng: float) -> WeatherData:
    """Fetch current weather from Open-Meteo for a given coordinate."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lng}"
        "&current=wind_speed_10m,surface_pressure,precipitation"
        "&wind_speed_unit=ms"  # m/s consistent with training
    )
    print(f"\n[LocalGround] 🌐 Fetching weather from Open-Meteo ...")
    print(f"[LocalGround]    URL: {url}")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        current = data.get("current", {})
        weather = WeatherData(
            wind_speed=float(current.get("wind_speed_10m", 5.0)),
            pressure=float(current.get("surface_pressure", 1010.0)),
            precip=float(current.get("precipitation", 0.0)),
        )
        print(f"[LocalGround] ✅ Weather received:")
        print(f"[LocalGround]    wind_speed  = {weather.wind_speed} m/s")
        print(f"[LocalGround]    pressure    = {weather.pressure} hPa")
        print(f"[LocalGround]    precip      = {weather.precip} mm")
        return weather
    except Exception as exc:
        print(f"[LocalGround] ❌ Weather fetch failed: {exc}")
        raise HTTPException(
            status_code=502,
            detail=f"Weather fetch failed: {exc}",
        )


def _date_features(dt: datetime) -> dict:
    """Return cyclical day-of-year and month features."""
    doy = dt.timetuple().tm_yday
    month = dt.month
    return {
        "day_of_year_sin": math.sin(2 * math.pi * doy / 365),
        "day_of_year_cos": math.cos(2 * math.pi * doy / 365),
        "month_sin": math.sin(2 * math.pi * month / 12),
        "month_cos": math.cos(2 * math.pi * month / 12),
    }


@router.post("/predict", response_model=SpotPredictResponse)
async def predict_spot(req: SpotPredictRequest):
    now_ts = datetime.now(timezone.utc)
    print(f"\n[LocalGround] {'='*50}")
    print(f"[LocalGround] 🎣 SCAN REQUEST  [{now_ts.strftime('%Y-%m-%d %H:%M:%S UTC')}]")
    print(f"[LocalGround] {'='*50}")
    print(f"[LocalGround]    Spot        : {req.name or 'Unnamed'}")
    print(f"[LocalGround]    Coordinates : lat={req.lat}, lng={req.lng}")
    print(f"[LocalGround]    Total kg    : {req.total_kg_latest} kg  (→ lstm_pred_kg fallback)")

    print(f"[LocalGround] ")
    print(f"[LocalGround] ── STEP 1: Weather Fetch ──────────────────────")
    weather = await _fetch_weather(req.lat, req.lng)

    print(f"[LocalGround] ")
    print(f"[LocalGround] ── STEP 2: Date Features ──────────────────────")
    now = datetime.now(timezone.utc)
    date_feats = _date_features(now)

    row = {
        "wind_speed":       weather.wind_speed,
        "pressure":         weather.pressure,
        "precip":           weather.precip,
        "day_of_year_sin":  date_feats["day_of_year_sin"],
        "day_of_year_cos":  date_feats["day_of_year_cos"],
        "month_sin":        date_feats["month_sin"],
        "month_cos":        date_feats["month_cos"],
        "lstm_pred_kg":     req.total_kg_latest,  # fallback from input (no LSTM history)
    }

    print(f"[LocalGround]    day_of_year_sin = {date_feats['day_of_year_sin']:.6f}")
    print(f"[LocalGround]    day_of_year_cos = {date_feats['day_of_year_cos']:.6f}")
    print(f"[LocalGround]    month_sin       = {date_feats['month_sin']:.6f}")
    print(f"[LocalGround]    month_cos       = {date_feats['month_cos']:.6f}")
    print(f"[LocalGround]    (today UTC: {now.strftime('%Y-%m-%d')}  day_of_year={now.timetuple().tm_yday})")

    print(f"[LocalGround] ")
    print(f"[LocalGround] ── STEP 3: Model Inference ────────────────────")
    print(f"[LocalGround] 🧮 Running XGBoost model ...")
    print(f"[LocalGround]    Input features (all 8 columns):")
    for k, v in row.items():
        print(f"[LocalGround]      {k:<22} = {v:.6f}" if isinstance(v, float) else f"[LocalGround]      {k:<22} = {v}")

    X = pd.DataFrame([row])[_FEATURE_COLS]

    try:
        model = _get_model()
        p = float(model.predict_proba(X)[0, 1])
    except Exception as exc:
        print(f"[LocalGround] ❌ Model prediction failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Model prediction failed: {exc}")

    level = "High" if p >= 0.7 else "Moderate" if p >= 0.4 else "Low"
    print(f"[LocalGround] ")
    print(f"[LocalGround] ── RESULT ────────────────────────────────────")
    print(f"[LocalGround] ✅ p_hotspot  = {p:.4f}")
    print(f"[LocalGround] ✅ score      = {round(p*100,1)}%")
    print(f"[LocalGround] ✅ level      = {level}")
    print(f"[LocalGround] ")
    print(f"[LocalGround] ── Feature Importance Note ───────────────────")
    print(f"[LocalGround]    lstm_pred_kg   ← 28.4%  (from total_kg={req.total_kg_latest})")
    print(f"[LocalGround]    month_sin      ← 24.8%  (seasonal)")
    print(f"[LocalGround]    day_of_year_cos← 24.4%  (seasonal)")
    print(f"[LocalGround]    day_of_year_sin← 22.5%  (seasonal)")
    print(f"[LocalGround]    wind/pressure/precip ← 0%  (not used by this model)")
    print(f"[LocalGround] {'='*50}\n")

    return SpotPredictResponse(
        name=req.name,
        lat=req.lat,
        lng=req.lng,
        score=round(p * 100, 1),
        p_hotspot=round(p, 4),
        level=level,
        weather=weather,
        features_used={**row, "date_utc": now.date().isoformat()},
    )
