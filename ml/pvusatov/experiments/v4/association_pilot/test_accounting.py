"""Truth/cohort and duplicate accounting regression, not detector-selection tests."""
import unittest
import numpy as np
from ml_inference.detector import Candidate
from ml.pvusatov.experiments.v4.association_pilot.study import finish
from ml.pvusatov.experiments.v4.association_pilot.policies import near_duplicate

class Accounting(unittest.TestCase):
    def test_native_unknown_and_policy_specific_control_attribution_preserved(self):
        a=Candidate((0,1,2),((0,0),(1,0),(2,0)),(5.,)*3,1.,0.,1.)
        b=Candidate((0,1,2),((0,4),(1,4),(2,4)),(6.,)*3,1.,0.,1.)
        policy=lambda ids:dict(indices=ids,accounting=dict(complete=True),error=None,cpu_seconds=0.)
        p=dict(tracks=[a,b],scores=dict(C13=[.6,.7],C596=[.8,.3]),policies=dict(legacy=policy([1]),learned_pair=policy([0]),near_duplicate=policy([0,1])))
        controls={'4.0':dict(tracks=[a,b],policies=dict(legacy=policy([0]),learned_pair=policy([1]),near_duplicate=policy([0,1])))}
        out=finish({'4.0':p},[np.asarray(a.positions_xy)],True,controls)['4.0']
        self.assertEqual(out['matches'],[0,-2])
        self.assertEqual(out['full_pool_detected'],1)
        self.assertFalse(out['policies']['legacy']['attribution_eligible'])
        self.assertTrue(out['policies']['learned_pair']['attribution_eligible'])
        self.assertEqual(out['policies']['legacy']['models']['C596']['detected'],0)
        self.assertEqual(out['policies']['learned_pair']['models']['C596']['detected'],1)
        self.assertEqual(out['policies']['near_duplicate']['models']['C596']['top3'],1)
        self.assertEqual(out['policies']['near_duplicate']['unknown_rows'],1)
        self.assertNotIn(-1,out['matches'])

    def test_diversity_policy_withholds_incomplete_work(self):
        a=Candidate((0,1,2),((0,0),(1,0),(2,0)),(5.,)*3,1.,0.,1.)
        with self.assertRaisesRegex(ValueError,'partial'):
            near_duplicate([(((0,0),(1,0),(2,0)),a)],max_ops=1)
