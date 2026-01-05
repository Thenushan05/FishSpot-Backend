#!/usr/bin/env python3
import json
from app.services.inputs_service import build_region_inputs

if __name__ == '__main__':
    bbox = (54.544, 54.61, 10.2, 10.4)
    date = None
    species = 'YFT'
    rows = build_region_inputs(date=date, bbox=bbox, species=species)
    print(json.dumps({'date': date, 'species': species, 'bbox': bbox, 'inputs_count': len(rows), 'sample': rows[:10]}, indent=2))
