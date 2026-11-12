"""
Step D5a: build a labelling sheet for a rough accuracy check (event date only).

Picks 60 pixels, 12 from each of five MNDWI ranges (clearly land ... clearly water),
shuffles them so the range is not obvious, and saves picture sheets showing each
spot in true colour and false colour. You then label each spot by eye in
data/labelling/labels.csv WITHOUT looking at points_private.csv (it holds the
MNDWI values and would bias you).
"""
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import planetary_computer
from odc.stac import load
from pystac_client import Client

from water_change import BBOX, CRS, DAYS, OFFSET, RES, STAC_URL, water_mask

MARGIN = 16          # keep spots this many pixels from the box edge so chips are full size
HALF = 15            # each chip is 31 x 31 pixels (about 620 m across)
PER_BIN = 12
BINS = [(-1.0, -0.3), (-0.3, -0.1), (-0.1, 0.1), (0.1, 0.3), (0.3, 1.01)]
PER_SHEET = 12
SEED = 42            # fixed seed so the same spots come out every run
OUT = Path("data/labelling")


def load_event():
    """Load the event day with the extra bands needed for the pictures."""
    day = DAYS["event"]
    client = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    items = client.search(
        collections=["sentinel-2-l2a"], bbox=BBOX,
        datetime=f"{day}T00:00:00Z/{day}T23:59:59Z",
    ).item_collection()
    ds = load(items, bands=["B02", "B03", "B04", "B08", "B11", "SCL"], bbox=BBOX,
              crs=CRS, resolution=RES, groupby="solar_day", chunks={})
    return ds.isel(time=0).compute()


def to_rgb(ds, bands, top):
    """Stack three bands into a picture, scaling reflectance 0..top to 0..1."""
    arr = np.stack([ds[b].values for b in bands], axis=-1).astype("float32")
    return np.clip((arr - OFFSET) / 10000 / top, 0, 1)


def main():
    ds = load_event()
    _, valid, mndwi = water_mask(ds)
    true_img = to_rgb(ds, ["B04", "B03", "B02"], 0.3)   # what the eye would see
    false_img = to_rgb(ds, ["B11", "B08", "B04"], 0.4)  # water black, vegetation green

    h, w = mndwi.shape
    interior = np.zeros((h, w), dtype=bool)
    interior[MARGIN:h - MARGIN, MARGIN:w - MARGIN] = True

    rng = np.random.default_rng(SEED)
    points = []
    for lo, hi in BINS:
        cand = np.argwhere(valid & interior & (mndwi >= lo) & (mndwi < hi))
        take = min(PER_BIN, len(cand))
        if take == 0:
            continue
        pick = cand[rng.choice(len(cand), take, replace=False)]
        points.extend((int(r), int(c)) for r, c in pick)
    points = [points[i] for i in rng.permutation(len(points))]  # shuffle

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "points_private.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["id", "row", "col", "mndwi"])
        for pid, (r, c) in enumerate(points, start=1):
            wr.writerow([pid, r, c, round(float(mndwi[r, c]), 4)])

    labels_path = OUT / "labels.csv"
    if labels_path.exists():
        print("labels.csv already exists, NOT overwritten (your labels are safe)")
    else:
        with open(labels_path, "w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["id", "label"])
            for pid in range(1, len(points) + 1):
                wr.writerow([pid, ""])

    n_sheets = int(np.ceil(len(points) / PER_SHEET))
    for s in range(n_sheets):
        chunk = list(enumerate(points, start=1))[s * PER_SHEET:(s + 1) * PER_SHEET]
        fig, axes = plt.subplots(6, 4, figsize=(12, 18))
        for ax in axes.ravel():
            ax.axis("off")
        for k, (pid, (r, c)) in enumerate(chunk):
            row, col = divmod(k, 2)
            for j, (img, kind) in enumerate(((true_img, "true colour"), (false_img, "false colour"))):
                ax = axes[row, col * 2 + j]
                ax.imshow(img[r - HALF:r + HALF + 1, c - HALF:c + HALF + 1],
                          interpolation="nearest")
                ax.add_patch(plt.Rectangle((HALF - 0.5, HALF - 0.5), 1, 1,
                                           fill=False, edgecolor="red", lw=1.5))
                ax.set_title(f"ID {pid}: {kind}", fontsize=9)
        fig.tight_layout()
        fig.savefig(OUT / f"sheet_{s + 1}.png", dpi=100)
        plt.close(fig)

    print(f"{len(points)} spots, {n_sheets} sheets saved in {OUT}/")
    print("Now label them in data/labelling/labels.csv")


if __name__ == "__main__":
    main()