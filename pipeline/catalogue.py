"""
Step D6: catalogue + feature table, so the asset can refresh.

Reads data/outputs/change_map.tif and summary.json (written by water_change.py) and
  1. registers the run as an Item in a small STAC catalogue (data/catalog/)
  2. writes per-cell statistics to a GeoParquet table (data/catalog/features.parquet)

Safe to re-run: a run is identified by its two dates, and re-running the same dates
replaces that run's item and rows instead of duplicating them.
"""
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pystac
import rasterio
from pyproj import Transformer
from rasterio.windows import Window, bounds as window_bounds
from shapely.geometry import box, mapping

OUT_DIR = Path("data/outputs")
CAT_DIR = Path("data/catalog")
FEATURES = CAT_DIR / "features.parquet"
COLLECTION_ID = "brahmaputra-flood-change"
CELL_PX = 100                       # 100 px x 20 m = 2 km cells (stand-in for admin blocks)
LAND, PERM, NEW, NODATA = 0, 1, 2, 255


def read_run():
    """Read the change map and the run summary written by water_change.py."""
    summary = json.loads((OUT_DIR / "summary.json").read_text())
    with rasterio.open(OUT_DIR / "change_map.tif") as src:
        arr = src.read(1)
        info = {"transform": src.transform, "crs": src.crs, "bounds": tuple(src.bounds)}
    run_id = f"{summary['post_window']}_vs_{summary['pre_window']}"
    return run_id, summary, arr, info


def cell_table(run_id, summary, arr, info):
    """One row per CELL_PX x CELL_PX cell: flooded area and how much was observable."""
    tr = info["transform"]
    px_km2 = abs(tr.a * tr.e) / 1e6
    h, w = arr.shape
    rows, geoms = [], []
    for r0 in range(0, h, CELL_PX):
        for c0 in range(0, w, CELL_PX):
            win = Window(c0, r0, min(CELL_PX, w - c0), min(CELL_PX, h - r0))
            block = arr[r0:r0 + int(win.height), c0:c0 + int(win.width)]
            n_valid = int((block != NODATA).sum())
            n_new = int((block == NEW).sum())
            rows.append({
                "run_id": run_id,
                "event_date": summary["post_window"],
                "baseline_date": summary["pre_window"],
                "cell_id": f"r{r0 // CELL_PX}c{c0 // CELL_PX}",
                "cell_km2": block.size * px_km2,
                "new_km2": n_new * px_km2,
                "persistent_km2": int((block == PERM).sum()) * px_km2,
                "valid_frac": n_valid / block.size,
                "new_pct_of_valid": 100 * n_new / n_valid if n_valid else np.nan,
            })
            geoms.append(box(*window_bounds(win, tr)))
    return gpd.GeoDataFrame(rows, geometry=geoms, crs=info["crs"])


def update_features(new_rows):
    """Append this run's rows; replace any earlier rows for the same run_id."""
    CAT_DIR.mkdir(parents=True, exist_ok=True)
    crs = new_rows.crs
    if FEATURES.exists():
        old = gpd.read_parquet(FEATURES)
        old = old[old["run_id"] != new_rows["run_id"].iloc[0]]
        new_rows = pd.concat([old, new_rows], ignore_index=True)
    table = gpd.GeoDataFrame(new_rows, geometry="geometry", crs=crs)
    table.to_parquet(FEATURES)
    return table


def update_catalogue(run_id, summary, features, info):
    """Add (or replace) this run as an Item in the STAC catalogue and save it."""
    west, south, east, north = Transformer.from_crs(
        info["crs"].to_string(), "EPSG:4326", always_xy=True
    ).transform_bounds(*info["bounds"])
    bbox = [west, south, east, north]

    cat_file = CAT_DIR / "catalog.json"
    if cat_file.exists():
        catalog = pystac.Catalog.from_file(str(cat_file))
        collection = catalog.get_child(COLLECTION_ID)
        if collection.get_item(run_id) is not None:
            collection.remove_item(run_id)
    else:
        catalog = pystac.Catalog(
            id="eo-flood-catalogue",
            description="Surface-water change runs over a Brahmaputra floodplain test box.",
        )
        collection = pystac.Collection(
            id=COLLECTION_ID,
            description="Two-date Sentinel-2 surface-water change maps (derived products).",
            extent=pystac.Extent(
                pystac.SpatialExtent([bbox]), pystac.TemporalExtent([[None, None]])
            ),
        )
        catalog.add_child(collection)

    rows = features[features["run_id"] == run_id]
    item = pystac.Item(
        id=run_id,
        geometry=mapping(box(*bbox)),
        bbox=bbox,
        datetime=datetime.fromisoformat(summary["post_window"]).replace(tzinfo=timezone.utc),
        properties={
            "baseline_date": summary["pre_window"],
            "event_date": summary["post_window"],
            "mndwi_threshold": summary.get("mndwi_threshold"),
            "new_water_km2": round(float(rows["new_km2"].sum()), 2),
            "persistent_water_km2": round(float(rows["persistent_km2"].sum()), 2),
            "observed_fraction": round(
                float(np.average(rows["valid_frac"], weights=rows["cell_km2"])), 4
            ),
            "source": "Sentinel-2 L2A via Microsoft Planetary Computer",
            "created": datetime.now(timezone.utc).isoformat(),
        },
    )
    item.add_asset(
        "change_map",
        pystac.Asset(
            href="./change_map.tif",
            media_type=pystac.MediaType.GEOTIFF,
            roles=["data"],
            title="Change map (0 land, 1 persistent water, 2 new water, 255 no data)",
        ),
    )
    collection.add_item(item)
    collection.update_extent_from_items()

    catalog.normalize_hrefs(str(CAT_DIR.resolve()))
    item_dir = Path(item.get_self_href()).parent
    item_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(OUT_DIR / "change_map.tif", item_dir / "change_map.tif")
    catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)
    return catalog


def main():
    run_id, summary, arr, info = read_run()
    features = update_features(cell_table(run_id, summary, arr, info))
    catalog = update_catalogue(run_id, summary, features, info)

    n_items = len(list(catalog.get_items(recursive=True)))
    run_rows = features[features["run_id"] == run_id]
    print(f"run: {run_id}")
    print(f"catalogue items: {n_items} | feature rows: {len(features)} "
          f"({len(run_rows)} for this run)")
    print("cells with the most new water:")
    top = run_rows.sort_values("new_km2", ascending=False).head(5)
    print(top[["cell_id", "new_km2", "valid_frac"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()