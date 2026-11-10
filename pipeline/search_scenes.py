"""
Step D1: ask the Planetary Computer catalogue which Sentinel-2 scenes exist
over our area and dates, and show how cloudy each one is.
Nothing is downloaded here, we only read the catalogue.
"""
import planetary_computer
from pystac_client import Client

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

# [west, south, east, north] in degrees longitude/latitude
BBOX = [94.10, 26.90, 94.30, 27.05]

# Date windows as "start/end"
WINDOWS = {
    "baseline (dry season)": "2024-01-15/2024-03-15",
    "event (monsoon)": "2024-07-01/2024-07-31",
}


def find_scenes(client, date_window):
    """Return Sentinel-2 L2A scenes over BBOX in the window, oldest first."""
    search = client.search(
        collections=["sentinel-2-l2a"],
        bbox=BBOX,
        datetime=date_window,
    )
    return sorted(search.item_collection(), key=lambda item: item.datetime)


def main():
    client = Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)

    for name, window in WINDOWS.items():
        scenes = find_scenes(client, window)
        print(f"\n=== {name}: {window} ===")
        print(f"Scenes found: {len(scenes)}")
        if not scenes:
            continue

        print(f"{'date':<12}{'tile':<8}{'cloud %':>8}")
        for scene in scenes:
            cloud = scene.properties.get("eo:cloud_cover", float("nan"))
            tile = scene.properties.get("s2:mgrs_tile", "?")
            print(f"{scene.datetime.date()!s:<12}{tile:<8}{cloud:>8.1f}")

        clear = [s for s in scenes if s.properties.get("eo:cloud_cover", 100) < 20]
        print(f"Scenes with under 20% cloud: {len(clear)} of {len(scenes)}")


if __name__ == "__main__":
    main()