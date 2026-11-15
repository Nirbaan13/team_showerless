"""Development-preset accounting guards; no fitted model or real pixels used."""
import hashlib
import json

import numpy as np
import pytest

from experiments.v3_evaluation import evaluate_presets as diagnostic


def test_offline_labels_follow_prepared_physical_observation_order(tmp_path):
    path = tmp_path / 'labels.npz'
    np.savez(path, observation_ids=np.array(['late', 'early', 'middle']),
             expected_xy=np.array([[30., 0.], [10., 0.], [20., 0.]]))
    frames = [dict(observation_id=value) for value in ['early', 'middle', 'late']]
    np.testing.assert_array_equal(diagnostic.load_expected(path, frames), [[10., 0.], [20., 0.], [30., 0.]])


def test_inconsistent_duplicate_observation_labels_fail(tmp_path):
    path = tmp_path / 'labels.npz'
    np.savez(path, observation_ids=np.array(['same', 'same']), expected_xy=np.array([[1., 0.], [2., 0.]]))
    with pytest.raises(ValueError, match='inconsistent'):
        diagnostic.load_expected(path, [dict(observation_id='same')])


def record(index, xy, score, method='residual_track'):
    return dict(candidate_index=index, epochs=[0, 1, 2], positions_xy=[xy, xy, xy],
                score=score, method=method, heuristic_rank=index + 1)


def test_unique_target_recovery_uses_stable_ties_and_keeps_bloom_unscored():
    expected = np.array([[2., 2.], [2., 2.], [2., 2.]])
    rows = [record(0, [7., 7.], .5), record(1, [2., 2.], .5), record(2, [2., 2.], .5)]
    bloom = [record(0, [2., 2.], None, 'bloom_track')]
    report = diagnostic.recovery(rows, bloom, expected, max_candidates=2)
    assert report['residual']['detected_before_ranking'] is True
    assert report['residual']['model_at_1'] is False
    assert report['residual']['model_at_3'] is True
    assert report['residual']['matching_candidate_rows'] == 2
    assert report['published']['candidate_count'] == 2
    assert report['published']['model_at_3'] is True
    assert report['bloom']['detected_before_ranking'] is True
    assert report['bloom']['ml_score_applied'] is False
    assert all(row['score'] is None and row['model_rank'] is None for row in report['bloom_records'])
    assert 'known_target_match' not in rows[0]


def test_unready_candidate_is_rejected_before_runtime_model_load(tmp_path):
    (tmp_path / 'ranker.onnx').write_bytes(b'unready candidate')
    digest = hashlib.sha256((tmp_path / 'ranker.onnx').read_bytes()).hexdigest()
    (tmp_path / 'metadata.json').write_text(json.dumps(dict(sha256=digest)))
    with pytest.raises(ValueError, match='freeze'):
        diagnostic.verify_candidate(tmp_path, digest)


def test_bound_review_policy_preserves_bloom_without_receiving_truth_labels(monkeypatch):
    from ml_inference.pipeline import select_review_entries
    calls = []
    def checked(entries, limit, preserve_bloom=False):
        assert all('known_target_match' not in entry[0] for entry in entries)
        calls.append(preserve_bloom)
        return select_review_entries(entries, limit, preserve_bloom=preserve_bloom)
    monkeypatch.setattr(diagnostic, 'select_review_entries', checked, raising=False)
    expected = np.array([[2., 2.], [2., 2.], [2., 2.]])
    residual = [record(i, [7., 7.], 1. - i / 10) for i in range(5)]
    bloom = [record(0, [2., 2.], None, 'bloom_track')]
    result = diagnostic.recovery(residual, bloom, expected, max_candidates=4, preserve_bloom=True)
    assert calls == [True, True]
    assert result['published']['candidate_count'] == 4
    assert result['published']['residual_count'] == 3
    assert result['published']['bloom_count'] == 1
    assert result['published']['known_target_present'] is True
    assert result['published']['model_at_3'] is False
    assert result['published']['model_entries'][-1]['score'] is None
    assert result['published']['model_entries'][-1]['model_rank'] is None
