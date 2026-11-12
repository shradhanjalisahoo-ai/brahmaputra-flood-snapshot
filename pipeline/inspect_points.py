"""
Inspect band values at chosen labelled points (event date only).
Why: four spots labelled water have MNDWI just under 0. Are they dark water, where both
bands are tiny and the index is unstable, or something else? Prints reflectance per band.

Run from the project folder:  python -m pipeline.inspect_points
"""
import csv
from pathlib import Path

import planetary_computer
from odc.stac import load
from pystac_client import Client

from pipeline.water_change import BBOX, CRS, DAYS, OFFSET, RES, STAC_URL

LAB = Path("data/labelling")
FOCUS = [6, 14, 29, 51]            # labelled water, MNDWI just under 0
REFERENCE = [22, 44, 10, 13, 38]   # clear water, river water, river water, land, land


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main():
    pts = {int(r["id"]): r for r in read_csv(LAB / "points_private.csv")}
    labels = {int(r["id"]): r["label"] for r in read_csv(LAB / "labels.csv")}

    day = DAYS["event"]
    client = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    items = client.search(
        collections=["sentinel-2-l2a"], bbox=BBOX,
        datetime=f"{day}T00:00:00Z/{day}T23:59:59Z",
    ).item_collection()
    ds = load(items, bands=["B03", "B08", "B11"], bbox=BBOX, crs=CRS,
              resolution=RES, groupby="solar_day", chunks={}).isel(time=0).compute()

    def refl(band, r, c):
        """Reflectance (0 to 1) after removing the processing offset, floored at 0."""
        return max(float(ds[band].values[r, c]) - OFFSET, 0) / 10000

    print(f"{'id':>3} {'label':>5} {'mndwi':>7} {'green':>7} {'nir':>7} {'swir':>7}")
    for group in (FOCUS, REFERENCE):
        for pid in group:
            r, c = int(pts[pid]["row"]), int(pts[pid]["col"])
            print(f"{pid:>3} {labels[pid]:>5} {float(pts[pid]['mndwi']):>7.3f} "
                  f"{refl('B03', r, c):>7.3f} {refl('B08', r, c):>7.3f} {refl('B11', r, c):>7.3f}")
        print()


if __name__ == "__main__":
    main()