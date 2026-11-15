"""Unit tests for the SPHEREx cutout and cleaning pipeline worker."""

import unittest
from pathlib import Path
import numpy as np

from spherex.cleaning import build_mask, allowed_bits, OUTLIER_BIT, SOURCE_BIT, BLOOM_BIT
from spherex.query import cutout, DEFAULT


class PipelineTests(unittest.TestCase):
    def test_build_mask_clean_signal(self):
        flags = [0, 0, 0]
        signal = [10.0, 20.0, 30.0]
        variance = [1.0, 1.0, 1.0]
        mask = build_mask(flags, signal, variance)
        self.assertFalse(np.any(mask))

    def test_build_mask_flagged_pixels(self):
        # Pixel with bad bit (e.g. 1 << 5)
        flags = [1 << 5, 0]
        signal = [10.0, 20.0]
        variance = [1.0, 1.0]
        mask = build_mask(flags, signal, variance)
        self.assertTrue(mask[0])
        self.assertFalse(mask[1])

    def test_build_mask_nan_and_negative_variance(self):
        flags = [0, 0, 0]
        signal = [10.0, np.nan, 30.0]
        variance = [1.0, 1.0, -0.5]
        mask = build_mask(flags, signal, variance)
        self.assertFalse(mask[0])
        self.assertTrue(mask[1])  # NaN signal must be masked
        self.assertTrue(mask[2])  # Negative variance must be masked

    def test_allowed_bits(self):
        self.assertEqual(allowed_bits(retain_outliers=False), SOURCE_BIT)
        self.assertEqual(allowed_bits(retain_outliers=True), SOURCE_BIT | OUTLIER_BIT)

    def test_cutout_bad_url_fails_gracefully(self):
        # Verify cutout does not raise unhandled NameError or crash on network failure
        res = cutout("http://127.0.0.1:54321/nonexistent.fits", Path("/tmp/nonexistent.fits"), retries=1)
        self.assertTrue(res.startswith("failure:"))

    def test_default_collection_present(self):
        self.assertTrue(DEFAULT.startswith("spherex_"))


if __name__ == "__main__":
    unittest.main()
