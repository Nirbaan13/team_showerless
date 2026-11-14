"""Find approximately linear tracks in registered, comparable image cutouts."""

import argparse
import json
from dataclasses import asdict, dataclass

import numpy as np
from scipy.ndimage import gaussian_filter, maximum_filter
from scipy.spatial import cKDTree


@dataclass(frozen=True)
class Candidate:
    epochs: tuple
    positions_xy: tuple
    snr: tuple
    speed_px_per_time: float
    fit_rms_px: float
    median_peak_ratio: float

    def features(self):
        return (
            len(self.epochs), self.fit_rms_px, np.median(self.snr),
            np.min(self.snr), np.std(self.snr) / np.mean(self.snr),
            self.median_peak_ratio,
        )


def _detect_peaks(residual, valid, sigma, min_snr, max_peaks, min_support=0.995):
    smoothed = gaussian_filter(np.where(valid, residual, 0), sigma)
    support = gaussian_filter(valid.astype(float), sigma)
    usable = (support >= min_support) & valid
    if not usable.any():
        return np.empty((0, 4))

    # Renormalize the filter where some of its pixels are masked.
    smoothed = np.divide(smoothed, support, out=np.zeros_like(smoothed), where=support > 0)
    center = np.median(smoothed[usable])
    noise = 1.4826 * np.median(np.abs(smoothed[usable] - center))
    if noise <= 0:
        return np.empty((0, 4))
    snr = (smoothed - center) / noise
    local_max = maximum_filter(np.where(usable, snr, -np.inf), size=3)
    y, x = np.where(usable & (snr >= min_snr) & (snr == local_max))
    order = np.argsort(-snr[y, x], kind="stable")[:max_peaks]
    y, x = y[order], x[order]
    peak_ratio = residual[y, x] / smoothed[y, x].clip(min=noise)
    return np.column_stack((x, y, snr[y, x], peak_ratio))


def find_candidates(images, times=None, *, min_snr=4.0, max_peaks=100,
                    psf_sigma=1.2, min_speed=0.5, max_speed=12.0,
                    match_radius=1.4, min_epochs=3, min_support=0.995):
    """Return tracks best first. Coordinates are zero-based (x, y).

    `images` has shape (epoch, y, x). Use NaN for masked pixels. Frames must
    share a pixel grid, with comparable passbands, flux scales and PSFs.
    Speeds are in pixels per input time unit (one epoch by default).
    `min_support` is the minimum valid fraction of the Gaussian filter.
    """
    images = np.asarray(images, dtype=float)
    if images.ndim != 3 or min_epochs < 3 or len(images) < min_epochs:
        raise ValueError("Expected (epoch, y, x) with at least min_epochs >= 3")
    times = np.arange(len(images), dtype=float) if times is None else np.asarray(times, dtype=float)
    if times.shape != (len(images),) or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError("Times must be finite, strictly increasing, and match the image count")
    settings = (min_snr, min_speed, max_speed, match_radius, psf_sigma, max_peaks)
    if not np.isfinite(settings).all() or min(settings) <= 0 or max_speed < min_speed:
        raise ValueError("Detection thresholds and sizes must be positive and speeds ordered")
    if not 0 < min_support <= 1:
        raise ValueError("Minimum filter support must be in (0, 1]")
    times = times - times[0]

    valid = np.isfinite(images)
    reference = np.zeros(images.shape[1:])
    # Include a pixel only if it has enough epochs to estimate a stationary background.
    reference_ok = valid.sum(axis=0) >= 3
    samples = np.where(valid[:, reference_ok], images[:, reference_ok], np.nan)
    reference[reference_ok] = np.nanmedian(samples, axis=0)
    peaks = [
        _detect_peaks(image - reference, mask & reference_ok, psf_sigma, min_snr, max_peaks, min_support)
        for image, mask in zip(images, valid)
    ]
    trees = [cKDTree(epoch[:, :2]) for epoch in peaks]

    tracks = {}
    for start in range(len(images) - min_epochs + 1):
        for end in range(start + min_epochs - 1, len(images)):
            dt = times[end] - times[start]
            middle = np.arange(start + 1, end)
            for first_index, first in enumerate(peaks[start][:, :2]):
                offsets = peaks[end][:, :2] - first
                speeds = np.linalg.norm(offsets, axis=1) / dt
                end_ids = np.flatnonzero((speeds >= min_speed) & (speeds <= max_speed))
                if not len(end_ids):
                    continue
                predictions = first + (times[middle, None, None] - times[start]) / dt * offsets[end_ids]
                matches = np.column_stack([
                    trees[epoch].query(prediction, distance_upper_bound=match_radius)[1]
                    for epoch, prediction in zip(middle, predictions)
                ])
                for end_id, middle_ids in zip(end_ids, matches):
                    links = [(start, first_index)]
                    links.extend((epoch, index) for epoch, index in zip(middle, middle_ids)
                                 if index < len(peaks[epoch]))
                    links.append((end, end_id))
                    if len(links) < min_epochs or tuple(links) in tracks:
                        continue
                    epochs, indexes = zip(*links)
                    detections = np.array([peaks[epoch][index] for epoch, index in zip(epochs, indexes)])
                    positions = detections[:, :2]
                    path_times = times[list(epochs)]
                    centered_times = path_times - path_times.mean()
                    mean_position = positions.mean(axis=0)
                    velocity = (centered_times @ positions) / (centered_times @ centered_times)
                    fit = mean_position + centered_times[:, None] * velocity
                    rms = np.sqrt(np.mean(np.sum((positions - fit) ** 2, axis=1)))
                    speed = np.linalg.norm(velocity)
                    if rms <= match_radius / 2 and min_speed <= speed <= max_speed:
                        tracks[tuple(links)] = Candidate(
                            tuple(map(int, epochs)), tuple(tuple(map(int, xy)) for xy in positions),
                            tuple(map(float, detections[:, 2])), float(speed), float(rms),
                            float(np.median(detections[:, 3])),
                        )

    ranked = sorted(tracks, key=lambda links: baseline_score(tracks[links]), reverse=True)
    seen_pairs = set()
    result = []
    for links in ranked:
        link_pairs = {(a, b) for offset, a in enumerate(links) for b in links[offset + 1:]}
        if seen_pairs.isdisjoint(link_pairs):
            result.append(tracks[links])
            seen_pairs.update(link_pairs)
    return result


def baseline_score(candidate):
    return len(candidate.epochs) * np.median(candidate.snr) / (1 + candidate.fit_rms_px)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cutouts", help="NPZ with images[epoch,y,x] and optional times[epoch]")
    parser.add_argument("--min-speed", type=float, default=0.5)
    parser.add_argument("--max-speed", type=float, default=12.0)
    parser.add_argument("--min-support", type=float, default=0.995)
    args = parser.parse_args()
    with np.load(args.cutouts) as data:
        candidates = find_candidates(data["images"], data.get("times"),
                                     min_speed=args.min_speed, max_speed=args.max_speed,
                                     min_support=args.min_support)
    print(json.dumps([asdict(candidate) for candidate in candidates], indent=2))


if __name__ == "__main__":
    main()
