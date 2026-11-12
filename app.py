"""
app.py — Brahmaputra floodplain surface-water change snapshot (Sentinel-2).

Reads pipeline outputs if present:
  data/outputs/change_map.tif  uint8: 0=land, 1=persistent water, 2=new water, 255=no data (cloud/shadow)
  data/outputs/summary.json    dates, scene counts, AOI name (all keys optional)
Otherwise renders a synthetic DEMO so the UI can be developed without data.
"""
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

OUT_DIR = Path("data/outputs")
CHANGE_TIF = OUT_DIR / "change_map.tif"
SUMMARY_JSON = OUT_DIR / "summary.json"

# Internal class codes (the pipeline's 255 no-data is remapped to NODATA on load)
LAND, PERM, NEW, NODATA = 0, 1, 2, 3
COLORS = ["#e8e4d8", "#1f5fa8", "#e4572e", "#bdbdbd"]
LABELS = ["Land", "Persistent water", "New water (flood)", "No data (cloud/shadow)"]
LOW_COVERAGE = 0.70  # warn the user below this valid-observation fraction


@st.cache_data
def load_real():
    """Load the change map and summary written by the pipeline. Returns None if absent."""
    if not CHANGE_TIF.exists():
        return None
    import rasterio  # imported lazily so the demo works without raster files

    with rasterio.open(CHANGE_TIF) as src:
        arr = src.read(1)
        px_km2 = abs(src.res[0] * src.res[1]) / 1e6  # assumes projected CRS in metres (e.g. UTM 46N)
    arr = np.where(arr == 255, NODATA, arr).astype(np.uint8)
    meta = json.loads(SUMMARY_JSON.read_text()) if SUMMARY_JSON.exists() else {}
    return arr, px_km2, meta


@st.cache_data
def make_demo():
    """Synthetic meandering river + flood + cloud patch. NOT real data."""
    h, w = 300, 400
    yy, xx = np.mgrid[0:h, 0:w]
    centre = 150 + 40 * np.sin(xx / 50)
    dist = np.abs(yy - centre)
    perm = dist < 8
    flood_width = 35 + 15 * np.sin(xx / 30 + 1)
    new = (dist < flood_width) & ~perm
    arr = np.full((h, w), LAND, dtype=np.uint8)
    arr[perm] = PERM
    arr[new] = NEW
    arr[(yy - 100) ** 2 + (xx - 280) ** 2 < 40**2] = NODATA  # simulated cloud
    return arr, 0.0004, {"aoi": "DEMO (synthetic)"}  # 20 m pixels = 0.0004 km²


def compute_metrics(arr, px_km2):
    valid = arr != NODATA
    return {
        "new_km2": float((arr == NEW).sum() * px_km2),
        "perm_km2": float((arr == PERM).sum() * px_km2),
        "valid_frac": float(valid.mean()),
        "new_pct_valid": float((arr == NEW).sum() / max(valid.sum(), 1) * 100),
    }


def render_map(arr):
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.imshow(arr, cmap=ListedColormap(COLORS), vmin=0, vmax=3, interpolation="nearest")
    ax.set_axis_off()
    ax.legend(
        handles=[Patch(color=c, label=l) for c, l in zip(COLORS, LABELS)],
        loc="lower center", bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=False,
    )
    fig.tight_layout()
    return fig


# ----------------------------- UI -----------------------------
st.set_page_config(page_title="Brahmaputra Flood Snapshot", layout="wide")
st.title("Brahmaputra Floodplain: Surface-Water Change Snapshot")
st.caption("Sentinel-2 change detection: pre-monsoon (dry) vs. post-rain (monsoon) · Assam, India")

st.markdown(
    "**Use-case.** A district disaster-response desk needs a rapid surface-water snapshot after "
    "heavy monsoon rain to decide which blocks to reach first. This view shows where water has "
    "appeared since the dry-season baseline, and how much of the area could not be observed "
    "because of cloud. It is refreshed whenever new Sentinel-2 scenes are ingested."
)

real = load_real()
if real is None:
    arr, px_km2, meta = make_demo()
    st.warning("DEMO MODE: synthetic data shown. Run the pipeline to populate `data/outputs/`.")
else:
    arr, px_km2, meta = real

m = compute_metrics(arr, px_km2)
c1, c2, c3, c4 = st.columns(4)
c1.metric("New water (km²)", f"{m['new_km2']:,.1f}")
c2.metric("Persistent water (km²)", f"{m['perm_km2']:,.1f}")
c3.metric("New water, % of observed area", f"{m['new_pct_valid']:.1f}%")
c4.metric("Observed (cloud-free) coverage", f"{m['valid_frac'] * 100:.0f}%")

if m["valid_frac"] < LOW_COVERAGE:
    st.error(
        f"Only {m['valid_frac'] * 100:.0f}% of the area was observed. Flood extent is a "
        "LOWER BOUND; grey areas are unknown, not dry."
    )

left, right = st.columns([3, 1])
with left:
    st.pyplot(render_map(arr))
with right:
    st.markdown("**Scene info**")
    st.write(f"AOI: {meta.get('aoi', 'n/a')}")
    st.write(f"Baseline window: {meta.get('pre_window', 'n/a')}")
    st.write(f"Event window: {meta.get('post_window', 'n/a')}")
    st.write(f"Scenes used (pre/post): {meta.get('pre_scenes', 'n/a')} / {meta.get('post_scenes', 'n/a')}")
     # ---- Priority cells: where to send teams first (from the GeoParquet table) ----
FEATURES = Path("data/catalog/features.parquet")


@st.cache_data
def load_priority(path):
    """Latest run's per-cell table, or None if the catalogue has not been built."""
    if not path.exists():
        return None
    import geopandas as gpd  # imported lazily, like rasterio above

    table = gpd.read_parquet(path)
    return table[table["event_date"] == table["event_date"].max()].copy()


cells = load_priority(FEATURES)
st.subheader("Where to go first")
if cells is None:
    st.info("No feature table yet. Run `python pipeline/catalogue.py` to build it.")
else:
    cells["flooded_pct_of_cell"] = cells["new_km2"] / cells["cell_km2"] * 100
    rank_by = st.radio("Rank cells by", ["new water km²", "% of cell flooded"], horizontal=True)
    sort_col = "new_km2" if rank_by == "new water km²" else "flooded_pct_of_cell"
    top = cells.sort_values(sort_col, ascending=False).head(10)
    st.caption(
        f"2 km cells ranked by newly flooded area, event date {cells['event_date'].iloc[0]}. "
        "Cells are a stand-in for administrative blocks."
    )
    map_col, table_col = st.columns([3, 2])
    with map_col:
        fig2, ax2 = plt.subplots(figsize=(6, 6))
        cells.plot(column="new_km2", cmap="Reds", legend=True, edgecolor="white",
                   linewidth=0.3, ax=ax2,
                   legend_kwds={"label": "new water (km²)", "shrink": 0.7})
        for _, row in top.head(5).iterrows():
            ax2.annotate(row["cell_id"], (row.geometry.centroid.x, row.geometry.centroid.y),
                         ha="center", fontsize=7)
        ax2.set_axis_off()
        st.pyplot(fig2)
    with table_col:
        st.dataframe(
            top[["cell_id", "new_km2", "flooded_pct_of_cell", "valid_frac"]]
            .rename(columns={"new_km2": "new water km²", "flooded_pct_of_cell": "% of cell",
                             "valid_frac": "observed"})
            .round(2),
            hide_index=True,
        )
with st.expander("Method and limitations"):
    st.markdown(
        "- Water = MNDWI (Green B03, SWIR1 B11) above a threshold, after SCL cloud/shadow masking.\n"
        "- Change = water in event composite AND not in baseline composite.\n"
        "- Optical sensing cannot see through monsoon cloud; grey = unknown.\n"
        "- Not validated for flooded vegetation, turbid water, or urban flooding."
    )