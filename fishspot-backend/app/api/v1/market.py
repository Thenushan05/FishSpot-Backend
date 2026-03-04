"""
Market price prediction API endpoint.

Uses `app/ml/market/ensemble_voting_balanced.pkl` — a VotingRegressor(XGBRegressor,
RidgeRegressor) trained on historical Sri Lankan fish market price data.

18-feature vector layout (inferred from model inspection):
  [0]  species_YFT       – one-hot (1 if YFT else 0)
  [1]  species_BET
  [2]  species_SKJ
  [3]  species_COM
  [4]  species_SWO
  [5]  species_MAHI
  [6]  species_BUM
  [7]  monsoon_active    – 1 during SW monsoon (May-Sep), else 0
  [8]  month             – 1-12
  [9]  catch_vol_norm    – normalised catch volume proxy (0-10)
  [10] export_demand     – export activity index (0-50)
  [11] local_demand      – domestic-market demand score (0-20)
  [12] market_pressure   – primary price driver (0-200);  XGB importance ≈ 0.44
  [13] seasonal_premium  – seasonal uplift score (0-50)
  [14] export_premium    – export-grade premium index (0-100)
  [15] supply_surplus    – surplus suppresses price (0-50)
  [16] weather_factor    – weather-induced supply disruption (0-10)
  [17] trend_momentum    – recent-price momentum (0-50)
"""

from __future__ import annotations

import json
import math
import pickle
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()

# ── Model ──────────────────────────────────────────────────────────────────────
_MODEL_PATH = Path(__file__).resolve().parents[2] / "ml" / "market" / "ensemble_voting_balanced.pkl"

def _load_model():
    if _MODEL_PATH.exists():
        with open(_MODEL_PATH, "rb") as f:
            return pickle.load(f)
    return None

_MODEL = _load_model()
print(f"🏪 Market model: {'✅ loaded' if _MODEL else '❌ not found'} ({_MODEL_PATH})")


# ── Per-species calibration data (based on 2024 Sri Lankan fish market prices) ──
# Keys: species code; Values: dict with base_pressure, monthly_profile, base_lkr
_SPECIES_PROFILE = {
    "YFT":  dict(base_pressure=165, monthly=[ 0,-5,-8, 5,15,22,18,12,-5,-8,-3, 2], base_lkr=1050),
    "BET":  dict(base_pressure=175, monthly=[ 0,-8,-5, 8,18,25,20,15,-5,-8,-3, 2], base_lkr=1150),
    "SKJ":  dict(base_pressure= 50, monthly=[ 0,-5, 0,10,20,15,10, 5, 0,-5,-3,-1], base_lkr= 550),
    "COM":  dict(base_pressure= 80, monthly=[-5,-2, 5,12,18,15,10, 5,-2,-5,-3,-1], base_lkr= 730),
    "SWO":  dict(base_pressure=145, monthly=[ 5, 8,10,12, 5,-5,-8,-5, 5,10, 8, 5], base_lkr=1020),
    "MAHI": dict(base_pressure=120, monthly=[ 8,12, 5, 0,-5,-8,-5, 0, 8,15,12, 8], base_lkr= 900),
    "BUM":  dict(base_pressure=110, monthly=[-5,-2, 2, 5,15,20,15, 8, 2,-5,-5,-5], base_lkr= 850),
    "SAX":  dict(base_pressure=100, monthly=[ 2, 5, 8,10, 8, 5, 5, 8,10, 8, 5, 2], base_lkr= 800),
    # remaining model-supported codes
    "ALB":  dict(base_pressure=140, monthly=[ 0, 0, 2, 5,10,12,10, 5, 0,-2, 0, 0], base_lkr= 980),
    "BLT":  dict(base_pressure= 60, monthly=[ 0,-2, 2, 8,15,12, 8, 5, 0,-2,-1,-1], base_lkr= 620),
    "FRI":  dict(base_pressure= 45, monthly=[ 0,-2, 2, 5,10, 8, 5, 3, 0,-2,-1,-1], base_lkr= 500),
    "KAW":  dict(base_pressure= 55, monthly=[-2, 0, 5,10,15,12, 8, 5,-2,-3,-2,-1], base_lkr= 580),
    "LOT":  dict(base_pressure= 70, monthly=[ 2, 2, 4, 8,12,10, 8, 5, 2,-2,-1, 0], base_lkr= 660),
    "MAK":  dict(base_pressure= 85, monthly=[-2, 0, 5,10,15,12, 8, 5,-2,-3,-2,-1], base_lkr= 740),
    "MAN":  dict(base_pressure= 75, monthly=[-5,-2, 5,12,18,15,10, 5,-2,-5,-3,-1], base_lkr= 690),
    "MLS":  dict(base_pressure=135, monthly=[ 5, 8,10,12, 5,-5,-8,-5, 5,10, 8, 5], base_lkr= 960),
    "SBF":  dict(base_pressure=180, monthly=[ 5, 8,10,15, 5,-8,-10,-5, 5,12, 8, 5], base_lkr=1200),
    "SKH":  dict(base_pressure= 95, monthly=[ 0, 2, 5,10,12, 8, 5, 2, 0,-2,-1, 0], base_lkr= 780),
    "SFA":  dict(base_pressure=115, monthly=[ 2, 5, 8,12,10, 5, 5, 8,10, 8, 5, 2], base_lkr= 870),
    "SMA":  dict(base_pressure=125, monthly=[ 2, 5, 8,12, 8, 3, 3, 8,10, 8, 5, 2], base_lkr= 920),
    "SPN":  dict(base_pressure=130, monthly=[ 2, 5,10,12, 8, 3, 3, 8,10, 8, 5, 2], base_lkr= 940),
    "SRX":  dict(base_pressure= 90, monthly=[ 0, 2, 5,10,12, 8, 5, 2, 0,-2,-1, 0], base_lkr= 760),
    "TUN":  dict(base_pressure=155, monthly=[ 0,-5,-5, 5,15,20,18,12,-2,-5,-3, 0], base_lkr=1080),
    "UNCL": dict(base_pressure= 65, monthly=[ 0, 0, 2, 5, 8, 5, 3, 2, 0,-2,-1, 0], base_lkr= 600),
}

_SPECIES_IDX = {code: i for i, code in enumerate(["YFT", "BET", "SKJ", "COM", "SWO", "MAHI", "BUM"])}

_SW_MONSOON   = {5, 6, 7, 8, 9}
_NE_MONSOON   = {11, 12, 1, 2}
_FESTIVAL_MAP = {  # month → approx festival premium (LKR/kg context → market_pressure delta)
    4:  12,  # Sinhala/Tamil New Year
    12: 10,  # Christmas / Year-end
    5:  6,   # Vesak
    8:  4,   # Independence Day adjacent
}

def _get_monsoon_name(month: int) -> str:
    if month in _SW_MONSOON:  return "Southwest Monsoon"
    if month in _NE_MONSOON:  return "Northeast Monsoon"
    if month in {3, 4}:       return "First Inter-Monsoon"
    return "Second Inter-Monsoon"


# ── Sri Lanka Public Holidays (date.nager.at — free, no key) ──────────────────
_HOLIDAYS_CACHE: dict[int, list[dict]] = {}

def _fetch_lk_holidays(year: int) -> list[dict]:
    """Fetch Sri Lanka public holidays; cached per year. Falls back to hardcoded list."""
    if year in _HOLIDAYS_CACHE:
        return _HOLIDAYS_CACHE[year]
    try:
        url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/LK"
        req = urllib.request.Request(url, headers={"User-Agent": "FishSpot/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            _HOLIDAYS_CACHE[year] = data
            print(f"📅 Loaded {len(data)} Sri Lanka holidays for {year} from API")
            return data
    except Exception as exc:
        print(f"⚠️  Holiday API unavailable for {year}: {exc} — using built-in list")
    # Hardcoded fallback — key Sri Lanka public holidays (fixed + approximate Poya dates)
    fallback = [
        {"date": f"{year}-01-14", "localName": "Tamil Thai Pongal Day"},
        {"date": f"{year}-02-04", "localName": "Independence Day"},
        {"date": f"{year}-03-13", "localName": "Madin Full Moon Poya"},
        {"date": f"{year}-04-13", "localName": "Sinhala & Tamil New Year Eve"},
        {"date": f"{year}-04-14", "localName": "Sinhala & Tamil New Year"},
        {"date": f"{year}-05-01", "localName": "Labour Day"},
        {"date": f"{year}-05-12", "localName": "Vesak Full Moon Poya"},
        {"date": f"{year}-05-13", "localName": "Day Following Vesak"},
        {"date": f"{year}-06-10", "localName": "Eid al-Adha (approx)"},
        {"date": f"{year}-07-10", "localName": "Esala Full Moon Poya"},
        {"date": f"{year}-08-08", "localName": "Nikini Full Moon Poya"},
        {"date": f"{year}-09-07", "localName": "Binara Full Moon Poya"},
        {"date": f"{year}-10-06", "localName": "Vap Full Moon Poya"},
        {"date": f"{year}-10-20", "localName": "Deepavali"},
        {"date": f"{year}-11-05", "localName": "Il Full Moon Poya"},
        {"date": f"{year}-12-04", "localName": "Unduvap Full Moon Poya"},
        {"date": f"{year}-12-25", "localName": "Christmas Day"},
    ]
    _HOLIDAYS_CACHE[year] = fallback
    return fallback


def _festival_boost_for_date(target_date: date) -> Tuple[float, Optional[str], int]:
    """
    Compute market-pressure boost from upcoming/current Sri Lanka holidays.
    Returns (boost_value, festival_name, days_until).
    Boost peaks at 20 on the holiday itself, fading linearly to 0 at 14 days ahead.
    Also considers 2 days past (post-festival demand tail).
    """
    # Gather holidays from current year + next year if we're late in year
    holidays = _fetch_lk_holidays(target_date.year)
    if target_date.month >= 11:
        holidays = holidays + _fetch_lk_holidays(target_date.year + 1)

    best_boost = 0.0
    best_name: Optional[str] = None
    best_days = 999

    for h in holidays:
        try:
            hd = date.fromisoformat(h["date"])
        except Exception:
            continue
        delta = (hd - target_date).days
        if -2 <= delta <= 14:          # within 14 days ahead or 2 days past
            days_until = max(0, delta)
            boost = max(0.0, 20.0 * (1.0 - days_until / 14.0))
            if boost > best_boost:
                best_boost = boost
                best_name = h.get("localName") or h.get("name", "Holiday")
                best_days = days_until

    return round(best_boost, 2), best_name, best_days


# Pre-warm holiday cache for current year on startup
try:
    _fetch_lk_holidays(date.today().year)
except Exception:
    pass

def _build_feature_vector(
    species: str,
    month: int,
    catch_vol: float = 5.0,    # 0-10 scale
    export_demand: float = 25.0,
    local_demand: float = 10.0,
    weather_factor: float = 2.0,
    festival_boost: float = 0.0,  # real-time boost from upcoming holidays (0-20)
) -> np.ndarray:
    """
    Construct the 18-element feature vector the market model expects.
    All values are deterministic. festival_boost raises market_pressure and
    seasonal_premium when a Sri Lanka public holiday is approaching.
    """
    prof = _SPECIES_PROFILE.get(species.upper(), _SPECIES_PROFILE["YFT"])
    mi   = month - 1  # 0-indexed
    monthly_delta = prof["monthly"][mi]

    # Festival premium elevates both market_pressure (F12) and seasonal_premium (F13)
    market_pressure  = max(0.0, float(prof["base_pressure"]) + monthly_delta + festival_boost * 0.5)

    seasonal_premium = max(0.0, monthly_delta + 10 + _FESTIVAL_MAP.get(month, 0) + festival_boost)
    export_premium   = max(0.0, export_demand * 1.5 + monthly_delta * 0.5)
    supply_surplus   = max(0.0, 25.0 - monthly_delta / 2)
    trend_momentum   = max(0.0, market_pressure * 0.15)

    monsoon_active = 1 if month in _SW_MONSOON else 0

    vec = np.zeros(18, dtype=float)
    sp_idx = _SPECIES_IDX.get(species.upper(), -1)
    if sp_idx >= 0:
        vec[sp_idx] = 1.0
    vec[7]  = monsoon_active
    vec[8]  = float(month)
    vec[9]  = float(catch_vol)
    vec[10] = float(export_demand)
    vec[11] = float(local_demand)
    vec[12] = float(market_pressure)
    vec[13] = float(seasonal_premium)
    vec[14] = float(export_premium)
    vec[15] = float(supply_surplus)
    vec[16] = float(weather_factor)
    vec[17] = float(trend_momentum)
    return vec


def _predict_price(
    species: str,
    month: int,
    catch_vol: float = 5.0,
    export_demand: float = 25.0,
    local_demand: float = 10.0,
    weather_factor: float = 2.0,
    festival_boost: float = 0.0,
) -> float:
    """Return predicted LKR/kg price for a species/month using the ML model."""
    if _MODEL is None:
        return _fallback_price(species, month)
    vec = _build_feature_vector(species, month, catch_vol, export_demand,
                                local_demand, weather_factor, festival_boost)
    try:
        pred = float(_MODEL.predict(vec.reshape(1, -1))[0])
    except Exception as e:
        print(f"⚠️ market model predict failed: {e}")
        return _fallback_price(species, month)
    return round(pred, 1)


def _predict_for_date(
    species: str,
    target_date: date,
    catch_vol: float = 5.0,
    export_demand: float = 25.0,
    local_demand: float = 10.0,
    weather_factor: float = 2.0,
) -> float:
    """
    Predict price for a specific calendar date.
    Automatically fetches Sri Lanka public holidays and applies festival boost
    to the feature vector before calling the ML model.
    """
    boost, _, _ = _festival_boost_for_date(target_date)
    return _predict_price(species, target_date.month,
                          catch_vol, export_demand, local_demand,
                          weather_factor, festival_boost=boost)


def _fallback_price(species: str, month: int) -> float:
    """Deterministic heuristic price used only when model file is unavailable."""
    prof = _SPECIES_PROFILE.get(species.upper(), _SPECIES_PROFILE["YFT"])
    base = prof["base_lkr"]
    monthly_delta = prof["monthly"][month - 1]
    return round(base + monthly_delta * 5, 1)


def _trend_label(pct: float) -> str:
    if pct >= 1.0:  return "Up"
    if pct <= -1.0: return "Down"
    return "Stable"


def _action(trend: str) -> str:
    return {"Up": "Buy", "Down": "Sell", "Stable": "Hold"}.get(trend, "Hold")

# ── Request / Response models ──────────────────────────────────────────────────

class MarketPredictRequest(BaseModel):
    species:    str  = Field("YFT", description="FAO species code")
    date:       Optional[str] = Field(None, description="ISO date YYYY-MM-DD; defaults to today")
    catch_vol:  float = Field(5.0, ge=0, le=10, description="Catch-volume proxy 0-10")
    export_idx: float = Field(25.0, ge=0, le=50, description="Export demand index 0-50")
    local_idx:  float = Field(10.0, ge=0, le=20, description="Local demand index 0-20")

# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/species")
def list_species():
    """Return all supported species codes with names and base prices."""
    species_meta = {
        "YFT": "Yellowfin Tuna",    "BET": "Bigeye Tuna",
        "SKJ": "Skipjack Tuna",     "COM": "Seer Fish (King Mackerel)",
        "SWO": "Swordfish",         "MAHI": "Mahi Mahi",
        "BUM": "Blue Marlin",       "SAX": "Sailfish",
        "ALB": "Albacore Tuna",     "BLT": "Bullet Tuna",
        "FRI": "Frigate Tuna",      "KAW": "Kawakawa",
        "LOT": "Longtail Tuna",     "MAK": "Mako Shark",
        "MAN": "Manta Ray",         "MLS": "Striped Marlin",
        "SBF": "Southern Bluefin",  "SKH": "Various Sharks",
        "SFA": "Indo-Pacific Sailfish", "SMA": "Shortfin Mako",
        "SPN": "Spearfish",         "SRX": "Stingrays",
        "TUN": "Tuna (unspecified)", "UNCL": "Uncategorised",
    }
    today = date.today()
    return {
        "species": [
            {
                "code":          code,
                "name":          name,
                "base_lkr":      _SPECIES_PROFILE.get(code, _SPECIES_PROFILE["YFT"])["base_lkr"],
                "current_price": round(_predict_for_date(code, today), 1),
            }
            for code, name in species_meta.items()
        ]
    }


@router.post("/predict")
def predict_price(req: MarketPredictRequest):
    """Predict today's market price and 7-day trend for a species."""
    target_date = date.fromisoformat(req.date) if req.date else date.today()
    month  = target_date.month
    year   = target_date.year
    species = req.species.upper()

    if species not in _SPECIES_PROFILE:
        raise HTTPException(status_code=400, detail=f"Unknown species code '{species}'")

    # Festival context for today
    fest_boost, fest_name, fest_days = _festival_boost_for_date(target_date)

    # Today's price — festival-aware model output
    today_price = _predict_price(species, month,
                                 catch_vol=req.catch_vol,
                                 export_demand=req.export_idx,
                                 local_demand=req.local_idx,
                                 festival_boost=fest_boost)

    # Yesterday reference for trend
    prev_date   = target_date - timedelta(days=1)
    prev_boost, _, _ = _festival_boost_for_date(prev_date)
    prev_price  = _predict_price(species, prev_date.month,
                                 catch_vol=req.catch_vol,
                                 export_demand=req.export_idx,
                                 local_demand=req.local_idx,
                                 festival_boost=prev_boost)
    pct_change  = round((today_price - prev_price) / max(prev_price, 1) * 100, 2)

    # Week-on-week (same day, last week)
    last_week   = target_date - timedelta(days=7)
    lw_boost, _, _ = _festival_boost_for_date(last_week)
    lw_price    = _predict_price(species, last_week.month,
                                 catch_vol=req.catch_vol,
                                 export_demand=req.export_idx,
                                 local_demand=req.local_idx,
                                 festival_boost=lw_boost)
    wow_pct     = round((today_price - lw_price) / max(lw_price, 1) * 100, 2)

    trend = _trend_label(wow_pct)

    # Build 7-day forecast — each day gets its own festival boost from the ML model
    forecast_7d = []
    for i in range(7):
        fd = target_date + timedelta(days=i)
        fd_boost, _, _ = _festival_boost_for_date(fd)
        fp = _predict_price(species, fd.month,
                            catch_vol=req.catch_vol,
                            export_demand=req.export_idx,
                            local_demand=req.local_idx,
                            festival_boost=fd_boost)
        forecast_7d.append({
            "date":         fd.isoformat(),
            "day_label":    fd.strftime("%a"),
            "price":        fp,
            "day_idx":      i,
            "festival_boost": fd_boost,
        })

    # Relative index (index=100 on day 0)
    base = forecast_7d[0]["price"]
    for pt in forecast_7d:
        pt["index"] = round(pt["price"] / max(base, 1) * 100, 1)

    # Confidence heuristic: simpler to predict when price is stable
    spread   = max(fp["price"] for fp in forecast_7d) - min(fp["price"] for fp in forecast_7d)
    conf_raw = max(0.55, min(0.97, 1.0 - spread / max(today_price, 1)))

    return {
        "species":      species,
        "date":         target_date.isoformat(),
        "today_price":  today_price,
        "prev_price":   prev_price,
        "pct_change":   pct_change,
        "wow_pct":      wow_pct,
        "trend":        trend,
        "confidence":   round(conf_raw, 3),
        "action":           _action(trend),
        "monsoon":          _get_monsoon_name(month),
        "festival_name":    fest_name,
        "festival_days":    fest_days if fest_name else None,
        "festival_boost":   fest_boost,
        "forecast_7d":      forecast_7d,
        "model_used":       _MODEL is not None,
    }


@router.get("/forecast")
def forecast_multi(
    species: str = Query("YFT", description="Species code"),
    days:    int = Query(30, ge=7, le=90),
    start:   Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
):
    """Return a multi-day forecast for one species (index relative to day 0 = 100)."""
    species = species.upper()
    if species not in _SPECIES_PROFILE:
        raise HTTPException(status_code=400, detail=f"Unknown species '{species}'")

    start_d = date.fromisoformat(start) if start else date.today()
    points  = []
    for i in range(days):
        fd = start_d + timedelta(days=i)
        fp = _predict_for_date(species, fd)
        points.append({"day": f"D{i+1}", "date": fd.isoformat(), "price": fp, "day_label": fd.strftime("%d %b")})

    base = points[0]["price"]
    for pt in points:
        pt["index"] = round(pt["price"] / max(base, 1) * 100, 1)

    return {"species": species, "days": days, "start": start_d.isoformat(), "points": points}


@router.get("/multi-species")
def multi_species_forecast(
    species: str = Query("YFT,BET,SKJ,COM,SWO", description="Comma-separated species codes"),
    days:    int = Query(30, ge=7, le=90),
    start:   Optional[str] = Query(None),
):
    """Return relative-index forecast for multiple species (for overlay chart)."""
    codes   = [s.strip().upper() for s in species.split(",") if s.strip()][:8]
    start_d = date.fromisoformat(start) if start else date.today()

    result = []
    for i in range(days):
        fd = start_d + timedelta(days=i)
        row: dict = {"day": f"D{i+1}", "date": fd.isoformat(), "day_label": fd.strftime("%d %b")}
        for code in codes:
            if code in _SPECIES_PROFILE:
                row[code] = _predict_for_date(code, fd)
        result.append(row)

    # Normalise to index=100 at day 0
    bases = {code: result[0].get(code, 1) for code in codes}
    for row in result:
        for code in codes:
            if code in row:
                row[f"{code}_idx"] = round(row[code] / max(bases[code], 1) * 100, 1)

    return {"codes": codes, "days": days, "start": start_d.isoformat(), "points": result}


@router.get("/summary")
def market_summary(
    target_date: Optional[str] = Query(None, alias="date", description="YYYY-MM-DD"),
):
    """Return price trend summary for all main species."""
    td    = date.fromisoformat(target_date) if target_date else date.today()
    month = td.month
    year  = td.year

    main_species = ["YFT", "BET", "SKJ", "COM", "SWO", "MAHI", "BUM", "SAX"]
    species_meta = {
        "YFT": "Yellowfin Tuna", "BET": "Bigeye Tuna", "SKJ": "Skipjack Tuna",
        "COM": "Seer Fish",      "SWO": "Swordfish",   "MAHI": "Mahi Mahi",
        "BUM": "Blue Marlin",    "SAX": "Sailfish",
    }

    summaries = []
    for code in main_species:
        current = _predict_for_date(code, td)
        last_wk = _predict_for_date(code, td - timedelta(days=7))
        wow     = round((current - last_wk) / max(last_wk, 1) * 100, 2)
        trend   = _trend_label(wow)

        # Next 7 day prices for sparkline — each point is festival-aware model output
        sparkline = []
        for j in range(7):
            sfd = td + timedelta(days=j)
            sparkline.append(round(_predict_for_date(code, sfd), 1))

        spread   = max(sparkline) - min(sparkline)
        conf     = max(0.55, min(0.97, 1.0 - spread / max(current, 1)))

        summaries.append({
            "code":       code,
            "name":       species_meta.get(code, code),
            "price":      current,
            "last_week":  last_wk,
            "wow_pct":    wow,
            "trend":      trend,
            "confidence": round(conf, 3),
            "action":     _action(trend),
            "sparkline":  sparkline,
        })

    # Include current festival info in summary
    fest_boost, fest_name, fest_days = _festival_boost_for_date(td)
    return {
        "date":           td.isoformat(),
        "monsoon":        _get_monsoon_name(month),
        "festival_name":  fest_name,
        "festival_days":  fest_days if fest_name else None,
        "festival_boost": fest_boost,
        "species":        summaries,
    }


@router.get("/weekly-outlook")
def weekly_outlook(
    species: str = Query("YFT"),
    start:   Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """4-week rolling outlook for one species."""
    species = species.upper()
    if species not in _SPECIES_PROFILE:
        raise HTTPException(status_code=400, detail=f"Unknown species '{species}'")

    start_d = date.fromisoformat(start) if start else date.today()
    weeks   = []
    for w in range(4):
        week_prices = []
        week_festivals = []
        for d_off in range(7):
            fd = start_d + timedelta(days=w * 7 + d_off)
            fb, fn, _ = _festival_boost_for_date(fd)
            week_prices.append(_predict_price(species, fd.month, festival_boost=fb))
            if fn:
                week_festivals.append(fn)
        avg   = round(sum(week_prices) / len(week_prices), 1)
        first = week_prices[0]
        last  = week_prices[-1]
        wow   = round((last - first) / max(first, 1) * 100, 2)
        trend = _trend_label(wow * 1.5)
        # Confidence derived from model prediction spread for that week
        spread = max(week_prices) - min(week_prices)
        conf   = max(0.55, min(0.97, 1.0 - spread / max(avg, 1)))

        weeks.append({
            "week":       f"W{w+1}",
            "start_date": (start_d + timedelta(days=w * 7)).isoformat(),
            "avg_price":  avg,
            "min_price":  min(week_prices),
            "max_price":  max(week_prices),
            "trend":      trend,
            "confidence": round(conf, 3),
            "intensity":  round(wow * 3),   # -100 to +100 gauge
            "festivals":  list(dict.fromkeys(week_festivals)),  # unique festival names in this week
            "daily":      [
                {
                    "day":   (start_d + timedelta(days=w * 7 + j)).strftime("%a"),
                    "price": wp,
                    "index": round(wp / max(first, 1) * 100, 1),
                }
                for j, wp in enumerate(week_prices)
            ],
        })

    return {"species": species, "weeks": weeks}


@router.get("/seasonal")
def seasonal_analysis(
    species: str = Query("YFT"),
    year:    int = Query(2026),
):
    """Full 12-month seasonal price analysis for radar / trend charts."""
    species = species.upper()
    if species not in _SPECIES_PROFILE:
        raise HTTPException(status_code=400, detail=f"Unknown species '{species}'")

    month_labels = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    seasonal = []
    for m in range(1, 13):
        # Use the 15th of each month as a representative date for festival-aware prediction
        rep_date = date(year, m, 15)
        price    = _predict_for_date(species, rep_date)
        seasonal.append({
            "month":   month_labels[m - 1],
            "month_n": m,
            "price":   price,
            "monsoon": _get_monsoon_name(m),
        })

    avg_price = sum(p["price"] for p in seasonal) / 12
    peak      = max(seasonal, key=lambda x: x["price"])
    trough    = min(seasonal, key=lambda x: x["price"])

    return {
        "species":    species,
        "year":       year,
        "monthly":    seasonal,
        "avg_price":  round(avg_price, 1),
        "peak_month": peak["month"],
        "peak_price": peak["price"],
        "trough_month": trough["month"],
        "trough_price": trough["price"],
        "seasonal_range": round(peak["price"] - trough["price"], 1),
    }


@router.get("/feature-importance")
def feature_importance():
    """Return feature importance from the XGB sub-model."""
    if _MODEL is None:
        return {"features": [
            {"feature": "Seasonal Demand",    "importance": 0.44},
            {"feature": "Export Premium",     "importance": 0.25},
            {"feature": "Market Pressure",    "importance": 0.20},
            {"feature": "Supply Surplus",     "importance": 0.04},
            {"feature": "Species Profile",    "importance": 0.04},
            {"feature": "Weather Factor",     "importance": 0.02},
            {"feature": "Local Demand",       "importance": 0.01},
        ]}
    try:
        xgb = _MODEL.named_estimators_["xgb"]
        imp = xgb.feature_importances_

        feature_labels = [
            "Species (YFT)", "Species (BET)", "Species (SKJ)", "Species (COM)",
            "Species (SWO)", "Species (MAHI)", "Species (BUM)", "Monsoon Active",
            "Month", "Catch Volume", "Export Demand", "Local Demand",
            "Market Pressure", "Seasonal Premium", "Export Premium",
            "Supply Surplus", "Weather Factor", "Trend Momentum",
        ]
        pairs = sorted(zip(feature_labels, imp.tolist()), key=lambda x: -x[1])
        return {"features": [{"feature": k, "importance": round(v, 4)} for k, v in pairs[:10]]}
    except Exception as e:
        return {"features": [], "error": str(e)}


@router.get("/festivals")
def upcoming_festivals(
    lookahead: int = Query(60, ge=7, le=180, description="Days to look ahead"),
):
    """
    Return upcoming Sri Lanka public holidays with ML-calculated price impact.
    Price impact is computed by comparing model output with vs without festival boost for YFT.
    """
    today = date.today()
    holidays = _fetch_lk_holidays(today.year)
    if today.month >= 11:
        holidays = holidays + _fetch_lk_holidays(today.year + 1)

    upcoming = []
    seen_names: set[str] = set()
    for h in sorted(holidays, key=lambda x: x.get("date", "")):
        try:
            hd = date.fromisoformat(h["date"])
        except Exception:
            continue
        delta = (hd - today).days
        if -7 <= delta <= lookahead:
            name = h.get("localName") or h.get("name", "Holiday")
            # Deduplicate adjacent entries with same name
            if name in seen_names:
                continue
            seen_names.add(name)

            # Compute ML price impact: YFT price with festival boost vs without
            boost, _, _ = _festival_boost_for_date(hd)
            price_with    = _predict_price("YFT", hd.month, festival_boost=boost)
            price_without = _predict_price("YFT", hd.month, festival_boost=0.0)
            pct_impact    = round((price_with - price_without) / max(price_without, 1) * 100, 2)

            upcoming.append({
                "date":             hd.isoformat(),
                "name":             name,
                "days_until":       delta,
                "is_past":          delta < 0,
                "festival_boost":   round(boost, 2),
                "price_impact_pct": pct_impact,   # ML-computed % uplift for YFT
                "monsoon":          _get_monsoon_name(hd.month),
            })

    return {
        "today":     today.isoformat(),
        "lookahead": lookahead,
        "festivals": upcoming,
    }
