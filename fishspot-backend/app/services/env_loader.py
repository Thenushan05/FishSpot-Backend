"""Environment grid loader.

This provides `load_env_grid(date_str)` which reads CSV files at
`data/env_grid/env_grid_<YYYYMMDD>.csv` and returns a pandas DataFrame.

Change the `ENV_GRID_DIR` constant below to point to your CSV directory.
"""
from pathlib import Path
from typing import Optional
import pandas as pd

# Change this path if your env CSVs are elsewhere
ENV_GRID_DIR = Path(__file__).resolve().parents[2] / "data" / "env_grid"


def load_env_grid(date_str: str) -> pd.DataFrame:
    """Load environment grid CSV for a given date string YYYYMMDD.

    Raises FileNotFoundError if not present.
    """
    filename = ENV_GRID_DIR / f"env_grid_{date_str}.csv"
    if not filename.exists():
        raise FileNotFoundError(f"Env grid file not found: {filename}")
    # read CSV - expect columns at least: lat, lon, sst, sss, ssh, chl
    df = pd.read_csv(filename)
    # Basic validation
    required = {"lat", "lon", "sst", "sss", "ssh", "chl"}
    if not required.issubset(set(df.columns)):
        missing = required - set(df.columns)
        raise ValueError(f"Env grid missing columns: {missing}")
    return df


def find_available_dates() -> list:
    """Return list of dates (YYYYMMDD) available in the env grid directory."""
    files = list(ENV_GRID_DIR.glob("env_grid_*.csv"))
    dates = [p.stem.replace("env_grid_", "") for p in files]
    return sorted(dates)
