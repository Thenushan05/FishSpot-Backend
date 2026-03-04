import sys, os, time
sys.path.insert(0, '.')

# Load .env
env_path = '.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                os.environ.setdefault(k.strip(), v.strip())

from app.services.free_ocean_data_service import (
    FreeOceanDataService,
    _fetch_sst,
    _fetch_ssh,
    _fetch_depth_gebco,
)

svc = FreeOceanDataService()

lats = [7.5, 8.0, 8.5, 9.0, 9.5]
lons = [81.5, 82.0, 82.5, 83.0, 83.5]

print(f"\nFetching ALL ocean vars for {len(lats)} points east of Sri Lanka...")
t0 = time.time()

# ── CHLO / SSS / SSD (parallel bbox fetch) ─────────────────────────────────
results = svc.get_ocean_vars(lats, lons)

# ── SST per point ───────────────────────────────────────────────────────────
print("\n[SST] Fetching SST for all points...")
sst_results = []
for lat, lon in zip(lats, lons):
    val, src = _fetch_sst(lat, lon)
    sst_results.append((val, src))

# ── SSH (single centre-point estimate) ─────────────────────────────────────
print("\n[SSH] Fetching SSH (centre point)...")
centre_lat = (min(lats) + max(lats)) / 2.0
centre_lon = (min(lons) + max(lons)) / 2.0
ssh_val, ssh_src = _fetch_ssh(centre_lat, centre_lon)

# ── Depth per point ─────────────────────────────────────────────────────────
print("\n[DEPTH] Fetching depth for all points...")
depth_results = []
for lat, lon in zip(lats, lons):
    val, src = _fetch_depth_gebco(lat, lon)
    depth_results.append((val, src))

elapsed = time.time() - t0

print()
print("=" * 70)
print(f"  RESULTS for {len(results)} points  (total {elapsed:.1f}s)")
print("=" * 70)
for i, r in enumerate(results):
    lat, lon = lats[i], lons[i]
    chlo    = r.get("chlo")
    sss     = r.get("sss")
    ssd     = r.get("ssd")
    sst_v, sst_s     = sst_results[i]
    depth_v, depth_s = depth_results[i]

    print(f"  Point {i+1} ({lat:.1f}N {lon:.1f}E):")
    print(f"    CHLO  = {chlo:.4f} mg/m3" if chlo  is not None else "    CHLO  = N/A")
    print(f"           src: {r.get('chlo_source','')[:70]}")
    print(f"    SSS   = {sss:.3f} PSU"    if sss   is not None else "    SSS   = N/A")
    print(f"           src: {r.get('sss_source','')[:70]}")
    print(f"    SSD   = {ssd:.4f} kg/m3"  if ssd   is not None else "    SSD   = N/A")
    print(f"           src: {r.get('ssd_source','')[:70]}")
    print(f"    SST   = {sst_v:.2f} °C"   if sst_v is not None else "    SST   = N/A")
    print(f"           src: {sst_s[:70]}")
    print(f"    Depth = {depth_v:.1f} m")
    print(f"           src: {depth_s[:70]}")

print()
print(f"  SSH   = {ssh_val:.4f} m" if ssh_val is not None else "  SSH   = N/A")
print(f"         src: {ssh_src[:70]}")
print(f"         (centre point {centre_lat:.2f}N {centre_lon:.2f}E)")
print("=" * 70)
