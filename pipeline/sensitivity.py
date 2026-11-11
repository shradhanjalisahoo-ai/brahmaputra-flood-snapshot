"""
Step D4: how sensitive is the flood estimate to the MNDWI threshold?
Loads both dates once, then recomputes new/persistent water for several cutoffs.
Prints a table and saves data/threshold_sensitivity.png.
"""
import matplotlib.pyplot as plt
import numpy as np
import planetary_computer
from pystac_client import Client

from water_change import DAYS, RES, STAC_URL, load_day, water_mask

THRESHOLDS = [-0.2, -0.1, 0.0, 0.1, 0.2, 0.3]
PX_KM2 = RES * RES / 1e6


def main():
    client = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)
    data = {}
    for name, day in DAYS.items():
        _, ds = load_day(client, day)
        _, valid, mndwi = water_mask(ds)  # we reuse valid + mndwi, apply our own cutoffs
        data[name] = (valid, mndwi)

    (pre_valid, pre_m), (post_valid, post_m) = data["baseline"], data["event"]
    both_valid = pre_valid & post_valid

    rows = []
    print(f"{'threshold':>10}{'baseline km2':>14}{'event km2':>12}{'NEW km2':>10}{'PERSIST km2':>13}")
    for t in THRESHOLDS:
        with np.errstate(invalid="ignore"):
            pre_w = both_valid & (pre_m > t)
            post_w = both_valid & (post_m > t)
        new = post_w & ~pre_w
        perm = post_w & pre_w
        row = (t, pre_w.sum() * PX_KM2, post_w.sum() * PX_KM2,
               new.sum() * PX_KM2, perm.sum() * PX_KM2)
        rows.append(row)
        print(f"{row[0]:>10.1f}{row[1]:>14.1f}{row[2]:>12.1f}{row[3]:>10.1f}{row[4]:>13.1f}")

    ts = [r[0] for r in rows]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(ts, [r[3] for r in rows], "o-", label="new water")
    ax.plot(ts, [r[4] for r in rows], "s-", label="persistent water")
    ax.set_xlabel("MNDWI threshold")
    ax.set_ylabel("area (km²)")
    ax.set_title("Sensitivity of the estimate to the threshold")
    ax.legend()
    fig.tight_layout()
    fig.savefig("data/threshold_sensitivity.png", dpi=120)
    print("Saved data/threshold_sensitivity.png")


if __name__ == "__main__":
    main()