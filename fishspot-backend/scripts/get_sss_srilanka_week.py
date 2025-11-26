import datetime as dt
from pathlib import Path

import copernicusmarine
import xarray as xr

# ---------- CONFIG ----------
SSS_DATASET_ID = "cmems_obs-mob_glo_phy-sss_nrt_multi_P1D"
SSS_VAR = "sea_surface_salinity"

# Sri Lanka region
LAT_MIN, LAT_MAX = 3, 12
LON_MIN, LON_MAX = 78, 84

# Week range: last available dataset end is 2025-11-19 (use that as end)
DATE_END = dt.date(2025, 11, 19)
DATE_START = DATE_END - dt.timedelta(days=6)
DATE_START_STR = DATE_START.isoformat()
DATE_END_STR = DATE_END.isoformat()

OUT_DIR = Path("data/cmems_week")
OUT_DIR.mkdir(parents=True, exist_ok=True)
# -----------------------------


def main():
    print(f"🔹 Requesting SSS from {DATE_START_STR} to {DATE_END_STR} in Sri Lanka box...")

    start = f"{DATE_START_STR}T00:00:00"
    end = f"{DATE_END_STR}T23:59:59"

    copernicusmarine.subset(
        dataset_id=SSS_DATASET_ID,
        variables=[SSS_VAR],
        minimum_longitude=LON_MIN,
        maximum_longitude=LON_MAX,
        minimum_latitude=LAT_MIN,
        maximum_latitude=LAT_MAX,
        start_datetime=start,
        end_datetime=end,
        file_format="netcdf",
        output_directory=str(OUT_DIR),
    )

    nc_files = list(OUT_DIR.glob("*.nc"))
    if not nc_files:
        print("No NetCDF file downloaded!")
        return

    print("Downloaded files:")
    for p in nc_files:
        print(" -", p)

    # Open first file and summarise
    nc_path = nc_files[0]
    ds = xr.open_dataset(nc_path)
    print(ds)

    if SSS_VAR in ds:
        sss_da = ds[SSS_VAR]
        try:
            print("SSS time coords:", sss_da.time)
            print("SSS spatial mean over time:")
            print(sss_da.mean(dim=("time", "latitude", "longitude")))
        except Exception as e:
            print("Could not summarize variable:", e)
    else:
        print(f"Variable {SSS_VAR} not found. Available: {list(ds.data_vars)}")


if __name__ == "__main__":
    main()
