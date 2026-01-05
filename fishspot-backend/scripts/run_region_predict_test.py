#!/usr/bin/env python3
import json
from app.services.predict import predict_hotspots_region

if __name__ == '__main__':
    from datetime import datetime
    bbox = (54.544, 54.61, 10.2, 10.4)
    date = datetime.utcnow().strftime("%Y%m%d")
    res = predict_hotspots_region(date=date, species_code='YFT', threshold=0.6, top_k=20, bbox=bbox)
    print(json.dumps(res, indent=2))
