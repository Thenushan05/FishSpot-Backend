"""Quick test: what scores does the local-ground model produce for different inputs?"""
import math, warnings, datetime
import joblib, pandas as pd
from pathlib import Path

MODEL_PATH = Path("app/ml/localground/xgb_model.joblib")
with warnings.catch_warnings():
    warnings.filterwarnings("ignore")
    model = joblib.load(MODEL_PATH)

now = datetime.datetime.now(datetime.timezone.utc)
doy = now.timetuple().tm_yday
month = now.month

base = {
    "wind_speed": 5.0,
    "pressure": 1010.0,
    "precip": 0.0,
    "day_of_year_sin": math.sin(2 * math.pi * doy / 365),
    "day_of_year_cos": math.cos(2 * math.pi * doy / 365),
    "month_sin": math.sin(2 * math.pi * month / 12),
    "month_cos": math.cos(2 * math.pi * month / 12),
}

cols = ["wind_speed","pressure","precip","day_of_year_sin","day_of_year_cos","month_sin","month_cos","lstm_pred_kg"]

print(f"Date: {now.date()}  DOY={doy}  Month={month}")
doy_sin = base["day_of_year_sin"]
doy_cos = base["day_of_year_cos"]
m_sin   = base["month_sin"]
m_cos   = base["month_cos"]
print(f"  day_of_year_sin={doy_sin:.4f}  day_of_year_cos={doy_cos:.4f}")
print(f"  month_sin={m_sin:.4f}  month_cos={m_cos:.4f}")
print()
print(f"{'total_kg':>12} | {'score %':>8} | {'level':>10}")
print("-" * 38)
for kg in [0, 10, 50, 100, 200, 350, 500, 750, 1000, 1500, 2000, 3000]:
    row = {**base, "lstm_pred_kg": float(kg)}
    X = pd.DataFrame([row])[cols]
    p = float(model.predict_proba(X)[0, 1])
    level = "High" if p >= 0.7 else "Moderate" if p >= 0.4 else "Low"
    print(f"{kg:>12} kg | {round(p*100,1):>7}% | {level:>10}")

print()
print("--- Same kg=350, different lat/lng (weather fetched per-location but 0% importance) ---")
for lat, lng, label in [(8.3, 81.2, "Trinco"), (6.9, 79.8, "Colombo"), (9.6, 80.1, "Jaffna"), (5.9, 80.5, "Galle")]:
    row = {**base, "lstm_pred_kg": 350.0}
    X = pd.DataFrame([row])[cols]
    p = float(model.predict_proba(X)[0, 1])
    print(f"  {label:10s} ({lat},{lng}) -> {round(p*100,1)}%  (weather ignored by model)")

print()
print("--- Effect of wind on score (should be zero) ---")
for wind in [0, 5, 10, 15, 20]:
    row = {**base, "wind_speed": float(wind), "lstm_pred_kg": 350.0}
    X = pd.DataFrame([row])[cols]
    p = float(model.predict_proba(X)[0, 1])
    print(f"  wind={wind:>3} m/s -> {round(p*100,1)}%")
