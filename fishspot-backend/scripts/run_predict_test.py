import json
from app.services.predict import predict_hotspots_region

# Sample bbox near Sri Lanka for a quick test
bbox = (7.5, 8.0, 79.5, 80.0)  # min_lat, max_lat, min_lon, max_lon
res = predict_hotspots_region(
    date='20251127',
    species_code='YFT',
    threshold=0.6,
    top_k=20,
    bbox=bbox,
    overrides={'sst': 28.0, 'ssh': 0.05, 'sss': 35.0}
)

print(json.dumps(res['summary'], indent=2))
print('\nTotal Cells:', res['summary']['total_cells'])
print('Hotspot Count:', res['summary']['hotspot_count'])

# Print up to 5 hotspot features
features = res.get('geojson', {}).get('features', [])
if features:
    print('\nSample features:')
    print(json.dumps(features[:5], indent=2))
else:
    print('\nNo hotspot features returned')
