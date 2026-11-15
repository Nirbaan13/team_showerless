"""Independent transient competitor uses no truth or trained-model features."""
import unittest
import numpy as np
from ml.pvusatov.experiments.v4.detection.joint_competitor import search_maps

class Competitor(unittest.TestCase):
    def test_single_epoch_impulse_is_not_coherent_motion(self):
        maps=np.zeros((3,24,24),np.float32);maps[0,12,10]=30.
        tracks,diag=search_maps(maps,[0.,.5,1.],threshold=5.,max_endpoint_component_px=6.)
        self.assertFalse(tracks)
        self.assertEqual(diag['statistic'],'single_epoch_competitor')

    def test_coherent_separated_three_epoch_signal_survives(self):
        maps=np.zeros((3,24,24),np.float32)
        maps[0,12,5]=10.;maps[1,12,8]=10.;maps[2,12,11]=10.
        tracks,diag=search_maps(maps,[0.,.5,1.],threshold=5.,max_endpoint_component_px=6.)
        found=[t for t in tracks if t.positions_xy==((5,12),(8,12),(11,12))]
        self.assertTrue(found);self.assertGreater(found[0].search_statistic,10.)
        self.assertFalse(found[0].positions_measured);self.assertIsNone(found[0].learned_score)
