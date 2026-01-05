#!/usr/bin/env python3
"""
Run hotspot model predictions for a JSON of model inputs.

This script expects a JSON file produced earlier (e.g. from frontend) with rows like:
  {"year":2020,...,"sst":7.4,...}

It maps keys to the model's FEATURE_COLS and calls the backend model loader/predictor
`app.services.ml_hotspot.predict_cells` and writes predictions to `predictions_bbox.json`.
"""
from pathlib import Path
import json
import math

SRC_JSON = Path("D:/Fish-Full/fin-finder-grid/model_inputs_bbox.json")
OUT_JSON = Path(__file__).resolve().parents[0] / "predictions_bbox.json"

def month_sin(m):
    return math.sin(2 * math.pi * m / 12) if m is not None else None

def month_cos(m):
    return math.cos(2 * math.pi * m / 12) if m is not None else None

def load_inputs(path):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input JSON not found at {p} -- please generate model_inputs_bbox.json and retry")
    with open(p, 'r') as f:
        data = json.load(f)
    return data

def build_feature_rows(records):
    rows = []
    for r in records:
        year = r.get('year')
        month = r.get('month')
        depth = r.get('depth')
        row = {
            'YEAR': int(year) if year is not None else None,
            'MONTH': int(month) if month is not None else None,
            'LAT': float(r.get('lat')) if r.get('lat') is not None else None,
            'LON': float(r.get('lon')) if r.get('lon') is not None else None,
            'DEPTH': float(depth) if depth is not None else None,
            'SSS': float(r.get('sss')) if r.get('sss') is not None else None,
            'SSD': float(r.get('ssd')) if r.get('ssd') is not None else None,
            'SST': float(r.get('sst')) if r.get('sst') is not None else None,
            'SSH': float(r.get('ssh')) if r.get('ssh') is not None else None,
            'CHLO': float(r.get('chlo')) if r.get('chlo') is not None else None,
            'MONTH_SIN': month_sin(month) if month is not None else None,
            'MONTH_COS': month_cos(month) if month is not None else None,
            'DEPTH_ABS': abs(float(depth)) if depth is not None else None,
            'SPECIES_CODE': r.get('SPECIES_CODE') or r.get('SPECIES') or 'UNKNOWN',
            'MONSOON': r.get('monsoon') or r.get('MONSOON') or 'No_monsoon_region'
        }
        rows.append(row)
    return rows

def main():
    records = load_inputs(SRC_JSON)
    features = build_feature_rows(records)

    # Import the model predictor from the app package
    from app.services import ml_hotspot

    preds = ml_hotspot.predict_cells(features)

    with open(OUT_JSON, 'w') as f:
        json.dump(preds, f, indent=2)

    print(f"Wrote {len(preds)} predictions to {OUT_JSON}")

if __name__ == '__main__':
    main()
