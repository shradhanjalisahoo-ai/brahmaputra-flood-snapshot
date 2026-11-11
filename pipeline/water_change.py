"""
Step D3: build the real surface-water change map (MNDWI, two dates).
Writes data/outputs/change_map.tif and summary.json (read by app.py) plus a
check figure data/water_check.png.

Classes in change_map.tif: 0 land, 1 persistent water, 2 new water, 255 no data.
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import planetary_computer
import rasterio
from affine import Affine
from matplotlib.colors import ListedColormap
from odc.stac import load
from pystac_client import Client

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
BBOX = [94.10, 26.90, 94.30, 27.05]   # west, south, east, north
CRS = "EPSG:32646"                    # UTM zone 46N, metres
RES = 20                              # metres per pixel (B11 is natively 20 m)
DAYS = {"baseline": "2024-02-12", "event": "2024-07-26"}

INVALID = [0, 1, 3, 8, 9, 10]         # SCL: no data, saturated, shadow, cloud, cirrus
OFFSET = 1000                         # reflectance offset in scenes processed after Jan 2022
MNDWI_THRESHOLD = 0.0                 # conventional start; checked in the histogram

OUT_DIR = Path("data/outputs")
LAND, PERM, NEW, NODATA = 0, 1, 2, 255


def load_day(client, day):
    """Load one calendar day over BBOX; tiles and duplicate scenes are merged."""
    items = client.search(
        collections=["sentinel-2-l2a"],
        bbox=BBOX,
        datetime=f"{day}T00:00:00Z/{day}T23:59:59Z",
    ).item_collection()
    ds = load(
        items,
        bands=["B03", "B11", "SCL"],
        bbox=BBOX,
        crs=CRS,
        resolution=RES,
        groupby="solar_day",
        chunks={},
    )
    return len(items), ds.isel(time=0).compute()


def water_mask(ds):
    """Return (water, valid, mndwi) arrays for one date."""
    green = ds["B03"].values.astype("float32")
    swir = ds["B11"].values.astype("float32")
    scl = ds["SCL"].values

    valid = np.isfinite(scl) & ~np.isin(scl, INVALID) & (green > 0) & (swir > 0)
    g = np.clip(green - OFFSET, 0, None)
    s = np.clip(swir - OFFSET, 0, None)
    denom = g + s
    with np.errstate(divide="ignore", invalid="ignore"):
        mndwi = np.where(denom > 0, (g - s) / denom, np.nan)
        valid &= np.isfinite(mndwi)
        water = valid & (mndwi > MNDWI_THRESHOLD)
    return water, valid, mndwi


def main():
    client = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)

    res = {}
    for name, day in DAYS.items():
        n_items, ds = load_day(client, day)
        water, valid, mndwi = water_mask(ds)
        res[name] = {"n": n_items, "ds": ds, "water": water, "valid": valid, "mndwi": mndwi}

    pre, post = res["baseline"], res["event"]
    assert pre["water"].shape == post["water"].shape, "the two dates are on different grids"

    # --- change map -------------------------------------------------------
    change = np.full(pre["water"].shape, LAND, dtype=np.uint8)
    change[pre["water"] & post["water"]] = PERM
    change[~pre["water"] & post["water"]] = NEW
    change[~(pre["valid"] & post["valid"])] = NODATA  # cannot compare -> unknown

    # --- numbers ----------------------------------------------------------
    px_km2 = RES * RES / 1e6
    for name, r in res.items():
        print(f"{name} {DAYS[name]}: water {r['water'].sum() * px_km2:.1f} km² | "
              f"valid {r['valid'].mean() * 100:.1f}% of pixels")
    print(f"NEW water: {(change == NEW).sum() * px_km2:.1f} km² | "
          f"PERSISTENT: {(change == PERM).sum() * px_km2:.1f} km² | "
          f"NO DATA: {(change == NODATA).mean() * 100:.1f}%")

    # --- save GeoTIFF (for the app) ---------------------------------------
    ds0 = pre["ds"]
    x, y = ds0["x"].values, ds0["y"].values
    assert y[0] > y[-1], "expected north-up rows"
    transform = Affine(RES, 0, x[0] - RES / 2, 0, -RES, y[0] + RES / 2)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        OUT_DIR / "change_map.tif", "w", driver="GTiff",
        height=change.shape[0], width=change.shape[1], count=1, dtype="uint8",
        crs=CRS, transform=transform, nodata=NODATA, compress="deflate",
    ) as dst:
        dst.write(change, 1)

    summary = {
        "aoi": "Majuli-Jorhat stretch, Brahmaputra (test box)",
        "pre_window": DAYS["baseline"],
        "post_window": DAYS["event"],
        "pre_scenes": pre["n"],
        "post_scenes": post["n"],
        "mndwi_threshold": MNDWI_THRESHOLD,
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))

    # --- check figure -----------------------------------------------------
    mask_cmap = ListedColormap(["#e8e4d8", "#1f5fa8", "#bdbdbd"])
    change_cmap = ListedColormap(["#e8e4d8", "#1f5fa8", "#e4572e", "#bdbdbd"])
    fig, ax = plt.subplots(2, 2, figsize=(11, 9))
    for a, (name, r) in zip(ax.ravel()[:2], res.items()):
        cls = np.where(~r["valid"], 2, r["water"].astype(int))
        a.imshow(cls, cmap=mask_cmap, vmin=0, vmax=2, interpolation="nearest")
        a.set_title(f"{name} {DAYS[name]}: blue water, grey unusable")
        a.axis("off")
    shown = np.where(change == NODATA, 3, change)
    ax[1, 0].imshow(shown, cmap=change_cmap, vmin=0, vmax=3, interpolation="nearest")
    ax[1, 0].set_title("change: red = new water")
    ax[1, 0].axis("off")
    for name, r in res.items():
        ax[1, 1].hist(r["mndwi"][r["valid"]], bins=100, alpha=0.6, label=name)
    ax[1, 1].axvline(MNDWI_THRESHOLD, color="k", ls="--", label="threshold")
    ax[1, 1].set_title("MNDWI values (valid pixels)")
    ax[1, 1].legend()
    fig.tight_layout()
    fig.savefig("data/water_check.png", dpi=120)
    print("Saved data/outputs/change_map.tif, summary.json and data/water_check.png")


if __name__ == "__main__":
    main()