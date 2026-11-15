"""DEVELOPMENT orchestration guards; no final inputs."""
import unittest
from types import SimpleNamespace
import numpy as np
from ml.pvusatov.experiments.v4.detection.pilot_joint_tracking import evaluate, merge_groups, select_native

class PilotGuards(unittest.TestCase):
    def test_spatial_recovery_does_not_manufacture_motion(self):
        t=SimpleNamespace(epochs=(0,1,2),positions_xy=((2,2),(3,2),(4,2)))
        truth=[np.asarray([[3,2],[3.01,2],[3.02,2]])]
        r=evaluate([t],truth,True)
        self.assertEqual(r['detected'],1);self.assertEqual(r['resolved_detected'],0)
        self.assertEqual(r['matches'],[0]);self.assertAlmostEqual(r['matched_true_spans_px'][0],.02)

    def test_truth_matching_requires_every_actual_epoch(self):
        t=SimpleNamespace(epochs=(0,2,3),positions_xy=((2,2),(2,2),(2,2)))
        r=evaluate([t],[np.asarray([[2,2],[99,99],[2,2],[4,2]])],True)
        self.assertEqual(r['matches'],[-2]);self.assertEqual(r['detected'],0)

    def test_windows_merge_only_when_actual_common_paths_agree(self):
        def t(ep,xy,s):return SimpleNamespace(epochs=ep,positions_xy=xy,search_statistic=s)
        a=t((0,1,2),((2,2),)*3,8);b=t((0,1,2,3),((2,2),)*4,7)
        c=t((0,1,2),((9,2),)*3,6)
        self.assertEqual(merge_groups([a,b,c],5)[0],[a,c])

    def test_native_subset_fixed_by_metadata_across_all_speeds(self):
        fields=[dict(truth_kind='moving_injection',direction_id=d,brightness=b,speed_px_hour=s)for s in [.01,.03,.1,.3,1,4,10,25,50]for d in range(6)for b in [3,6,12,24,48]]
        self.assertEqual(len(select_native(fields)),27)
        self.assertEqual({f['speed_px_hour']for f in select_native(fields)},{.01,.03,.1,.3,1,4,10,25,50})

class MatchingAccounting(unittest.TestCase):
    def test_multiple_candidate_hypotheses_do_not_multiply_one_truth(self):
        t=SimpleNamespace(epochs=(0,1,2),positions_xy=((1,1),(2,1),(3,1)))
        result=evaluate([t,t],[np.asarray(t.positions_xy)],False)
        self.assertEqual(result['matches'],[0,0]);self.assertEqual(result['detected'],1)
        self.assertEqual(result['top3'],1)

    def test_only_matched_epochs_define_true_span(self):
        t=SimpleNamespace(epochs=(0,1,2),positions_xy=((1,1),(2,1),(3,1)))
        truth=np.asarray([[1,1],[2,1],[3,1],[100,100]])
        result=evaluate([t],[truth],False)
        self.assertEqual(result['matched_true_spans_px'],[2.]);self.assertEqual(result['resolved_detected'],0)
