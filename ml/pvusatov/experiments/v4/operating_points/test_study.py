import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from ml.pvusatov.experiments.v4.operating_points.study import label_tracks, recovery, initialize

class OperatingPoints(unittest.TestCase):
    def test_missing_protocol_never_initializes_science(self):
        with patch('pathlib.Path.read_bytes',side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):initialize('/missing','0'*64)

    def test_duplicate_candidates_count_truth_once_at_review_budget(self):
        t=SimpleNamespace(epochs=(0,1,2),positions_xy=((2,3),(3,3),(4,3)))
        labels=label_tracks([t,t],[np.asarray(t.positions_xy)],False)
        self.assertEqual(labels,[0,0])
        self.assertEqual(recovery(labels,[1,0])['top3'],1)

    def test_native_unknown_is_not_a_negative_label(self):
        t=SimpleNamespace(epochs=(0,1,2),positions_xy=((2,3),(3,3),(4,3)))
        self.assertEqual(label_tracks([t],[],True),[-2])
        self.assertEqual(label_tracks([t],[],False),[-1])

    def test_matching_uses_all_actual_candidate_epochs(self):
        t=SimpleNamespace(epochs=(0,2,3),positions_xy=((2,3),(3,3),(4,3)))
        p=np.asarray([[2,3],[99,99],[3,3],[6,3]])
        self.assertEqual(label_tracks([t],[p],False),[-1])
