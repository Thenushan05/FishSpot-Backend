"""Speed test — measures end-to-end prediction time for 5 cells."""
import sys, time
sys.path.insert(0, '.')

from app.services.enhanced_hotspot_service import EnhancedHotspotService

svc = EnhancedHotspotService()
cells = [{'lat': 7.5 + i * 0.05, 'lon': 81.5 + i * 0.05} for i in range(5)]

t0 = time.time()
res = svc.predict_with_weather_data(cells, species='YFT')
elapsed = time.time() - t0

print(f"\n{'='*50}")
print(f"⏱  Total: {elapsed:.1f}s  ({len(res)} cells)")
for r in res:
    print(f"  lat={r['LAT']:.2f} lon={r['LON']:.2f}  score={r.get('score',0):.3f}  {r.get('hotspot_level')}")
print('='*50)
