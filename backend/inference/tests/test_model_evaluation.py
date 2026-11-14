"""Selected real targets must remain recovery cases with all other rows unlabeled."""
import importlib
import numpy as np
from ml_inference.detector import Candidate


def test_known_ephemeris_match_does_not_label_other_tracks_negative():
    module = importlib.import_module('training.evaluate_real')
    tracks = [Candidate((0, 1, 2), ((2, 3), (4, 5), (6, 7)), (5, 5, 5), 2.8, 0, 1),
              Candidate((0, 1, 2), ((20, 3), (24, 5), (26, 7)), (8, 8, 8), 3.2, .1, 1)]
    report = module.recovery(tracks, np.asarray([.2, .9]), np.asarray([[2, 3], [4, 5], [6, 7]]))
    assert report['known_target_recovered'] is True
    assert report['known_target_matches'][0]['heuristic_rank'] == 1
    assert report['known_target_matches'][0]['model_rank'] == 2
    assert report['unmatched_candidates_unlabeled'] == 1
    assert 'precision' not in report
    assert 'false_candidates' not in report
