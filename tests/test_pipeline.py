"""
Offline tests for the water mask (pipeline/water_change.py).

They use tiny made-up images (a few pixels) instead of real satellite data,
so they run in seconds with no internet. Each pixel is chosen so that we know
in advance what the right answer is.
"""
import numpy as np
import pytest
import xarray as xr

from pipeline.water_change import INVALID, water_mask


def make_ds(green, swir, scl):
    """Build a tiny fake scene with the three bands that water_mask reads."""
    dims = ("y", "x")
    return xr.Dataset(
        {
            "B03": (dims, np.array(green, dtype="float32")),
            "B11": (dims, np.array(swir, dtype="float32")),
            "SCL": (dims, np.array(scl, dtype="uint8")),
        }
    )


def test_water_land_cloud_and_nodata_together():
    # Four pixels side by side: water, land, cloud over water, empty pixel.
    ds = make_ds(
        green=[[3000, 1500, 3000, 0]],
        swir=[[1500, 3000, 1500, 0]],
        scl=[[6, 4, 9, 0]],  # 6 = water, 4 = vegetation, 9 = cloud, 0 = no data
    )
    water, valid, _ = water_mask(ds)
    assert water.tolist() == [[True, False, False, False]]
    assert valid.tolist() == [[True, True, False, False]]


@pytest.mark.parametrize("code", INVALID)
def test_invalid_scl_codes_are_never_valid(code):
    # A pixel that looks like water, but flagged as cloud/shadow/etc.,
    # must be "unknown", not water.
    ds = make_ds(green=[[3000]], swir=[[1500]], scl=[[code]])
    water, valid, _ = water_mask(ds)
    assert not valid[0, 0]
    assert not water[0, 0]


@pytest.mark.parametrize("code", [4, 5, 6])
def test_clear_scl_codes_are_valid(code):
    # Vegetation (4), bare soil (5) and water (6) are usable observations.
    ds = make_ds(green=[[3000]], swir=[[1500]], scl=[[code]])
    _, valid, _ = water_mask(ds)
    assert valid[0, 0]


def test_offset_correction():
    # Scenes after Jan 2022 carry a +1000 offset that must be removed first.
    # Pixel 1: green 1500, swir 1000 -> 500 and 0 after offset -> MNDWI = 1 -> water.
    # Pixel 2: both 1000 -> 0 and 0 -> index undefined -> must be "unknown".
    ds = make_ds(green=[[1500, 1000]], swir=[[1000, 1000]], scl=[[4, 4]])
    water, valid, _ = water_mask(ds)
    assert water.tolist() == [[True, False]]
    assert valid.tolist() == [[True, False]]