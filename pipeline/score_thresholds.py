"""
Score MNDWI thresholds against the hand labels.

Reads data/labelling/labels.csv (id, label: w = water, l = land, u = unsure) and
data/labelling/points_private.csv (id, row, col, mndwi). Unsure points are not scored.

For each threshold t, a point is predicted "water" if its MNDWI > t. We count how many
labelled points are right, and print precision, recall, F1 and IoU.

IMPORTANT: the 60 points were drawn evenly from five MNDWI ranges, so they over-represent
ambiguous pixels. These scores compare thresholds with each other. They are NOT the
accuracy of the map over the whole area.

Run from the project folder:  python -m pipeline.score_thresholds
"""
from pathlib import Path

import pandas as pd

LABEL_DIR = Path("data/labelling")
THRESHOLDS = [-0.2, -0.1, -0.05, 0.0, 0.05, 0.1, 0.2]


def load_points():
    """Join the hand labels to the sampled points; drop unsure and unlabelled ones."""
    # header=None + to_numeric makes this work with or without a header row
    labels = pd.read_csv(LABEL_DIR / "labels.csv", header=None, names=["id", "label"])
    labels["id"] = pd.to_numeric(labels["id"], errors="coerce")
    labels = labels.dropna(subset=["id"]).astype({"id": int})
    labels["label"] = labels["label"].astype(str).str.strip().str.lower()

    points = pd.read_csv(LABEL_DIR / "points_private.csv")
    data = labels.merge(points[["id", "mndwi"]], on="id", how="inner")
    return data


def score(data, threshold):
    """Confusion counts and scores for one threshold (water = positive class)."""
    truth = data["label"] == "w"
    pred = data["mndwi"] > threshold
    tp = int((truth & pred).sum())
    fp = int((~truth & pred).sum())
    fn = int((truth & ~pred).sum())
    tn = int((~truth & ~pred).sum())
    precision = tp / (tp + fp) if tp + fp else float("nan")
    recall = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * precision * recall / (precision + recall) if tp else float("nan")
    iou = tp / (tp + fp + fn) if tp + fp + fn else float("nan")
    return {"threshold": threshold, "TP": tp, "FP": fp, "FN": fn, "TN": tn,
            "precision": precision, "recall": recall, "F1": f1, "IoU": iou}


def main():
    data = load_points()
    counts = data["label"].value_counts().to_dict()
    print(f"labelled points: {len(data)} | counts: {counts}")
    scored = data[data["label"].isin(["w", "l"])]
    print(f"scored (water + land only): {len(scored)}\n")
    table = pd.DataFrame([score(scored, t) for t in THRESHOLDS])
    print(table.round(2).to_string(index=False))


if __name__ == "__main__":
    main()