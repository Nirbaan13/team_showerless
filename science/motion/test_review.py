"""Regression checks against the real, labeled IRSA observation sequences."""

import unittest
from pathlib import Path

import numpy as np

from detector import difference_frames
from ranker import train_random_forest
from review import make_review

CASES = Path(__file__).with_name('cases')


class RealObservationTests(unittest.TestCase):
    def test_per_frame_reference_recovers_d2_across_a_mask_gap(self):
        report = make_review(CASES / 'december-d2.npz')
        checks = report['comparison']
        self.assertIsNone(checks['shared_median']['match'])
        self.assertIsNone(checks['outliers_masked']['match'])
        self.assertEqual(checks['leave_one_out']['match']['rank'], 1)
        self.assertEqual(report['tracks'][0]['epochs'], (0, 1, 2))
        self.assertLess(report['tracks'][0]['max_offset_px'], 0.7)

    def test_d6_is_recovered_when_any_one_exposure_is_removed(self):
        report = make_review(CASES / 'december-d6.npz')
        match = report['comparison']['leave_one_out']['match']
        self.assertEqual((match['rank'], match['exposures']), (1, 4))
        self.assertLess(match['max_offset_px'], 0.6)
        self.assertEqual(len(report['omitted_frame_checks']), 4)
        self.assertTrue(all(item['match']['rank'] == 1 for item in report['omitted_frame_checks']))

    def test_reference_keeps_pixels_with_other_frame_support(self):
        images = np.array([[[4.0, 4.0]], [[np.nan, np.nan]], [[1.0, np.nan]]])
        residuals = difference_frames(images, leave_one_out=True)
        np.testing.assert_array_equal(residuals[:, 0, 0], [3.0, np.nan, -3.0])
        self.assertTrue(np.isnan(residuals[:, 0, 1]).all())

    def test_vesta_core_mask_recovers_the_track_in_two_detectors(self):
        for series in ('vesta-d3', 'vesta-d6'):
            with self.subTest(series=series):
                report = make_review(CASES / f'{series}.npz')
                self.assertIsNone(report['comparison']['leave_one_out']['match'])
                match = report['comparison']['bloom']['match']
                self.assertEqual((match['rank'], match['exposures']), (1, 3))
                self.assertLess(match['max_offset_px'], 0.4)
                track = report['bloom_tracks'][0]
                self.assertEqual(track['stack_contributing_exposures'], 3)
                self.assertIsNone(track['snr'])

    def test_forest_reranks_the_same_real_tracks(self):
        forest = train_random_forest()
        for series in ('december-d2', 'december-d6', 'vesta-d3'):
            with self.subTest(series=series):
                report = make_review(CASES / f'{series}.npz', forest=forest)
                tracks = report['tracks']
                self.assertEqual(sorted(t['random_forest_rank'] for t in tracks), list(range(1, len(tracks) + 1)))
                recovered = [t['random_forest_rank'] for t in tracks if t['known_match']]
                match = report['comparison']['random_forest']['match']
                self.assertEqual(match['rank'] if match else None, min(recovered, default=None))


if __name__ == '__main__':
    unittest.main()
