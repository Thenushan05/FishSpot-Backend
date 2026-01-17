# Fuel Consumption API Usage

The fuel consumption API provides endpoints to calculate fuel requirements for vessel trips based on coordinates.

## Available Endpoints

### 1. Calculate Fuel Consumption
**POST** `/api/v1/fuel/calculate-fuel-consumption`

Request body:
```json
{
  "start_lat": 6.9,
  "start_lon": 79.8,
  "end_lat": 7.2,
  "end_lon": 80.1,
  "vessel_id": "V0001"  // Optional - uses average vessel if not provided
}
```

Response:
```json
{
  "distance_km": 47.0,
  "estimated_trip_duration_hours": 2.14,
  "fuel_consumption_liters": 6.23,
  "vessel_used": "V0001",
  "fuel_cost_usd": 8.19
}
```

### 2. List All Vessels
**GET** `/api/v1/fuel/vessels`

Response:
```json
{
  "vessels": [
    {
      "vessel_id": "V0001",
      "vessel_type": "IMUL",
      "engine_type": "Inboard Diesel",
      "hp": 51.8,
      "fuel_consumption_per_day": 178.2,
      "fuel_cost_usd_per_day": 231.61
    }
  ],
  "total_count": 100
}
```

### 3. Get Specific Vessel Details
**GET** `/api/v1/fuel/vessels/{vessel_id}`

Response:
```json
{
  "vessel_id": "V0001",
  "fuel_consumption": 178.2,
  "fuel_cost_usd_per_day": 231.61,
  "hp": 51.8,
  "vessel_type": "IMUL",
  "engine_type": "Inboard Diesel"
}
```

## Integration with Frontend (Hotspot Map)

To integrate this with your hotspot map frontend:

1. **Get coordinates from map clicks/selection**:
   ```javascript
   const startCoords = { lat: startLatitude, lon: startLongitude };
   const endCoords = { lat: endLatitude, lon: endLongitude };
   ```

2. **Make API call to calculate fuel**:
   ```javascript
   const calculateFuelConsumption = async (startLat, startLon, endLat, endLon, vesselId = null) => {
     const response = await fetch('http://localhost:8000/api/v1/fuel/calculate-fuel-consumption', {
       method: 'POST',
       headers: { 'Content-Type': 'application/json' },
       body: JSON.stringify({
         start_lat: startLat,
         start_lon: startLon,
         end_lat: endLat,
         end_lon: endLon,
         vessel_id: vesselId
       })
     });
     
     return await response.json();
   };
   ```

3. **Display results in UI**:
   ```javascript
   const result = await calculateFuelConsumption(6.9, 79.8, 7.2, 80.1);
   console.log(`Trip distance: ${result.distance_km} km`);
   console.log(`Fuel needed: ${result.fuel_consumption_liters} liters`);
   console.log(`Estimated cost: $${result.fuel_cost_usd}`);
   console.log(`Trip duration: ${result.estimated_trip_duration_hours} hours`);
   ```

## Calculation Details

- **Distance**: Calculated using the Haversine formula for great-circle distance
- **Speed**: Assumes 12 knots (~22 km/h) average vessel speed
- **Fuel Consumption**: Based on vessel data from `vessels.csv` (liters per day)
- **Duration**: Distance ÷ Speed
- **Fuel Required**: (Fuel per day ÷ 24) × Trip hours

## Data Source

Vessel data is loaded from `/data/vessel/vessels.csv` containing:
- 100+ vessel records from Sri Lanka Fisheries Department
- Fuel consumption rates (liters/day)
- Engine specifications (HP, type)
- Cost estimates (USD/day)

## Testing Examples

```bash
# Test with Python requests
python -c "
import requests, json
data = {'start_lat': 6.9, 'start_lon': 79.8, 'end_lat': 7.2, 'end_lon': 80.1}
r = requests.post('http://127.0.0.1:8000/api/v1/fuel/calculate-fuel-consumption', json=data)
print(json.dumps(r.json(), indent=2))
"

# Test with curl
curl -X POST http://127.0.0.1:8000/api/v1/fuel/calculate-fuel-consumption \
  -H "Content-Type: application/json" \
  -d '{"start_lat": 6.9, "start_lon": 79.8, "end_lat": 7.2, "end_lon": 80.1}'
```