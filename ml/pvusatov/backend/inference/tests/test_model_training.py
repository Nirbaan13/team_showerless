"""Scientific metrics must use known injected truth and unique objects, not duplicate tracks."""
import importlib
import numpy as np


def training():
    return importlib.import_module('training.train')


def test_ranking_metrics_use_fixed_budget_and_unique_objects():
    fields = [{'seed': 1, 'features': [[3, .1, 7, 6, .1, 1]] * 4,
               'matches': [0, 0, -1, 1], 'truth_count': 3, 'baseline': [9, 8, 7, 6]},
              {'seed': 2, 'features': [[3, .1, 7, 6, .1, 1]],
               'matches': [-1], 'truth_count': 0, 'baseline': [5]}]
    metrics = training().evaluate(fields, lambda field: np.asarray(field['baseline']), top_k=3)
    assert metrics['injected_tracks'] == 3
    assert metrics['recovered_before_ranking'] == 2
    assert metrics['recovered_in_top_k'] == 1
    assert metrics['false_tracks_in_top_k'] == 2
    assert metrics['top_k_recall'] == 1 / 3
    assert metrics['false_tracks_per_field_in_top_k'] == 1


def test_empty_noise_control_has_defined_metrics():
    metrics = training().evaluate([dict(seed=3, features=[], matches=[], truth_count=0, baseline=[])],
                                  lambda field: np.empty(0), top_k=3)
    assert metrics['injected_tracks'] == 0
    assert metrics['top_k_recall'] is None
    assert metrics['track_average_precision'] is None
    assert metrics['false_tracks_in_top_k'] == 0


def test_train_validation_test_fields_never_overlap():
    seeds = training().split_seeds(20, 10, 10)
    assert seeds['train'] == list(range(20))
    assert seeds['validation'] == list(range(100_000, 100_010))
    assert seeds['test'] == list(range(200_000, 200_010))


def test_paired_uncertainty_counts_unique_recovery_per_field():
    module = importlib.import_module('training.statistics')
    fields = [dict(features=[[.1]*6, [.9]*6], matches=[-1, 0], truth_count=2, baseline=[10, 9])]
    result = module.paired_bootstrap(fields, lambda f: np.asarray([.1, .9]), top_k=1, draws=100)
    assert result['top_k_recall_difference_rf_minus_baseline_95percent'] == [.5, .5]
    assert result['false_tracks_per_field_difference_rf_minus_baseline_95percent'] == [-1., -1.]
