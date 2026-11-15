"""Prospective peak-level physical gate; retains original measured peak values."""
from dataclasses import asdict
import unittest
import numpy as np
from ml_inference.detector import find_candidates
from ml.pvusatov.experiments.v4.detection.psf_gate import detect, SETTINGS


class GateTests(unittest.TestCase):
    def images(self):
        rng=np.random.default_rng(3801002);images=rng.normal(0,1,(4,40,40));yy,xx=np.indices((40,40))
        for e,image in enumerate(images):image+=25*np.exp(-((xx-10-4*e)**2+(yy-20)**2)/(2*.8**2))
        return images,np.arange(4.)

    def test_no_gate_is_identical_to_baseline(self):
        images,times=self.images();result=detect(images,times,gate_snr=None)
        self.assertIsNone(result['error'])
        self.assertEqual([asdict(t)for t in result['tracks']],[asdict(t)for t in find_candidates(images,times,**SETTINGS)])

    def test_strong_mover_survives_local_background_fit(self):
        images,times=self.images();result=detect(images,times,gate_snr=4.)
        self.assertIsNone(result['error']);self.assertTrue(result['tracks'])
        self.assertTrue(any(np.all(np.linalg.norm(np.array(t.positions_xy)-np.array([[10+4*e,20]for e in t.epochs]),axis=1)<=1.5)for t in result['tracks']))

    def test_very_high_gate_removes_peaks_before_linking(self):
        images,times=self.images();result=detect(images,times,gate_snr=1e6)
        self.assertTrue(sum(result['peaks_before'])>0);self.assertEqual(sum(result['peaks_after']),0);self.assertEqual(result['tracks'],[])

    def test_invalid_gate_and_physical_times_rejected(self):
        images,times=self.images()
        with self.assertRaises(ValueError):detect(images,times,gate_snr=-1.)
        with self.assertRaises(ValueError):detect(images,np.zeros(4),gate_snr=2.)


if __name__=='__main__':unittest.main()
