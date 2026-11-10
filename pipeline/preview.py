"""
Step D2: look at the data before analysing it.
Loads one baseline day and one event day at coarse 60 m resolution (fast),
saves true-colour pictures plus an "unusable pixels" mask, and prints the share
of OUR box that is unusable. The catalogue's cloud % covers the whole 110 km
tile, not our box, so we measure it ourselves with the SCL layer.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import planetary_computer
from odc.stac import load
from pystac_client import Client

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
BBOX = [94.10, 26.90, 94.30, 27.05]  # west, south, east, north
CRS = "EPSG:32646"                   # UTM zone 46N, metres
DAYS = {"baseline": "2024-02-12", "event": "2024-07-26"}

# SCL (scene classification) codes we treat as unusable:
# 0 no data, 1 saturated, 3 cloud shadow, 8/9 cloud, 10 thin cirrus
INVALID = [0, 1, 3, 8, 9, 10]
WATER = 6  # SCL's own water class (only used as a rough sanity check)


def load_day(client, day):
    """Load one calendar day over BBOX, merging tiles and duplicate scenes."""
    items = client.search(
        collections=["sentinel-2-l2a"],
        bbox=BBOX,
        datetime=f"{day}T00:00:00Z/{day}T23:59:59Z",
    ).item_collection()
    ds = load(
        items,
        bands=["B04", "B03", "B02", "SCL"],
        bbox=BBOX,
        crs=CRS,
        resolution=60,
        groupby="solar_day",
        chunks={},
    )
    return len(items), ds.isel(time=0).compute()


def main():
    client = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    fig, axes = plt.subplots(2, len(DAYS), figsize=(10, 9))

    for col, (name, day) in enumerate(DAYS.items()):
        n_items, ds = load_day(client, day)

        # True colour: red, green, blue. The -1000 removes the offset that
        # Sentinel-2 data processed after Jan 2022 carries; 0.3 brightens the view.
        rgb = np.stack([ds[b].values for b in ("B04", "B03", "B02")], axis=-1)
        rgb = np.clip((rgb.astype("float32") - 1000) / 10000, 0, 0.3) / 0.3

        scl = ds["SCL"].values
        bad = np.isin(scl, INVALID)
        water_share = (scl[~bad] == WATER).mean() * 100 if (~bad).any() else float("nan")
        print(f"{name} {day}: {n_items} scene files merged | "
              f"unusable pixels: {bad.mean() * 100:.1f}% | "
              f"SCL water (rough): {water_share:.1f}% of usable pixels")

        axes[0, col].imshow(rgb)
        axes[0, col].set_title(f"{name} {day}: true colour")
        axes[1, col].imshow(bad, cmap="gray_r", vmin=0, vmax=1)
        axes[1, col].set_title("black = unusable (cloud/shadow/no data)")
        for row in (0, 1):
            axes[row, col].axis("off")

    Path("data").mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig("data/preview.png", dpi=120)
    print("Saved data/preview.png")


if __name__ == "__main__":
    main()