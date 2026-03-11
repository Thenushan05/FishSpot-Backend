import httpx
import asyncio
import json
from datetime import datetime, timezone

async def check():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=6.85&longitude=79.75"
        "&current=wind_speed_10m,wind_direction_10m,surface_pressure,precipitation,"
        "rain,showers,temperature_2m,relative_humidity_2m,weather_code"
        "&wind_speed_unit=ms"
        "&timezone=Asia/Colombo"
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
    data = resp.json()
    c = data["current"]
    units = data["current_units"]

    fetched_at = c["time"]
    utc_now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")

    print(f"Fetched at (Colombo local): {fetched_at}")
    print(f"UTC now                   : {utc_now}")
    print()
    print("--- Live Weather for Colombo Bank (6.85, 79.75) ---")
    for k, v in c.items():
        if k not in ("time", "interval"):
            unit = units.get(k, "")
            print(f"  {k:<32} = {v}  {unit}")

    wc = c.get("weather_code", 0)
    wmo_map = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        51: "Drizzle (light)", 53: "Drizzle (moderate)", 55: "Drizzle (dense)",
        61: "Rain (slight)", 63: "Rain (moderate)", 65: "Rain (heavy)",
        80: "Rain showers (slight)", 81: "Rain showers (moderate)", 82: "Rain showers (violent)",
        95: "Thunderstorm", 96: "Thunderstorm with hail",
    }
    print()
    print(f"  WMO weather_code {wc} => {wmo_map.get(wc, 'Unknown code ' + str(wc))}")
    print()

    # Verdict
    precip = float(c.get("precipitation", 0))
    rain   = float(c.get("rain", 0))
    shower = float(c.get("showers", 0))
    if precip == 0.0 and rain == 0.0 and shower == 0.0:
        print("VERDICT: precip=0.0 is REAL. No rain at this location right now.")
    else:
        print(f"VERDICT: Active precipitation! precip={precip}, rain={rain}, showers={shower}")

asyncio.run(check())
