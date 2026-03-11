"""
Quick test for the local-ground XGBoost model.
Run: python test_local_ground.py
"""
import math
import warnings
import pandas as pd
import joblib
from datetime import datetime, timezone
from pathlib import Path

warnings.filterwarnings("ignore")

MODEL_PATH = Path("app/ml/localground/xgb_model.joblib")
model = joblib.load(MODEL_PATH)
print(f"[OK] Model loaded from {MODEL_PATH}")
print(f"     Features: {model.feature_names_in_.tolist()}\n")

FEATURE_COLS = [
    "wind_speed", "pressure", "precip",
    "day_of_year_sin", "day_of_year_cos",
    "month_sin", "month_cos", "lstm_pred_kg",
]

now = datetime.now(timezone.utc)
doy = now.timetuple().tm_yday
month = now.month
date_feats = {
    "day_of_year_sin": math.sin(2 * math.pi * doy / 365),
    "day_of_year_cos": math.cos(2 * math.pi * doy / 365),
    "month_sin":       math.sin(2 * math.pi * month / 12),
    "month_cos":       math.cos(2 * math.pi * month / 12),
}

# Simulated Open-Meteo weather + total_kg_latest per ground
test_cases = [
    {"name": "Colombo Bank",     "lat": 6.85, "lng": 79.75, "wind": 5.2,  "pressure": 1010.5, "precip": 0.0,  "total_kg": 80.0},
    {"name": "Trincomalee",      "lat": 8.65, "lng": 81.60, "wind": 7.1,  "pressure": 1008.2, "precip": 0.3,  "total_kg": 320.0},
    {"name": "Jaffna Bank",      "lat": 9.90, "lng": 80.10, "wind": 9.5,  "pressure": 1006.0, "precip": 1.2,  "total_kg": 950.0},
    {"name": "Mirissa Point",    "lat": 5.92, "lng": 80.62, "wind": 3.8,  "pressure": 1013.0, "precip": 0.0,  "total_kg": 50.0},
    {"name": "Mannar Bank",      "lat": 8.85, "lng": 79.40, "wind": 6.3,  "pressure": 1009.0, "precip": 0.0,  "total_kg": 500.0},
    {"name": "Negombo Bank",     "lat": 7.35, "lng": 79.75, "wind": 4.9,  "pressure": 1011.0, "precip": 0.0,  "total_kg": 200.0},
    {"name": "Batticaloa Bank",  "lat": 7.80, "lng": 81.85, "wind": 8.2,  "pressure": 1007.5, "precip": 0.5,  "total_kg": 750.0},
    {"name": "Beruwala Grounds", "lat": 6.48, "lng": 79.92, "wind": 4.5,  "pressure": 1012.0, "precip": 0.0,  "total_kg": 120.0},
]

print(f"Date: {now.date()}   DOY: {doy}   Month: {month}")
print("=" * 82)
print(f"{'Spot':<22}  {'Wind':>5}  {'Press':>8}  {'Prec':>5}  {'TotalKg':>8}  |  {'Score':>6}  {'Level'}")
print("-" * 82)

for tc in test_cases:
    print(
        f"[Weather] {tc['name']:<18}  "
        f"wind={tc['wind']} m/s  pressure={tc['pressure']} hPa  "
        f"precip={tc['precip']} mm  total_kg_latest={tc['total_kg']} kg"
    )
    row = {
        "wind_speed":      tc["wind"],
        "pressure":        tc["pressure"],
        "precip":          tc["precip"],
        "lstm_pred_kg":    tc["total_kg"],   # fallback: total_kg_latest → lstm_pred_kg
        **date_feats,
    }
    X = pd.DataFrame([row])[FEATURE_COLS]
    p = float(model.predict_proba(X)[0, 1])
    level = "High" if p >= 0.7 else "Moderate" if p >= 0.4 else "Low"
    print(
        f"  -> {tc['name']:<22}  "
        f"{tc['wind']:>5.1f}  {tc['pressure']:>8.1f}  {tc['precip']:>5.1f}  "
        f"{tc['total_kg']:>8.1f}  |  {round(p*100,1):>5.1f}%  {level}"
    )
    print()

print("=" * 82)

# Show sensitivity of score to total_kg_latest
print("\n--- Sensitivity: total_kg_latest → score (Colombo Bank weather) ---")
base = {"wind_speed": 5.2, "pressure": 1010.5, "precip": 0.0, **date_feats}
for kg in [0, 10, 50, 100, 200, 500, 1000, 2000, 5000]:
    row = {**base, "lstm_pred_kg": float(kg)}
    X = pd.DataFrame([row])[FEATURE_COLS]
    p = float(model.predict_proba(X)[0, 1])
    bar = "#" * int(p * 40)
    print(f"  total_kg={kg:<5}  ->  {round(p*100,1):>5.1f}%  {bar}")

print("\nFeature importances:")
imp = dict(zip(model.feature_names_in_, model.feature_importances_))
for k in sorted(imp, key=imp.get, reverse=True):
    bar = "#" * int(imp[k] * 60)
    print(f"  {k:<22}  {imp[k]:.4f}  {bar}")

