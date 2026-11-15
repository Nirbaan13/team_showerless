import unittest
import numpy as np
from ml.pvusatov.experiments.v4.operating_points.analyze import paired_interval

class PairedIntervals(unittest.TestCase):
    def test_constant_whole_field_differences_have_degenerate_interval(self):
        result=paired_interval(np.ones(100),resamples=100)
        self.assertEqual(result['delta_known_objects_per_field'],1.)
        self.assertEqual(result['interval95'],[1.,1.])

    def test_failed_or_missing_field_cannot_be_silently_removed(self):
        with self.assertRaises(ValueError):paired_interval(np.asarray([1.,np.nan]),resamples=100)
