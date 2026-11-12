"""
Offline tests for the cell table and the feature table (pipeline/catalogue.py).

A tiny made-up change map (200 x 200 pixels = four 100 x 100 cells) is built
by hand, so every expected number can be worked out on paper.
"""
import numpy as np
import pytest
from affine import Affine
from rasterio.crs import CRS

from pipeline import catalogue
from pipeline.catalogue import NEW, NODATA, PERM, cell_table, starts, update_features

PX_KM2 = 20 * 20 / 1e6  # one 20 m pixel in km2
INFO = {"transform": Affine(20, 0, 500000, 0, -20, 3000000), "crs": CRS.from_epsg(32646)}
RUN_ID = "2024-07-26_vs_2024-02-12"


def make_summary(post="2024-07-26"):
    return {"pre_window": "2024-02-12", "post_window": post}


def make_map():
    """200 x 200 map of land with a few known patches."""
    arr = np.zeros((200, 200), dtype="uint8")
    arr[0, 0:10] = NEW             # 10 new-water pixels in cell r0c0
    arr[1, 0:20] = NODATA          # 20 unobserved pixels in cell r0c0
    arr[50, 50:55] = PERM          # 5 persistent-water pixels in cell r0c0
    arr[100:200, 100:200] = NODATA  # cell r1c1 completely cloudy
    return arr


@pytest.fixture
def isolated_catalogue(tmp_path, monkeypatch):
    """Point the feature table at a temporary folder so tests never touch real data."""
    monkeypatch.setattr(catalogue, "CAT_DIR", tmp_path)
    monkeypatch.setattr(catalogue, "FEATURES", tmp_path / "features.parquet")


# ---------------------------- cell grid ----------------------------

@pytest.mark.parametrize(
    "n, expected",
    [
        (250, [0, 100, 200]),  # leftover strip of 50 px is big enough to be its own cell
        (230, [0, 100]),       # leftover strip of 30 px joins the previous cell
        (100, [0]),            # exactly one cell
        (40, [0]),             # smaller than one cell
    ],
)
def test_starts(n, expected):
    assert starts(n) == expected


def test_cell_table_values():
    table = cell_table(RUN_ID, make_summary(), make_map(), INFO)
    assert len(table) == 4
    c = table.set_index("cell_id").loc["r0c0"]
    assert c["cell_km2"] == pytest.approx(10000 * PX_KM2)
    assert c["new_km2"] == pytest.approx(10 * PX_KM2)
    assert c["persistent_km2"] == pytest.approx(5 * PX_KM2)
    assert c["valid_frac"] == pytest.approx(9980 / 10000)
    assert c["new_pct_of_valid"] == pytest.approx(100 * 10 / 9980)


def test_fully_cloudy_cell_is_unknown_not_zero():
    table = cell_table(RUN_ID, make_summary(), make_map(), INFO).set_index("cell_id")
    cloudy = table.loc["r1c1"]
    assert cloudy["valid_frac"] == 0
    assert np.isnan(cloudy["new_pct_of_valid"])  # unknown, not "0% flooded"


# ------------------------- feature table re-runs -------------------------

def test_rerun_same_dates_replaces_rows(isolated_catalogue):
    first = update_features(cell_table(RUN_ID, make_summary(), make_map(), INFO))
    assert len(first) == 4

    changed = make_map()
    changed[20, 0:10] = NEW  # 10 more new-water pixels
    second = update_features(cell_table(RUN_ID, make_summary(), changed, INFO))

    assert len(second) == 4  # replaced, not duplicated
    assert second["new_km2"].sum() == pytest.approx(20 * PX_KM2)  # new values kept


def test_new_dates_add_a_second_run(isolated_catalogue):
    update_features(cell_table(RUN_ID, make_summary(), make_map(), INFO))
    other = "2024-07-31_vs_2024-02-12"
    table = update_features(cell_table(other, make_summary("2024-07-31"), make_map(), INFO))

    assert len(table) == 8
    assert set(table["run_id"]) == {RUN_ID, other}