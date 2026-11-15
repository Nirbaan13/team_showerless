"""Whole-contract research parity on signed, masked, and empty-epoch images."""
import hashlib
from pathlib import Path
import unittest
import numpy as np
from ml_inference.detector import Candidate,difference_frames
from ml.pvusatov.experiments.v4.detection.features import extract_features as reference
from ml.pvusatov.experiments.v4.feature_performance.prototype import extract_features as batch

class Parity(unittest.TestCase):
    def test_all_thirty_float32_columns_ids_and_missingness_on_masked_signed_images(self):
        rng=np.random.default_rng(3800801);images=rng.normal(size=(6,32,32));images[4]=np.nan;images[:,:3,:]=np.nan
        outlier=rng.random(images.shape)<.05;bloom=np.zeros(images.shape,bool);bloom[:,15:17,15:17]=True
        times=np.asarray([0.,.01,.8,2.,3.,6.]);tracks=[]
        for n in [3,4,5,6]:
            for origin in [(1,1),(6,6),(14,15),(30,30)]:
                xy=tuple((origin[0]+i%2,origin[1]+i%3)for i in range(n))
                tracks.append(Candidate(tuple(range(n)),xy,tuple(np.arange(n)+4.3),1.,.4,1.))
        residuals=difference_frames(images,leave_one_out=True)
        kw=dict(psf_sigma=.8,outlier=outlier,bloom=bloom,residuals=residuals)
        a=reference(images,times,tracks,**kw);b=batch(images,times,tracks,**kw)
        np.testing.assert_array_equal(np.asarray(a['features_v4'],np.float32),np.asarray(b['features_v4'],np.float32))
        self.assertEqual(a['candidate_ids'],b['candidate_ids']);self.assertEqual(a['diagnostics'],b['diagnostics'])
        self.assertEqual(a['feature_names'],b['feature_names']);self.assertEqual(a['feature_contract_sha256'],b['feature_contract_sha256'])
        self.assertEqual(b['reference_feature_source_sha256'],a['feature_source_sha256'])
        self.assertNotEqual(b['feature_source_sha256'],a['feature_source_sha256'])
    def test_empty_candidates_preserve_shape_and_provenance_without_maps(self):
        images=np.zeros((3,8,8));times=np.arange(3.)
        a=reference(images,times,[]);b=batch(images,times,[])
        np.testing.assert_array_equal(a['features_v4'],b['features_v4']);self.assertEqual(b['diagnostics'],[])
        self.assertEqual(b['reference_feature_source_sha256'],a['feature_source_sha256'])
if __name__=='__main__':unittest.main()
