"""
One command, end to end:

    python -m pipeline.run
    python -m pipeline.run --pre 2024-02-12 --post 2024-07-26

Step 1 downloads, cloud-masks and compares the two dates (water_change.py).
Step 2 registers the run in the STAC catalogue and the GeoParquet table (catalogue.py).
A run is identified by its two dates: a new --post date adds a run, the same dates replace it.
"""
import argparse

from pipeline import catalogue, water_change


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--pre", default=water_change.DAYS["baseline"],
                        help="baseline date, YYYY-MM-DD")
    parser.add_argument("--post", default=water_change.DAYS["event"],
                        help="event date, YYYY-MM-DD")
    args = parser.parse_args()

    water_change.DAYS["baseline"] = args.pre
    water_change.DAYS["event"] = args.post

    print(f"[1/2] change map: {args.pre} -> {args.post}")
    water_change.main()
    print("[2/2] catalogue and feature table")
    catalogue.main()


if __name__ == "__main__":
    main()