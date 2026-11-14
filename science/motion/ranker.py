"""Train the prototype Random Forest on simulated data only.

Simulation is shared with the initial ranking benchmark. Real fields and
ephemerides are never inputs to the model.
"""

import numpy as np

from detector import find_candidates

TRAINING_FIELDS = 80
MATCH_TOLERANCE = 1.5


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


def train_random_forest():
    from sklearn.ensemble import RandomForestClassifier

    features, labels = [], []
    for seed in range(TRAINING_FIELDS):
        images, times, truth = simulate(seed)
        # Keep the initial benchmark's detector and model settings fixed.
        for track in find_candidates(images, times, max_speed=7.0):
            positions = np.asarray(track.positions_xy)
            labels.append(any(np.all(np.linalg.norm(
                positions - path[list(track.epochs)], axis=1) <= MATCH_TOLERANCE)
                for path in truth))
            features.append(track.features())
    forest = RandomForestClassifier(n_estimators=150, min_samples_leaf=4,
                                    class_weight='balanced', random_state=42)
    return forest.fit(features, labels)


def random_forest_order(forest, tracks):
    if not tracks:
        return []
    scores = forest.predict_proba([track.features() for track in tracks])[:, 1]
    return np.argsort(-scores, kind='stable').tolist()
