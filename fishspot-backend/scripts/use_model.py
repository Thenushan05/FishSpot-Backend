"""Simple CLI to load a saved pipeline and produce hotspot probabilities.

Supports:
- Single-point prediction via CLI flags
- Batch prediction from an input CSV (will compute derived features if missing)

Examples:
  # single point
  python scripts/use_model.py --model models/xgb_classification_tuned.joblib \
    --year 2020 --month 1 --lat 7.5 --lon 82.0 --depth 30 --sss 35.0 --ssd 1025.0 \
    --sst 28.0 --ssh 0.1 --chlo 0.2 --SPECIES_CODE SPC123 --monsoon NE

  # batch mode (writes y_true if hotspot available, else only p_hotspot)
  python scripts/use_model.py --model models/xgb_classification_tuned.joblib \
    --in_csv data/processed/catch_env_2020_filtered.csv --out_csv eval_predictions_2020_quick.csv --max_rows 5

"""

import argparse
from pathlib import Path
import joblib
import pandas as pd
import numpy as np
import json


FEATURE_NUMERIC = [
    "year",
    "month",
    "lat",
    "lon",
    "depth",
    "sss",
    "ssd",
    "sst",
    "ssh",
    "chlo",
    "month_sin",
    "month_cos",
    "depth_abs",
]

FEATURE_CATEGORICAL = [
    "SPECIES_CODE",
    "monsoon",
]

ALL_FEATURES = FEATURE_NUMERIC + FEATURE_CATEGORICAL


def compute_derived(df: pd.DataFrame) -> pd.DataFrame:
    # month_sin/month_cos
    if "month" in df.columns and ("month_sin" not in df.columns or "month_cos" not in df.columns):
        df["month_sin"] = np.sin(2 * np.pi * df["month"] / 12)
        df["month_cos"] = np.cos(2 * np.pi * df["month"] / 12)

    if "depth" in df.columns and "depth_abs" not in df.columns:
        df["depth_abs"] = df["depth"].abs()

    # log_catchweight is only used for label generation in eval scripts; not required for prediction
    return df


def load_model(model_path: Path):
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    model = joblib.load(model_path)
    return model


def predict_df(model, df: pd.DataFrame) -> pd.DataFrame:
    # compute derived features
    df = compute_derived(df.copy())

    # Prepare a cleaned copy for the pipeline: ensure all features exist and have stable types
    X = df.copy()
    # add missing columns with sensible defaults
    missing = [c for c in ALL_FEATURES if c not in X.columns]
    if missing:
        for c in missing:
            if c in FEATURE_CATEGORICAL:
                X[c] = "missing"
            else:
                X[c] = np.nan

    # Coerce numeric features to numeric dtype (strings -> numbers when possible)
    for c in FEATURE_NUMERIC:
        if c in X.columns:
            X[c] = pd.to_numeric(X[c], errors="coerce")

    # Coerce categorical features to string to avoid mixed-type comparisons during encoding
    for c in FEATURE_CATEGORICAL:
        if c in X.columns:
            # replace nan-like with explicit 'missing' then cast to str
            X[c] = X[c].where(X[c].notnull(), "missing").astype(str)

    # select feature order expected by pipeline
    try:
        probs = model.predict_proba(X[ALL_FEATURES])[:, 1]
    except Exception as e:
        # last-resort: try passing whole DataFrame to pipeline (some pipelines accept extra cols)
        try:
            probs = model.predict_proba(X)[:, 1]
        except Exception:
            raise

    out = pd.DataFrame({
        "p_hotspot": probs,
    })
    # attach y_true if present
    if "hotspot" in df.columns:
        out["y_true"] = df["hotspot"].values
    return out


def single_point_args_to_df(args) -> pd.DataFrame:
    # create a single-row dataframe with required columns
    data = {}
    for f in FEATURE_NUMERIC + FEATURE_CATEGORICAL:
        val = getattr(args, f, None)
        if val is None:
            # leave missing values as NaN (pipeline may handle)
            data[f] = [np.nan]
        else:
            data[f] = [val]
    df = pd.DataFrame(data)
    df = compute_derived(df)
    return df


def main():
    p = argparse.ArgumentParser(description="Use trained hotspot model to predict probabilities")
    p.add_argument("--model", required=True, help="Path to joblib model pipeline")

    # single-point args
    for f in FEATURE_NUMERIC + FEATURE_CATEGORICAL:
        p.add_argument(f"--{f}", default=None)

    # batch
    p.add_argument("--in_csv", help="Input CSV to predict (full features or raw processed file)")
    p.add_argument("--in_json", help="Input JSON file (array of objects) to predict")
    p.add_argument("--out_csv", help="Output CSV path (writes p_hotspot and y_true if available)")
    p.add_argument("--out_json", help="Output JSON file (writes array of results)")
    p.add_argument("--print_json", action="store_true", help="Print JSON to stdout")
    p.add_argument("--max_rows", type=int, default=None, help="If set, limit rows read from input CSV for quick testing")
    p.add_argument("--top_k", type=int, default=None, help="If set, return top-k rows by predicted probability")

    args = p.parse_args()

    model = load_model(Path(args.model))

    if args.in_csv or args.in_json:
        if args.in_csv:
            df = pd.read_csv(args.in_csv)
        else:
            # JSON input expected to be an array of objects
            with open(args.in_json, "r", encoding="utf-8") as jf:
                data = json.load(jf)
            df = pd.DataFrame(data)

        if args.max_rows:
            df = df.head(args.max_rows)
        out = predict_df(model, df)
        # merge predictive columns back with identifying columns if present
        if "lat" in df.columns and "lon" in df.columns:
            out = pd.concat([df.reset_index(drop=True)[[c for c in df.columns if c in ["year","month","lat","lon"]]], out.reset_index(drop=True)], axis=1)
        # CSV output
        if args.out_csv:
            out.to_csv(args.out_csv, index=False)
            print(f"Wrote predictions to {args.out_csv} ({out.shape[0]} rows)")

        # JSON output
        if args.out_json:
            # produce list of dicts
            records = []
            for i, row in out.reset_index(drop=True).iterrows():
                rec = {}
                if "year" in df.columns and "month" in df.columns:
                    rec.update({"year": int(df.iloc[i]["year"]), "month": int(df.iloc[i]["month"])})
                if "lat" in df.columns and "lon" in df.columns:
                    rec.update({"lat": float(df.iloc[i]["lat"]), "lon": float(df.iloc[i]["lon"])})
                rec.update({"p_hotspot": float(row["p_hotspot"])})
                if "y_true" in row and not pd.isna(row["y_true"]):
                    rec.update({"y_true": int(row["y_true"] )})
                records.append(rec)

            # apply top_k if requested
            if args.top_k:
                records = sorted(records, key=lambda r: r.get("p_hotspot", 0), reverse=True)[: args.top_k]

            with open(args.out_json, "w", encoding="utf-8") as jf:
                json.dump(records, jf, indent=2)
            print(f"Wrote JSON predictions to {args.out_json} ({len(records)} rows)")

        # also optionally print JSON to stdout
        if args.print_json:
            records = []
            for i, row in out.reset_index(drop=True).iterrows():
                rec = {}
                if "year" in df.columns and "month" in df.columns:
                    rec.update({"year": int(df.iloc[i]["year"]), "month": int(df.iloc[i]["month"])})
                if "lat" in df.columns and "lon" in df.columns:
                    rec.update({"lat": float(df.iloc[i]["lat"]), "lon": float(df.iloc[i]["lon"])})
                rec.update({"p_hotspot": float(row["p_hotspot"])})
                if "y_true" in row and not pd.isna(row["y_true"]):
                    rec.update({"y_true": int(row["y_true"] )})
                records.append(rec)
            print(json.dumps(records if len(records)>1 else records[0], indent=2))
    else:
        # single point mode: construct DataFrame from provided args
        df = single_point_args_to_df(args)
        out = predict_df(model, df)
        # print a friendly output
        row = out.iloc[0].to_dict()
        result = {"p_hotspot": float(row["p_hotspot"]) }
        if "y_true" in row and not pd.isna(row["y_true"]):
            result["y_true"] = int(row["y_true"])
        # include input location if provided
        for k in ["year","month","lat","lon"]:
            v = getattr(args, k, None)
            if v is not None:
                try:
                    result[k] = float(v) if k in ["lat","lon"] else int(v)
                except Exception:
                    result[k] = v
        if args.print_json:
            print(json.dumps(result))
        else:
            print(result)


if __name__ == "__main__":
    main()
