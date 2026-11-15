"""Typed TBD hypotheses use measured images and metadata, never target coordinates."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from ml_inference.detector import DetectionLimitError
from ml.pvusatov.experiments.v4.detection.joint_tracking import (
    library,plan_search,search_maps,automatic_groups,round_offsets)


class JointTracking(unittest.TestCase):
    def test_clusters_are_deterministic_from_times_only(self):
        self.assertEqual(automatic_groups([0.,.1,.2,5.,5.1,5.2,12.]),[(0,1,2,3,4,5,6),(0,1,2),(3,4,5)])
        self.assertEqual(automatic_groups([0.,.1,.2]),[(0,1,2)])

    def test_plan_exposes_hypotheses_and_work_before_pixel_search(self):
        plan=plan_search([0.,.5,1.],(16,16),max_endpoint_component_px=6.)
        self.assertGreater(plan['velocity_hypotheses'],0);self.assertGreater(plan['planned_pixel_epoch_tests'],0)
        self.assertEqual(plan['planned_pixel_epoch_tests'],3*plan['anchor_velocity_tests'])

    def test_consistent_half_away_rounding_and_typed_fitted_path(self):
        np.testing.assert_array_equal(round_offsets([-1.5,-.5,.5,1.5]),[-2,-1,1,2])
        maps=np.zeros((3,16,16),np.float32);maps[0,6,5]=20.;maps[1,6,8]=20.;maps[2,6,10]=20.
        tracks,diag=search_maps(maps,[0.,.5,1.],max_endpoint_component_px=6.,threshold=5.)
        found=[t for t in tracks if t.positions_xy==((5,6),(8,6),(10,6))]
        self.assertTrue(found);self.assertFalse(found[0].positions_measured)
        self.assertEqual(found[0].kind,'joint_template_hypothesis');self.assertFalse(hasattr(found[0],'features'))
        self.assertTrue(diag['hypothesis_search_complete'])

    def test_all_masked_maps_create_no_hypothesis(self):
        tracks,diag=search_maps(np.full((3,16,16),np.nan,np.float32),[0.,.5,1.],max_endpoint_component_px=6.)
        self.assertEqual(tracks,[]);self.assertEqual(diag['valid_hypothesis_tests'],0)

    def test_null_maximum_is_recorded_even_below_proposal_threshold(self):
        tracks,diag=search_maps(np.zeros((3,16,16),np.float32),[0.,.5,1.],max_endpoint_component_px=6.)
        self.assertEqual(tracks,[]);self.assertEqual(diag['maximum_search_statistic'],0.)

    def test_work_cap_rejects_before_backend_pixel_search(self):
        lib=library()
        with patch.object(lib,'search',side_effect=AssertionError('pixel search must not run')):
            with self.assertRaises(DetectionLimitError):search_maps(np.zeros((3,16,16),np.float32),[0.,.5,1.],max_work=1)

    def test_fresh_scratch_directory_is_created_before_compilation(self):
        with tempfile.TemporaryDirectory()as d:
            scratch=Path(d)/'missing-parent'/'scratch'
            lib=library(scratch);self.assertTrue(scratch.is_dir());self.assertTrue(hasattr(lib,'plan'))


if __name__=='__main__':unittest.main()
