# Exact 23 feature names as expected by the ColumnTransformer inside the pipeline.
# Verified by inspecting model.steps[0][1].feature_names_in_
FEATURE_COLS = [
    "month",
    "depth_abs",
    "sss",
    "ssd",
    "sst",
    "ssh",
    "chlo",
    "month_sin",
    "month_cos",
    # interaction / engineered features
    "sst_x_chlo",
    "ssh_x_chlo",
    "sst_x_ssh",
    "depth_x_sst",
    "depth_x_chlo",
    "sst_squared",
    "chlo_log",
    "sss_x_sst",
    # cyclic lat/lon encoding
    "lat_sin",
    "lat_cos",
    "lon_sin",
    "lon_cos",
    # categorical
    "SPECIES_CODE",
    "monsoon",
]

T_CAND = 0.60
T_CORE = 0.80
