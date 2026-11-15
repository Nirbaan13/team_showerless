"""Coverage-aware native latents with the immutable RNG and injection arithmetic.

No frame, time or trial is removed. Only completely empty registered frames
are excluded from the background MAD reference; invalid nonempty frames fail.
Legacy constants/identity/error helpers are supplied explicitly by the caller.
"""
from __future__ import annotations

import math
import numpy as np


def native_latents(parent, stack, natives, science, shape, legacy):
    """Yield the legacy (identity, images, positions, error) trial interface."""
    rng = np.random.default_rng(parent['seed']); h, w = shape
    nonempty = [bool(np.isfinite(image).any()) for image in stack.images]
    with np.errstate(over='ignore', invalid='ignore'):
        noise = np.asarray([1.4826 * np.median(abs(v - np.median(v)))
                            for image, usable in zip(stack.images, nonempty) if usable
                            for v in [image[np.isfinite(image)]]])
    setup_error = None
    if len(noise) < 3 or not np.isfinite(noise).all() or np.any(noise <= 0):
        setup_error = legacy._error('background_normalization', ValueError(
            'at least three nonempty native epochs with positive finite background MAD required'))
    for speed in legacy.SPEEDS:
        for direction in range(6):
            origin = rng.uniform([8, 8], [w - 8, h - 8]); angle = rng.uniform(0, 2 * np.pi)
            velocity = speed * np.array([np.cos(angle), np.sin(angle)])
            trajectory_id = f'{speed:g}-{direction}'
            positions = origin + stack.times[:, None] * velocity
            usable = []; epsf = []; response = None; typical = None; error = setup_error
            geometry_known = list(stack.images.shape[1:]) == shape
            if geometry_known:
                for image, (x, y) in zip(stack.images, np.rint(positions).astype(int)):
                    usable.append(bool(0 <= x < w and 0 <= y < h and np.isfinite(image[y, x])))
            if error is None:
                try:
                    projected = [science.project_response(n, stack.grid, xy) for n, xy in zip(natives, positions)]
                    response = np.asarray([p[0] for p in projected]); epsf = [p[1] for p in projected]
                    peaks = np.max(response, axis=(1, 2)); covered = peaks[np.asarray(usable) & (peaks > 0)]
                    supported = covered if len(covered) else peaks[peaks > 0]
                    if not len(supported):
                        fallback = [science.project_response(n, stack.grid, np.array([w / 2, h / 2]))[0].max() for n in natives]
                        supported = np.asarray([v for v in fallback if v > 0])
                    typical = float(np.median(supported)) if len(supported) else 1.
                    if not math.isfinite(typical) or typical <= 0:
                        raise ValueError('invalid supported response normalization')
                except Exception as exc:
                    error = legacy._error('injection_projection', exc)
            for brightness in legacy.BRIGHTNESS:
                flux = brightness * float(np.median(noise)) / typical if error is None else None
                identity = legacy._latent_id(parent, trajectory_id, speed, direction, brightness,
                    origin, velocity, positions, flux, usable, epsf, geometry_known)
                identity.update(noise_reference_usable_epoch_count=len(noise),
                    noise_reference_policy='all_nonempty_registered_epochs_positive_finite_mad_min3')
                images = None; trial_error = error
                if trial_error is None:
                    try:
                        images = science.add_injection(stack.images, response, flux)
                        for image in images:
                            if not np.isnan(image).all():
                                image -= np.nanmedian(image)
                    except Exception as exc:
                        trial_error = legacy._error('injection_addition', exc)
                yield identity, images, positions, trial_error
