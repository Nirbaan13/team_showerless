"""Train a candidate ranker on simulated fields and evaluate it on held-out data."""

import argparse
import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score

from detector import baseline_score, find_candidates


def add_source(image, x, y, peak, sigma):
    radius = int(np.ceil(4 * sigma))
    left, right = max(0, int(x) - radius), min(image.shape[1], int(x) + radius + 1)
    top, bottom = max(0, int(y) - radius), min(image.shape[0], int(y) + radius + 1)
    yy, xx = np.ogrid[top:bottom, left:right]
    image[top:bottom, left:right] += peak * np.exp(-((xx - x)**2 + (yy - y)**2) / (2 * sigma**2))


def simulate(seed):
    rng = np.random.default_rng(seed)
    times = np.array([0.0, 1.0, 2.2, 3.1, 4.4, 5.3])
    images = rng.normal(0, 1, (len(times), 96, 96))
    for _ in range(50):
        x, y = rng.uniform(4, 92, 2)
        brightness = rng.uniform(5, 45)
        variation = rng.uniform(0.01, 0.35)
        for image in images:
            add_source(image, x, y, brightness * rng.uniform(1 - variation, 1 + variation), 1.2)

    truth = []
    for _ in range(rng.integers(0, 4)):
        angle = rng.uniform(0, 2 * np.pi)
        velocity = np.array([np.cos(angle), np.sin(angle)]) * rng.uniform(1.4, 5.0)
        track = rng.uniform(32, 64, 2) + times[:, None] * velocity
        truth.append(track)
        brightness = rng.uniform(1.5, 8)
        for image, (x, y) in zip(images, track):
            add_source(image, x, y, brightness * rng.uniform(0.85, 1.15), 1.2)

    # Include bright one-frame artifacts, transient blobs and a masked strip.
    for image in images:
        for _ in range(24):
            x, y = rng.integers(3, 93, 2)
            image[y, x] += rng.uniform(10, 40)
        for _ in range(24):
            x, y = rng.uniform(5, 91, 2)
            add_source(image, x, y, rng.uniform(3, 12), rng.uniform(0.6, 2.1))
    gap = rng.integers(5, 89)
    images[rng.integers(len(images)), :, gap:gap + 3] = np.nan
    return images, times, truth


def detections_for_field(seed):
    images, times, truth = simulate(seed)
    tracks = find_candidates(images, times, max_speed=7.0)
    matches = []
    for track in tracks:
        positions = np.array(track.positions_xy)
        distances = [np.linalg.norm(positions - path[list(track.epochs)], axis=1) for path in truth]
        matching = [index for index, distance in enumerate(distances) if np.all(distance <= 1.5)]
        matches.append(min(matching, key=lambda i: np.mean(distances[i])) if matching else -1)
    return tracks, np.array(matches, dtype=int), len(truth)


def evaluate(fields, score, top_k):
    injected = recovered_at_k = found = false_at_k = 0
    labels, scores = [], []
    for tracks, matches, truth_count in fields:
        injected += truth_count
        if not tracks:
            continue
        ratings = score(tracks)
        order = np.argsort(-ratings, kind="stable")
        selected = matches[order[:top_k]]
        recovered = len(set(selected) - {-1})
        recovered_at_k += recovered
        found += len(set(matches) - {-1})
        false_at_k += int(np.count_nonzero(selected == -1))
        labels.extend(matches >= 0)
        scores.extend(ratings)
    return {
        "injected_tracks": injected,
        "recovered_before_ranking": found,
        "recovered_in_top_k": recovered_at_k,
        "top_k_recall": round(recovered_at_k / injected, 4),
        "false_tracks_in_top_k": false_at_k,
        "false_tracks_per_field_in_top_k": round(false_at_k / len(fields), 4),
        "track_average_precision": round(average_precision_score(labels, scores), 4),
    }


def evaluate_spherex(forest):
    fixture = Path(__file__).with_name("spherex_3i_atlas.npz")
    with np.load(fixture) as data:
        tracks = find_candidates(data["images"], data["times"], max_speed=60, min_support=0.8)
        expected = data["expected_xy"]
    if not tracks:
        raise SystemExit("The detector found no candidates in the SPHEREx exposures.")

    forest_scores = forest.predict_proba([track.features() for track in tracks])[:, 1]
    forest_order = np.argsort(-forest_scores, kind="stable")
    forest_ranks = {index: rank for rank, index in enumerate(forest_order, 1)}
    matches = []
    for index, track in enumerate(tracks):
        offsets = np.linalg.norm(np.array(track.positions_xy) - expected[list(track.epochs)], axis=1)
        if offsets.max() <= 1.5:
            matches.append({
                "baseline_rank": index + 1,
                "random_forest_rank": forest_ranks[index],
                "matched_exposures": len(track.epochs),
                "max_offset_px": round(float(offsets.max()), 3),
            })
    return {
        "test_object": "3I/ATLAS",
        "exposures": len(expected),
        "candidates": len(tracks),
        "ephemeris_matches": matches,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-fields", type=int, default=80)
    parser.add_argument("--test-fields", type=int, default=40)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--spherex", action="store_true", help="Evaluate on the real 3I/ATLAS exposures")
    args = parser.parse_args()
    if min(args.train_fields, args.test_fields, args.top_k) < 1:
        parser.error("Field counts and top-k must be positive")

    train = [detections_for_field(seed) for seed in range(args.train_fields)]
    features = [track.features() for tracks, _, _ in train for track in tracks]
    labels = [match >= 0 for _, matches, _ in train for match in matches]
    if len(set(labels)) < 2:
        parser.error("Increase the number of training fields to include both classes")

    forest = RandomForestClassifier(n_estimators=150, min_samples_leaf=4,
                                    class_weight="balanced", random_state=42)
    forest.fit(features, labels)
    if args.spherex:
        print(json.dumps({"simulated_training_fields": len(train), **evaluate_spherex(forest)}, indent=2))
        return

    test = [detections_for_field(seed) for seed in range(100_000, 100_000 + args.test_fields)]
    if sum(field[2] for field in test) == 0:
        parser.error("Increase the number of test fields to include injected tracks")
    print(json.dumps({
        "train_fields": len(train),
        "test_fields": len(test),
        "top_k_per_field": args.top_k,
        "baseline": evaluate(test, lambda tracks: np.array([baseline_score(t) for t in tracks]), args.top_k),
        "random_forest": evaluate(test, lambda tracks: forest.predict_proba([t.features() for t in tracks])[:, 1],
                                  args.top_k),
    }, indent=2))


if __name__ == "__main__":
    main()
