#!/usr/bin/env python3
"""
Test script for weather API integration with fuel consumption calculations.
Tests the Open-Meteo weather API functionality.
"""

import asyncio
import aiohttp
import json
from typing import Dict, Any

# Test locations around Sri Lanka
TEST_LOCATIONS = [
    {"name": "Colombo Harbor", "lat": 6.9271, "lng": 79.8612},
    {"name": "Galle", "lat": 6.0535, "lng": 80.2210},
    {"name": "Trincomalee", "lat": 8.5874, "lng": 81.2152},
    {"name": "Negombo", "lat": 7.2008, "lng": 79.8737},
    {"name": "Offshore East", "lat": 7.5, "lng": 82.0},  # Offshore location
]

class WeatherAPITest:
    def __init__(self):
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def test_open_meteo_weather(self, lat: float, lng: float) -> Dict[str, Any]:
        """Test regular Open-Meteo weather API"""
        print(f"\\n🌤️  Testing Weather API for {lat}, {lng}")
        
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lng,
            "current_weather": "true",
            "hourly": "wind_speed_10m,wind_direction_10m,windgusts_10m,precipitation,precipitation_probability,weathercode,visibility",
            "timezone": "UTC"
        }

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    current = data.get("current_weather", {})
                    hourly = data.get("hourly", {})
                    
                    result = {
                        "wind_speed": current.get("windspeed", 0),
                        "wind_direction": current.get("winddirection", 0),
                        "temperature": current.get("temperature", 0),
                        "weather_code": current.get("weathercode", 0),
                        "wind_gusts": hourly.get("windgusts_10m", [0])[0] if hourly.get("windgusts_10m") else 0,
                        "visibility": hourly.get("visibility", [10000])[0] if hourly.get("visibility") else 10000,
                        "precipitation": hourly.get("precipitation", [0])[0] if hourly.get("precipitation") else 0
                    }
                    
                    print(f"✅ Weather data retrieved:")
                    print(f"   Wind: {result['wind_speed']:.1f} m/s @ {result['wind_direction']:.0f}°")
                    print(f"   Gusts: {result['wind_gusts']:.1f} m/s")
                    print(f"   Visibility: {result['visibility']/1000:.1f} km")
                    print(f"   Temperature: {result['temperature']:.1f}°C")
                    
                    return result
                else:
                    print(f"❌ Weather API failed: {response.status}")
                    return {}
                    
        except Exception as e:
            print(f"❌ Weather API error: {e}")
            return {}

    async def test_open_meteo_marine(self, lat: float, lng: float) -> Dict[str, Any]:
        """Test Open-Meteo marine API"""
        print(f"\\n🌊 Testing Marine API for {lat}, {lng}")
        
        url = "https://marine-api.open-meteo.com/v1/marine"
        params = {
            "latitude": lat,
            "longitude": lng,
            "hourly": "wave_height,wave_direction,wind_speed_10m,sea_surface_temperature",
            "timezone": "UTC"
        }

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    hourly = data.get("hourly", {})
                    
                    # Get current hour data (first entry)
                    result = {
                        "wave_height": hourly.get("wave_height", [0])[0] if hourly.get("wave_height") else 0,
                        "wave_direction": hourly.get("wave_direction", [0])[0] if hourly.get("wave_direction") else 0,
                        "wind_speed": hourly.get("wind_speed_10m", [0])[0] if hourly.get("wind_speed_10m") else 0,
                        "sea_temperature": hourly.get("sea_surface_temperature", [0])[0] if hourly.get("sea_surface_temperature") else 0
                    }
                    
                    print(f"✅ Marine data retrieved:")
                    print(f"   Wave Height: {result['wave_height']:.1f} m")
                    print(f"   Wave Direction: {result['wave_direction']:.0f}°")
                    print(f"   Marine Wind: {result['wind_speed']:.1f} m/s")
                    print(f"   Sea Temp: {result['sea_temperature']:.1f}°C")
                    
                    return result
                else:
                    print(f"❌ Marine API failed: {response.status}")
                    return {}
                    
        except Exception as e:
            print(f"❌ Marine API error: {e}")
            return {}

    def determine_sea_condition(self, wind_speed: float, wave_height: float) -> Dict[str, Any]:
        """Determine sea condition based on weather data"""
        print(f"\\n📊 Analyzing Sea Conditions...")
        print(f"   Wind Speed: {wind_speed:.1f} m/s ({wind_speed * 1.94384:.1f} knots)")
        print(f"   Wave Height: {wave_height:.1f} m ({wave_height * 3.28084:.1f} feet)")
        
        # Determine condition
        if wind_speed >= 10.8 or wave_height >= 2.5:
            condition = "rough"
            fuel_multiplier = 1.35
            speed_multiplier = 0.65
            safety = "high"
            description = "Dangerous conditions - strong winds and/or high waves"
        elif wind_speed >= 5.5 or wave_height >= 1.0:
            condition = "choppy" 
            fuel_multiplier = 1.18
            speed_multiplier = 0.82
            safety = "medium"
            description = "Moderate conditions - use caution"
        else:
            condition = "calm"
            fuel_multiplier = 1.0
            speed_multiplier = 1.0
            safety = "low"
            description = "Ideal conditions for fishing"

        result = {
            "condition": condition,
            "fuel_multiplier": fuel_multiplier,
            "speed_multiplier": speed_multiplier,
            "safety_level": safety,
            "description": description,
            "wind_speed": wind_speed,
            "wave_height": wave_height
        }
        
        print(f"   Sea Condition: {condition.upper()}")
        print(f"   Fuel Impact: +{((fuel_multiplier - 1) * 100):.0f}%")
        print(f"   Speed Impact: {((1 - speed_multiplier) * 100):.0f}% reduction")
        print(f"   Safety Level: {safety}")
        print(f"   {description}")
        
        return result

    async def test_location(self, location: Dict[str, Any]) -> Dict[str, Any]:
        """Test weather APIs for a specific location"""
        print("\\n" + "="*60)
        print(f"🏝️  TESTING: {location['name']}")
        print("="*60)
        
        # Get weather and marine data
        weather_data = await self.test_open_meteo_weather(location["lat"], location["lng"])
        marine_data = await self.test_open_meteo_marine(location["lat"], location["lng"])
        
        # Combine data - prefer marine wind data for marine operations
        wind_speed = marine_data.get("wind_speed", weather_data.get("wind_speed", 0))
        wave_height = marine_data.get("wave_height", 0)
        
        # Determine sea conditions
        sea_condition = self.determine_sea_condition(wind_speed, wave_height)
        
        return {
            "location": location,
            "weather": weather_data,
            "marine": marine_data,
            "sea_condition": sea_condition
        }

    async def test_fuel_impact(self, base_fuel: float, conditions: Dict[str, Any]):
        """Test fuel consumption impact of weather conditions"""
        print(f"\\n⛽ Fuel Impact Analysis (Base: {base_fuel:.1f}L)")
        
        multiplier = conditions["fuel_multiplier"]
        adjusted_fuel = base_fuel * multiplier
        additional_fuel = adjusted_fuel - base_fuel
        
        print(f"   Adjusted Fuel: {adjusted_fuel:.1f}L")
        print(f"   Additional: +{additional_fuel:.1f}L (+{((multiplier-1)*100):.0f}%)")
        print(f"   Cost Impact: ${additional_fuel * 1.3:.2f} (@ $1.30/L)")
        
        return {
            "base_fuel": base_fuel,
            "adjusted_fuel": adjusted_fuel,
            "additional_fuel": additional_fuel,
            "fuel_multiplier": multiplier,
            "cost_impact": additional_fuel * 1.3
        }

    async def run_comprehensive_test(self):
        """Run comprehensive weather API test"""
        print("="*80)
        print("🌊 OPEN-METEO WEATHER API INTEGRATION TEST")
        print("="*80)
        
        all_results = []
        
        for location in TEST_LOCATIONS:
            try:
                result = await self.test_location(location)
                all_results.append(result)
                
                # Test fuel impact with example fuel consumption
                if result["sea_condition"]:
                    await self.test_fuel_impact(50.0, result["sea_condition"])
                    
            except Exception as e:
                print(f"❌ Failed to test {location['name']}: {e}")
                
            # Small delay between requests to be nice to the API
            await asyncio.sleep(0.5)
        
        # Summary
        print("\\n" + "="*80)
        print("📊 SUMMARY")
        print("="*80)
        
        conditions_count = {"calm": 0, "choppy": 0, "rough": 0}
        avg_wind = 0
        avg_waves = 0
        valid_results = 0
        
        for result in all_results:
            if result.get("sea_condition"):
                condition = result["sea_condition"]["condition"]
                conditions_count[condition] += 1
                avg_wind += result["sea_condition"]["wind_speed"]
                avg_waves += result["sea_condition"]["wave_height"]
                valid_results += 1
                
                print(f"{result['location']['name']:15} | "
                      f"{condition:6} | "
                      f"{result['sea_condition']['wind_speed']:4.1f}m/s | "
                      f"{result['sea_condition']['wave_height']:4.1f}m | "
                      f"+{((result['sea_condition']['fuel_multiplier']-1)*100):2.0f}%")
        
        if valid_results > 0:
            print(f"\\nAverage Wind Speed: {avg_wind/valid_results:.1f} m/s")
            print(f"Average Wave Height: {avg_waves/valid_results:.1f} m")
            print(f"\\nConditions Distribution:")
            for condition, count in conditions_count.items():
                percentage = (count / valid_results) * 100
                print(f"  {condition.capitalize()}: {count}/{valid_results} ({percentage:.0f}%)")
        
        # Save results
        with open("weather_api_test_results.json", "w") as f:
            json.dump(all_results, f, indent=2, default=str)
            
        print(f"\\n📄 Detailed results saved to: weather_api_test_results.json")
        print("\\n✅ Weather API integration test completed!")
        
        return all_results

async def main():
    """Main test function"""
    print("Starting Open-Meteo Weather API Integration Test...")
    
    try:
        async with WeatherAPITest() as tester:
            results = await tester.run_comprehensive_test()
            
        print(f"\\n🎉 Successfully tested {len(results)} locations")
        
    except KeyboardInterrupt:
        print("\\n⏹️ Test interrupted by user")
    except Exception as e:
        print(f"\\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())