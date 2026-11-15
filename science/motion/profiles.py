"""Physical search bounds for qualified historical stacks, independent of targets."""

import math


def proper_motion_profile(pixel_scale_arcsec):
    """Convert the 0.1–30 arcsec/Julian-year profile to pixels per elapsed hour."""
    pixel_scale_arcsec = float(pixel_scale_arcsec)
    if not math.isfinite(pixel_scale_arcsec) or pixel_scale_arcsec <= 0:
        raise ValueError('A finite positive pixel scale in arcsec/pixel is required')
    hours_per_year = 365.25 * 24
    return {
        'name': 'historical-proper-motion',
        'min_speed': 0.1 / pixel_scale_arcsec / hours_per_year,
        'max_speed': 30.0 / pixel_scale_arcsec / hours_per_year,
        'speed_unit': 'pixels/hour',
        'time_unit': 'hours',
        'proper_motion_arcsec_per_year': {'min': 0.1, 'max': 30.0},
        'pixel_scale_arcsec': pixel_scale_arcsec,
        'hours_per_year': hours_per_year,
    }
