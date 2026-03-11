"""
Test Open-Meteo API: verify wind_speed, pressure, precipitation are fetched.
Run: python test_weather_fetch.py
"""
import httpx
import asyncio
import json

SPOTS = [
    ("Colombo Bank",     6.85,  79.75),
    ("Trincomalee",      8.65,  81.60),
    ("Jaffna Bank",      9.90,  80.10),
    ("Mirissa Point",    5.92,  80.62),
    ("Mannar Bank",      8.85,  79.40),
]

BASE_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lng}"
    "&current=wind_speed_10m,surface_pressure,precipitation"
    "&wind_speed_unit=ms"
)

async def main():
    print("=" * 65)
    print(f"{'Spot':<20} {'Wind m/s':>10} {'Press hPa':>11} {'Precip mm':>11}")
    print("-" * 65)

    async with httpx.AsyncClient(timeout=15.0) as client:
        for name, lat, lng in SPOTS:
            url = BASE_URL.format(lat=lat, lng=lng)
            resp = await client.get(url)
            resp.raise_for_status()
            c = resp.json().get("current", {})

            ws = c.get("wind_speed_10m",   "MISSING")
            pr = c.get("surface_pressure", "MISSING")
            pc = c.get("precipitation",    "MISSING")

            print(f"{name:<20} {str(ws):>10} {str(pr):>11} {str(pc):>11}")
            print(f"  [raw current keys]: {list(c.keys())}")

    print("=" * 65)

    # Full raw JSON for first spot
    print("\nFull raw JSON for Colombo Bank:")
    async with httpx.AsyncClient(timeout=15.0) as client:
        url = BASE_URL.format(lat=6.85, lng=79.75)
        resp = await client.get(url)
    print(json.dumps(resp.json(), indent=2))

asyncio.run(main())
