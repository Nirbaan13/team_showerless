import unittest
import numpy as np
from ml_inference.detector import Candidate,link_detections
from ml.pvusatov.experiments.v4.association_pilot.policies import build_hypotheses,pair_exclusive,near_duplicate

class Associations(unittest.TestCase):
    def test_baseline_reconstruction_matches_unchanged_linker(self):
        peaks=[np.asarray([[10+i,10,9,1],[30-i,30,6,1],[15,4+i,4,1]],float)for i in range(4)]
        times=np.asarray([0.,1.,2.,3.])
        pool,work=build_hypotheses(peaks,times,.5,60.,1.4,3)
        selected,account=pair_exclusive(pool)
        expected=link_detections(peaks,times,.5,60.,1.4,3)
        self.assertEqual([pool[i][1]for i in selected],expected)
        self.assertEqual(account['kept']+account['suppressed'],len(pool))
        self.assertGreater(work['link_checks'],0)

    def test_fixed_learned_order_can_preserve_a_competing_measured_arc(self):
        a=((0,0),(1,0),(2,0),(3,0));b=((0,0),(1,0),(2,1),(3,1))
        ca=Candidate((0,1,2,3),((0,0),(1,0),(2,0),(3,0)),(10.,)*4,1.,0.,1.)
        cb=Candidate((0,1,2,3),((0,0),(1,0),(2,2),(3,2)),(5.,)*4,1.,.4,1.)
        pool=[(a,ca),(b,cb)]
        original,_=pair_exclusive(pool);learned,stats=pair_exclusive(pool,priorities=np.asarray([.1,.9]))
        self.assertEqual(original,[0]);self.assertEqual(learned,[1])
        self.assertEqual(stats['kept']+stats['suppressed'],2)
        retained,_=near_duplicate(pool)
        self.assertEqual(set(retained),{0,1})

    def test_work_cap_withholds_partial_policy_results(self):
        c=Candidate((0,1,2),((0,0),(1,0),(2,0)),(5.,)*3,1.,0.,1.)
        with self.assertRaises(ValueError):pair_exclusive([(((0,0),(1,0),(2,0)),c)],max_ops=1)
