import unittest
import numpy as np
from ml.pvusatov.experiments.v4.detection.information_gate import local_evidence

class InformationGate(unittest.TestCase):
    def test_missing_faint_wings_preserve_core_information(self):
        y,x=np.mgrid[-3:4,-3:4];kernel=np.exp(-(x*x+y*y)/(2*.8**2));kernel/=kernel.sum()
        full=10*kernel+2;full[0,:]=np.nan;full[-1,:]=np.nan
        snr,fraction=local_evidence(full,kernel,1.)
        self.assertGreater(fraction,.8);self.assertGreater(snr,0.)

    def test_missing_bright_core_rejects_lost_information(self):
        y,x=np.mgrid[-3:4,-3:4];kernel=np.exp(-(x*x+y*y)/(2*.8**2));kernel/=kernel.sum()
        image=10*kernel+2;image[2:5,2:5]=np.nan
        snr,fraction=local_evidence(image,kernel,1.)
        self.assertLess(fraction,.8);self.assertEqual(snr,0.)

    def test_full_patch_matches_amplitude_plus_constant_solution(self):
        y,x=np.mgrid[-3:4,-3:4];kernel=np.exp(-(x*x+y*y)/(2*.8**2));kernel/=kernel.sum()
        snr,fraction=local_evidence(10*kernel+2,kernel,1.)
        self.assertAlmostEqual(fraction,1.);self.assertAlmostEqual(snr,10*np.sqrt(np.sum((kernel-kernel.mean())**2)))
