"""
Diagnostic: compare the cloud mask (SCL) at 20 m and 60 m for the event date,
and check how much of the "unusable" area would have been water.
"""
import numpy as np
import planetary_computer
from odc.stac import load
from pystac_client import Client

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
BBOX = [94.10, 26.90, 94.30, 27.05]
CRS = "EPSG:32646"
DAY = "2024-07-26"
INVALID = [0, 1, 3, 8, 9, 10]
NAMES = {0: "no data", 1: "saturated", 2: "dark area", 3: "cloud shadow",
         4: "vegetation", 5: "not vegetated", 6: "water", 7: "unclassified",
         8: "cloud (medium)", 9: "cloud (high)", 10: "thin cirrus", 11: "snow/ice"}

client = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
items = client.search(
    collections=["sentinel-2-l2a"], bbox=BBOX,
    datetime=f"{DAY}T00:00:00Z/{DAY}T23:59:59Z",
).item_collection()
print(f"{len(items)} scene files for {DAY}")

for res in (20, 60):
    ds = load(items, bands=["B03", "B11", "SCL"], bbox=BBOX, crs=CRS,
              resolution=res, groupby="solar_day", chunks={}).isel(time=0).compute()
    scl = ds["SCL"].values
    print(f"\n--- {res} m: shape {scl.shape}, SCL dtype {scl.dtype} ---")
    values, counts = np.unique(scl, return_counts=True)
    for v, c in zip(values, counts):
        print(f"  class {int(v):>3} ({NAMES.get(int(v), '?'):<15}) {c / scl.size * 100:6.2f}%")

    green = np.clip(ds["B03"].values.astype("float32") - 1000, 0, None)
    swir = np.clip(ds["B11"].values.astype("float32") - 1000, 0, None)
    denom = green + swir
    with np.errstate(divide="ignore", invalid="ignore"):
        mndwi = np.where(denom > 0, (green - swir) / denom, np.nan)
    bad = np.isin(scl, INVALID)
    print(f"  unusable: {bad.mean() * 100:.2f}% of pixels")
    if bad.any():
        print(f"  of those, {(mndwi[bad] > 0).mean() * 100:.1f}% look like water (MNDWI > 0)")