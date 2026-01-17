#!/usr/bin/env python3
"""
Demo script to test the integrated Trip Planner functionality with backend APIs.
This script validates that the backend fuel consumption and maintenance APIs work correctly.
"""

import asyncio
import aiohttp
import json
from typing import List, Dict, Any

# Test configuration
BASE_URL = "http://localhost:8000"
DEMO_COORDINATES = [
    {"lat": 6.9271, "lng": 79.8612, "name": "Colombo Harbor"},  # Start
    {"lat": 6.0535, "lng": 80.2210, "name": "Galle Hotspot"},   # Hotspot 1
    {"lat": 8.5874, "lng": 81.2152, "name": "Trinco Hotspot"},  # Hotspot 2
    {"lat": 6.9271, "lng": 79.8612, "name": "Return to Colombo"}  # Return
]

class TripPlannerDemo:
    def __init__(self):
        self.session = None
        self.test_vessel_id = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def test_fuel_vessels_api(self) -> List[Dict[Any, Any]]:
        """Test the fuel vessels API endpoint"""
        print("\\n🚢 Testing Fuel Vessels API...")
        
        try:
            async with self.session.get(f"{BASE_URL}/api/v1/fuel/vessels") as response:
                if response.status == 200:
                    data = await response.json()
                    vessels = data.get("vessels", [])
                    print(f"✅ Found {len(vessels)} vessels")
                    
                    if vessels:
                        # Store first vessel for testing
                        self.test_vessel_id = vessels[0]["vessel_id"]
                        print(f"   Using test vessel: {self.test_vessel_id}")
                        
                        # Show vessel details
                        for i, vessel in enumerate(vessels[:3]):  # Show first 3
                            print(f"   {i+1}. {vessel['vessel_id']} - {vessel['vessel_type']} ({vessel['hp']}HP)")
                    
                    return vessels
                else:
                    print(f"❌ Fuel vessels API failed: {response.status}")
                    return []
                    
        except Exception as e:
            print(f"❌ Error testing fuel vessels API: {e}")
            return []

    async def test_single_fuel_calculation(self, start_coord: Dict, end_coord: Dict, vessel_id: str = None) -> Dict:
        """Test single fuel consumption calculation"""
        print(f"\\n⛽ Testing fuel calculation: {start_coord['name']} → {end_coord['name']}")
        
        payload = {
            "start_lat": start_coord["lat"],
            "start_lon": start_coord["lng"],
            "end_lat": end_coord["lat"],
            "end_lon": end_coord["lng"]
        }
        
        if vessel_id:
            payload["vessel_id"] = vessel_id
            
        try:
            async with self.session.post(
                f"{BASE_URL}/api/v1/fuel/calculate-fuel-consumption",
                json=payload
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ Calculation successful:")
                    print(f"   Distance: {result['distance_km']:.1f} km")
                    print(f"   Duration: {result['estimated_trip_duration_hours']:.1f} hours")
                    print(f"   Fuel: {result['fuel_consumption_liters']:.1f} liters")
                    print(f"   Cost: ${result['fuel_cost_usd']:.2f}")
                    print(f"   Vessel: {result['vessel_used']}")
                    return result
                else:
                    error_text = await response.text()
                    print(f"❌ Fuel calculation failed: {response.status} - {error_text}")
                    return {}
                    
        except Exception as e:
            print(f"❌ Error in fuel calculation: {e}")
            return {}

    async def test_full_trip_calculation(self, coordinates: List[Dict], vessel_id: str = None) -> Dict:
        """Test full trip calculation with multiple stops"""
        print("\\n🗺️  Testing full trip calculation...")
        
        total_distance = 0
        total_fuel = 0
        total_cost = 0
        total_duration = 0
        segments = []
        
        for i in range(len(coordinates) - 1):
            start = coordinates[i]
            end = coordinates[i + 1]
            
            result = await self.test_single_fuel_calculation(start, end, vessel_id)
            
            if result:
                segments.append(result)
                total_distance += result['distance_km']
                total_fuel += result['fuel_consumption_liters']
                total_cost += result['fuel_cost_usd']
                total_duration += result['estimated_trip_duration_hours']
            else:
                print(f"⚠️ Segment calculation failed: {start['name']} → {end['name']}")
                
        trip_summary = {
            "segments": segments,
            "totals": {
                "distance_km": total_distance,
                "fuel_consumption_liters": total_fuel,
                "fuel_cost_usd": total_cost,
                "estimated_trip_duration_hours": total_duration
            }
        }
        
        print("\\n📊 Trip Summary:")
        print(f"   Total Distance: {total_distance:.1f} km")
        print(f"   Total Duration: {total_duration:.1f} hours")
        print(f"   Total Fuel: {total_fuel:.1f} liters")
        print(f"   Total Cost: ${total_cost:.2f}")
        
        return trip_summary

    async def test_maintenance_api(self) -> List[Dict]:
        """Test the maintenance vessels API"""
        print("\\n🔧 Testing Maintenance Vessels API...")
        
        try:
            async with self.session.get(f"{BASE_URL}/api/v1/maintenance/vessels") as response:
                if response.status == 200:
                    data = await response.json()
                    vessels = data.get("vessels", [])
                    print(f"✅ Found {len(vessels)} maintenance vessels")
                    
                    for i, vessel in enumerate(vessels[:2]):  # Show first 2
                        print(f"   {i+1}. {vessel['name']} - {vessel['type']}")
                        print(f"      Systems: {len(vessel.get('systems', []))}")
                        
                        # Show system status
                        for system in vessel.get('systems', [])[:3]:
                            status_emoji = {
                                'operational': '✅',
                                'due-soon': '⚠️',
                                'overdue': '🔴',
                                'critical': '🚨',
                                'offline': '❌'
                            }.get(system.get('status', 'unknown'), '❓')
                            print(f"        {status_emoji} {system['name']}: {system.get('status', 'unknown')}")
                    
                    return vessels
                else:
                    print(f"❌ Maintenance API failed: {response.status}")
                    return []
                    
        except Exception as e:
            print(f"❌ Error testing maintenance API: {e}")
            return []

    async def simulate_weather_impact(self, base_fuel: float) -> Dict:
        """Simulate weather impact on fuel consumption"""
        print("\\n🌊 Testing Weather Impact Simulation...")
        
        weather_conditions = {
            "calm": {"multiplier": 1.0, "description": "Ideal conditions"},
            "choppy": {"multiplier": 1.15, "description": "Moderate seas"},
            "rough": {"multiplier": 1.3, "description": "Dangerous conditions"}
        }
        
        results = {}
        
        for condition, data in weather_conditions.items():
            adjusted_fuel = base_fuel * data["multiplier"]
            fuel_increase = adjusted_fuel - base_fuel
            
            results[condition] = {
                "base_fuel": base_fuel,
                "adjusted_fuel": adjusted_fuel,
                "additional_fuel": fuel_increase,
                "increase_percent": ((data["multiplier"] - 1) * 100),
                "description": data["description"]
            }
            
            print(f"   {condition.upper()}: {adjusted_fuel:.1f}L (+{fuel_increase:.1f}L, +{results[condition]['increase_percent']:.0f}%)")
            
        return results

    async def run_full_demo(self):
        """Run complete integration demo"""
        print("=" * 60)
        print("🎣 FISHSPOT TRIP PLANNER INTEGRATION DEMO")
        print("=" * 60)
        
        # Test fuel vessels API
        fuel_vessels = await self.test_fuel_vessels_api()
        
        # Test fuel calculation with vessel
        if fuel_vessels and self.test_vessel_id:
            trip_result = await self.test_full_trip_calculation(DEMO_COORDINATES, self.test_vessel_id)
        else:
            print("⚠️ No vessels found, testing without vessel ID...")
            trip_result = await self.test_full_trip_calculation(DEMO_COORDINATES)
        
        # Test maintenance API
        maintenance_vessels = await self.test_maintenance_api()
        
        # Simulate weather impact
        if trip_result and trip_result["totals"]["fuel_consumption_liters"] > 0:
            await self.simulate_weather_impact(trip_result["totals"]["fuel_consumption_liters"])
        
        print("\\n" + "=" * 60)
        print("✅ INTEGRATION DEMO COMPLETED!")
        print("=" * 60)
        
        return {
            "fuel_vessels": fuel_vessels,
            "trip_calculation": trip_result,
            "maintenance_vessels": maintenance_vessels
        }

async def main():
    """Main demo function"""
    print("Starting Trip Planner Integration Demo...")
    print("Make sure the FishSpot backend is running on http://localhost:8000")
    
    try:
        async with TripPlannerDemo() as demo:
            results = await demo.run_full_demo()
            
            # Save results to file for inspection
            with open("trip_planner_demo_results.json", "w") as f:
                json.dump(results, f, indent=2, default=str)
            
            print("\\n📄 Results saved to: trip_planner_demo_results.json")
            
    except KeyboardInterrupt:
        print("\\n⏹️ Demo interrupted by user")
    except Exception as e:
        print(f"\\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())