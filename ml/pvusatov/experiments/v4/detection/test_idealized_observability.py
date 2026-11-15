import unittest
import numpy as np
from ml.pvusatov.experiments.v4.detection.idealized_observability import make_variants, draw_parent

class Idealized(unittest.TestCase):
    def test_missing_protocol_refuses_before_rng_or_model(self):
        from unittest.mock import patch
        with patch('numpy.random.default_rng',side_effect=AssertionError('RNG must remain unopened')):
            with self.assertRaises(ValueError):draw_parent(3802000)

    def test_noise_epochs_and_geometry_are_paired_across_amplitudes(self):
        noise=np.arange(8*64*64,dtype=float).reshape(8,64,64)/1000
        rows=list(make_variants(noise,.4,[31.25,32.1]))
        self.assertEqual(len(rows),20)
        by={(r['cadence'],r['epoch_count'],r['nominal_template_amplitude']):r for r in rows}
        for cadence in ['short','long']:
            a=by[cadence,8,0.];b=by[cadence,3,0.]
            np.testing.assert_array_equal(b['images'],a['images'][[0,3,7]])
            self.assertEqual(a['shared_noise_sha256'],b['shared_noise_sha256'])
            self.assertAlmostEqual(a['true_span_px'],1.4 if cadence == 'short' else 28.)
            for n in [3,8]:
                zero=by[cadence,n,0.]['images'];two=by[cadence,n,2.]['images'];four=by[cadence,n,4.]['images']
                np.testing.assert_allclose(four-zero,2*(two-zero),atol=1e-12)
