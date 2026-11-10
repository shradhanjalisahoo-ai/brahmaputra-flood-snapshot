# Brahmaputra Flood Snapshot (EO-AI Role 01: R5 / S1 / D2 / T1)

Sentinel-2 change detection of surface water, pre-monsoon vs. post-rain, over a small
Brahmaputra floodplain AOI in Assam. Built for a district disaster-response desk.

## Setup
```bash
git clone <your-repo-url> && cd <repo>
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
Rasterio ships binary wheels on Linux/macOS/Windows. If install fails, use conda-forge.

## Run the app
```bash
streamlit run app.py
```
Opens at http://localhost:8501. With no data in `data/outputs/` the app shows a clearly
labelled DEMO. Once the pipeline has run it shows real results.

## Pipeline (end to end)
```bash
python -m pipeline.run --aoi aoi.geojson --pre 2026-01-01/2026-03-15 --post 2026-07-01/2026-09-15
```
Writes `data/outputs/change_map.tif`, `data/outputs/summary.json`, and the STAC
catalogue / GeoParquet feature table under `data/catalog/`.
(Pipeline module is the next piece to implement; update this section to match what you build.)

## Layout
```
app.py            Streamlit asset
pipeline/         ingest -> mask -> index -> change -> catalogue
data/outputs/     map + summary consumed by the app
data/catalog/     STAC items + GeoParquet features
tests/            unit tests (masking, index, change logic)
```

## Data
Sentinel-2 L2A via Microsoft Planetary Computer STAC (no account needed for reads
via `planetary-computer` signing). Public data only.