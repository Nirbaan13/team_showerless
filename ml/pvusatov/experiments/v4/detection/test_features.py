"""Observable-only physical features; controlled pixels and measured tracks."""
from dataclasses import dataclass
import copy
import unittest
import numpy as np

from ml.pvusatov.experiments.v4.detection.features import FEATURE_NAMES, extract_features


@dataclass
class Track:
    epochs: tuple
    positions_xy: tuple
    snr: tuple = (8., 8., 8., 8.)
    def features(self): return (len(self.epochs), .1, 8., 7., .1, 2.)


def case(sign=1., static=False, sigma=.8):
    rng = np.random.default_rng(42001)
    images = rng.normal(0, 1., (4, 40, 40)); yy, xx = np.indices((40, 40))
    positions = [(12.+4.*i, 20.) for i in range(4)]
    if static: positions = [(20., 20.)]*4
    for image, (x, y) in zip(images, positions):
        image += sign*25*np.exp(-((xx-x)**2+(yy-y)**2)/(2*sigma*sigma))
    return images, np.arange(4.)*.5, Track(tuple(range(4)), tuple(positions))


class PhysicalFeatures(unittest.TestCase):
    def value(self, result, name): return result['features_v4'][0, FEATURE_NAMES.index(name)]

    def test_order_original_six_empty_and_no_mutation(self):
        images,times,track=case(); before=images.copy(); tracks=copy.deepcopy(track)
        result=extract_features(images,times,[track]);self.assertEqual(result['features_v4'].shape,(1,30))
        np.testing.assert_array_equal(result['features_v4'][0,:6],track.features())
        np.testing.assert_array_equal(images,before);self.assertEqual(track,tracks)
        empty=extract_features(images,times,[]);self.assertEqual(empty['features_v4'].shape,(0,30))
        self.assertEqual(len(set(FEATURE_NAMES)),30)

    def test_moving_and_static_motion_evidence_are_distinct(self):
        a,t,track=case();moving=extract_features(a,t,[track]);b,u,stationary=case(static=True)
        static=extract_features(b,u,[stationary])
        self.assertGreater(self.value(moving,'moving_minus_static_coadd_snr2'),20.)
        self.assertGreater(self.value(moving,'velocity_snr_proxy'),3.)
        self.assertAlmostEqual(self.value(static,'motion_delta_chi2_proxy'),0.)
        self.assertAlmostEqual(self.value(static,'moving_minus_static_coadd_snr2'),0.)

    def test_negative_measurements_retain_their_sign(self):
        a,t,track=case(sign=-1.);result=extract_features(a,t,[track])
        self.assertLess(self.value(result,'residual_psf_snr_median'),0.)
        self.assertEqual(self.value(result,'residual_positive_epoch_fraction'),0.)

    def test_broad_morphology_has_larger_template_residual(self):
        a,t,track=case();b,_,_=case(sigma=2.)
        narrow=extract_features(a,t,[track]);broad=extract_features(b,t,[track])
        self.assertGreater(self.value(broad,'residual_psf_reduced_chi2_median'),self.value(narrow,'residual_psf_reduced_chi2_median'))

    def test_mask_support_flags_undefined_instead_of_claiming_measurement(self):
        a,t,track=case();a[:]=np.nan;result=extract_features(a,t,[track])
        self.assertTrue(np.isfinite(result['features_v4']).all())
        self.assertEqual(self.value(result,'photometry_summary_valid'),0.)
        self.assertEqual(self.value(result,'photometry_epoch_fraction'),0.)
        self.assertTrue(result['diagnostics'][0]['missing_statistics'])

    def test_outlier_and_bloom_masks_have_explicit_availability(self):
        a,t,track=case();outlier=np.ones(a.shape,bool);bloom=np.zeros(a.shape,bool)
        absent=extract_features(a,t,[track]);present=extract_features(a,t,[track],outlier=outlier,bloom=bloom)
        self.assertEqual(self.value(absent,'quality_masks_available'),0.)
        self.assertEqual(self.value(present,'quality_masks_available'),1.)
        self.assertEqual(self.value(present,'outlier_patch_fraction_mean'),1.)
        self.assertEqual(self.value(present,'bloom_patch_fraction_mean'),0.)

    def test_covariance_uses_actual_matched_time_span(self):
        a,t,track=case();track.epochs=(0,2,3);track.positions_xy=(track.positions_xy[0],track.positions_xy[2],track.positions_xy[3])
        result=extract_features(a,t,[track]);self.assertEqual(self.value(result,'matched_timespan_hours'),1.5)
        self.assertEqual(self.value(result,'linked_epoch_fraction'),.75)

    def test_reject_invalid_shapes_times_and_candidate_indices(self):
        a,t,track=case()
        with self.assertRaises(ValueError):extract_features(a,[0.,0.,1.,2.],[track])
        track.epochs=(0,1,2,9)
        with self.assertRaises(ValueError):extract_features(a,t,[track])
        with self.assertRaises(ValueError):extract_features(a,t,[],outlier=np.zeros((1,2,3)))


if __name__=='__main__':unittest.main()
