import requests
import json

print('Testing fuel calculation API with vessel V0010:')

data = {
    'start_lat': 6.0, 
    'start_lon': 80.0, 
    'end_lat': 6.5, 
    'end_lon': 81.0, 
    'vessel_id': 'V0010'
}

try:
    r = requests.post('http://127.0.0.1:8000/api/v1/fuel/calculate-fuel-consumption', json=data)
    if r.status_code == 200:
        result = r.json()
        print(f"✅ Success!")
        print(f"Distance: {result['distance_km']} km")
        print(f"Fuel needed: {result['fuel_consumption_liters']} liters")
        print(f"Cost: ${result['fuel_cost_usd']}")
        print(f"Duration: {result['estimated_trip_duration_hours']} hours")
        print(f"Vessel used: {result['vessel_used']}")
    else:
        print(f"❌ Error: HTTP {r.status_code}")
        print(r.text)
except Exception as e:
    print(f"❌ Connection error: {e}")