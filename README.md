# Brahmaputra Flood Snapshot (EO-AI Role 01: R5 / S1 / D2 / T1)

Sentinel-2 change detection of surface water over a test box on the Brahmaputra
floodplain (Majuli / Jorhat stretch, Assam): dry-season baseline vs. a monsoon date.
Built for a district disaster-response desk deciding which blocks to reach first.

Pipeline: STAC search (Planetary Computer) -> cloud mask (SCL) -> MNDWI water mask ->
two-date change map -> STAC catalogue + GeoParquet cell table -> Streamlit app.

## Requirements

- **Python 3.11 or 3.12.** Newer versions (3.13/3.14) have no prebuilt wheels for the
  pinned packages and fail to install.
- Internet access for the pipeline (public Sentinel-2 L2A data via Microsoft Planetary
  Computer, no account needed).

## Setup

```bash
git clone <this-repo-url> && cd brahmaputra-flood-snapshot
python3.12 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

If you only have a newer Python, `uv` can fetch 3.12:
`pip install uv && uv venv --python 3.12 --managed-python .venv`, then
`uv pip install -r requirements.txt`.
`requirements.lock.txt` records the exact versions the project was tested with.

Note: `numpy` is pinned to 1.26.4 and `pyarrow` to 17.0.0 on purpose. Newer pyarrow
needs NumPy 2 and breaks the Parquet step.

## Run

One command, end to end (about two minutes):

```bash
python -m pipeline.run
```

It builds the change map for the default dates (baseline 2024-02-12, event 2024-07-26)
and registers the run in the catalogue. Other dates:

```bash
python -m pipeline.run --pre 2024-02-12 --post 2024-07-31
```

A run is identified by its two dates: new dates add a run, the same dates replace it.

Then the asset:

```bash
streamlit run app.py
```

Without pipeline outputs, the app shows a clearly labelled synthetic DEMO.

## Tests

```bash
python -m pytest -q
```

Offline tests for the water mask, cloud masking, cell grid, and catalogue re-runs.

19 tests; all should pass

## Outputs

| Path | What it is |
|---|---|
| `data/outputs/change_map.tif` | 0 land, 1 persistent water, 2 new water, 255 no data (20 m, EPSG:32646) |
| `data/outputs/summary.json` | dates, scene counts, threshold |
| `data/catalog/` | STAC catalogue: one Item per run, with the change map as an asset |
| `data/catalog/features.parquet` | GeoParquet: one row per ~2 km cell per run (new / persistent water km², observed fraction) |

The 2 km cells stand in for administrative blocks. A real deployment would use the
official block boundaries.

## Repository layout

```
app.py                       Streamlit asset (map, metrics, ranked cells)
pipeline/run.py              one-command entry point
pipeline/water_change.py     load, cloud-mask, MNDWI, change map
pipeline/catalogue.py        STAC catalogue + GeoParquet cell table
pipeline/search_scenes.py    catalogue search: how many scenes, how cloudy
pipeline/preview.py          quick look at the two dates
pipeline/sensitivity.py      effect of the MNDWI threshold on the estimate
pipeline/make_label_sheet.py builds the hand-label sheets
pipeline/check_scl.py        checks the cloud-mask (SCL) classes
pipeline/score_thresholds.py scores the hand labels at each MNDWI threshold
data/labelling/              60 hand labels and sampled points (see Evaluation)
tests/                       offline unit tests
```

## Evaluation (summary; details in the report)

- **Threshold sensitivity:** new water is 49.0 km² at MNDWI > 0, and about 38 to 69 km²
  for thresholds from +0.1 to -0.1. The estimate depends strongly on the threshold.
- **Hand labels:** 60 spots from the 26 July scene only, labelled from imagery by one person (23 water, 28 land,
  9 unsure; unsure spots are not scored, leaving 51). The sample is drawn evenly from
  five MNDWI ranges, so it over-represents ambiguous pixels. Scores compare thresholds
  with each other and are not accuracy over the whole area. Reproduce with
  `python -m pipeline.score_thresholds`.
  F1 is 0.81 to 0.86 for every threshold from -0.1 to +0.1 (0.83 at the default 0.0),
  so on 51 points these thresholds cannot be told apart. Lower thresholds raise recall
  and add false positives; higher ones do the opposite.
- Labels for some sheets began as an AI first pass that was checked and edited by me.

## Limitations

- Optical data: monsoon cloud limits what Sentinel-2 can see. In the 2024 test month,
  every scene from 1 to 21 July was about 95 to 100% cloudy (tile-level figures), so
  early July cannot be assessed. 26 July was the first clear date and is the one used
  here. 31 July was partly clear at tile level and was not evaluated for this box.
- "New water" is measured against a February low-water baseline, so it includes the
  normal seasonal rise, flooded paddy fields, and muddy or shallow water that the index
  can misjudge.
- Test box only. Not validated against ground data or other flood products.
- Do not use for operational decisions.

## Data and credits

Contains modified Copernicus Sentinel-2 data, accessed via Microsoft Planetary Computer.

[AI-assistant disclosure: see the report.]