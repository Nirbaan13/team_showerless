"""Synthetic fields adapted from the team's ml/benchmark.py and Ivan's ranker.py.

Source revisions are recorded in the training manifest. Real observations and
expected object coordinates are never read by this generator.
"""
import numpy as np
from scipy.ndimage import shift


def add_source(image, x, y, peak, sigma):
    radius = int(np.ceil(4 * sigma))
    left, right = max(0, int(x) - radius), min(image.shape[1], int(x) + radius + 1)
    top, bottom = max(0, int(y) - radius), min(image.shape[0], int(y) + radius + 1)
    if left >= right or top >= bottom:
        return
    yy, xx = np.ogrid[top:bottom, left:right]
    image[top:bottom, left:right] += peak * np.exp(-((xx - x)**2 + (yy - y)**2) / (2 * sigma**2))


def simulate(seed):
    rng = np.random.default_rng(seed)
    mode = 'noise_only' if seed % 10 == 0 else 'artifacts_only' if seed % 10 == 1 else 'injected'
    varied = seed % 3 != 0
    times = np.array([0., 1., 2.2, 3.1, 4.4, 5.3])
    noise = rng.uniform(.7, 1.8) if varied else 1.
    images = rng.normal(0, noise, (len(times), 96, 96))
    if mode == 'noise_only':
        return images, times, [], mode
    sigmas = rng.uniform(.8, 1.8, len(times)) if varied else np.full(len(times), 1.2)
    for _ in range(50):
        x, y = rng.uniform(4, 92, 2)
        brightness = rng.uniform(5, 45)
        variation = rng.uniform(.01, .5 if varied else .35)
        for image, sigma in zip(images, sigmas):
            add_source(image, x, y, brightness * rng.uniform(1 - variation, 1 + variation), sigma)
    truth = []
    if mode == 'injected':
        for _ in range(rng.integers(1, 4)):
            angle = rng.uniform(0, 2 * np.pi)
            velocity = np.array([np.cos(angle), np.sin(angle)]) * rng.uniform(.7 if varied else 1.4, 7 if varied else 5.)
            track = rng.uniform(32, 64, 2) + times[:, None] * velocity
            truth.append(track)
            brightness = rng.uniform(1., 10.) if varied else rng.uniform(1.5, 8.)
            dropped = rng.integers(len(times)) if varied and rng.random() < .3 else -1
            for epoch, (image, (x, y), sigma) in enumerate(zip(images, track, sigmas)):
                if epoch != dropped:
                    add_source(image, x, y, brightness * rng.uniform(.55 if varied else .85, 1.45 if varied else 1.15), sigma)
    for image in images:
        for _ in range(24):
            x, y = rng.integers(3, 93, 2)
            image[y, x] += rng.uniform(10, 40)
        for _ in range(24):
            x, y = rng.uniform(5, 91, 2)
            add_source(image, x, y, rng.uniform(3, 12), rng.uniform(.6, 2.1))
    if varied:
        offsets = rng.normal(0, .15, (len(times), 2))
        for epoch, (dx, dy) in enumerate(offsets):
            images[epoch] = shift(images[epoch], (dy, dx), order=1, mode='constant', cval=np.nan)
            for track in truth:
                track[epoch] += (dx, dy)
    gap = rng.integers(5, 89)
    images[rng.integers(len(images)), :, gap:gap + 3] = np.nan
    return images, times, truth, mode
