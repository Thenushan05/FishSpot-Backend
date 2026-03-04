import urllib.request, json, pickle, numpy as np

def get(path):
    with urllib.request.urlopen("http://localhost:8000" + path, timeout=8) as r:
        return json.loads(r.read())

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        "http://localhost:8000" + path, data=data,
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read())

print("=== TEST 1: model_used flag ===")
p = post("/api/v1/market/predict", {"species": "YFT"})
print("  model_used:", p["model_used"])

print()
print("=== TEST 2: different species return different prices ===")
s = get("/api/v1/market/summary")
for sp in s["species"]:
    code  = sp["code"]
    wow   = sp["wow_pct"]
    price = sp["price"]
    print(f"  {code:6s}  price={price}  wow={wow:+.2f}%")

print()
print("=== TEST 3: festival month raises price (model input changes) ===")
p_mar = post("/api/v1/market/predict", {"species": "YFT", "date": "2026-03-04"})
p_apr = post("/api/v1/market/predict", {"species": "YFT", "date": "2026-04-14"})
p_jun = post("/api/v1/market/predict", {"species": "YFT", "date": "2026-06-01"})
print(f"  YFT 2026-03-04  price={p_mar['today_price']}  festival={p_mar['festival_name']!r}")
print(f"  YFT 2026-04-14  price={p_apr['today_price']}  festival={p_apr['festival_name']!r}")
print(f"  YFT 2026-06-01  price={p_jun['today_price']}  festival={p_jun['festival_name']!r}")

print()
print("=== TEST 4: direct pkl predict vs API (YFT March, no festival) ===")
model = pickle.load(open("app/ml/market/ensemble_voting_balanced.pkl", "rb"))
# March YFT baseline vector matching _build_feature_vector(YFT, month=3, festival_boost=0)
vec = np.zeros(18)
vec[0]  = 1      # species_YFT
vec[7]  = 0      # monsoon_active (March = dry)
vec[8]  = 3      # month
vec[9]  = 5      # catch_vol (med profile)
vec[10] = 25     # export_demand
vec[11] = 10     # local_demand
vec[12] = 157    # market_pressure (base 130 + monthly_delta no festival)
vec[13] = 2      # seasonal_premium
vec[14] = 37.5   # export_premium
vec[15] = 25.4   # supply_surplus
vec[16] = 2      # weather_factor
vec[17] = 23.55  # trend_momentum
direct = round(float(model.predict(vec.reshape(1, -1))[0]), 1)
api_val = p_mar["today_price"]
print(f"  Direct pkl.predict(): {direct}")
print(f"  API today_price:      {api_val}")

print()
print("=== TEST 5: feature importance from model internals ===")
xgb_est = model.estimators_[0]
names = ["YFT","BET","SKJ","ALB","SWO","KGS","LOC","monsoon","month",
         "catch_vol","export_demand","local_demand","market_pressure",
         "seasonal_premium","export_premium","supply_surplus","weather_factor","trend_momentum"]
fi = xgb_est.feature_importances_
top = sorted(zip(names, fi), key=lambda x: -x[1])[:5]
print("  Top-5 XGB feature importances (from real model):")
for name, imp in top:
    print(f"    {name:20s} {imp:.4f}")
