"""Publish real measured middle-epoch links, without holdout or model access."""
import gzip
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_nonempty_measured_hypotheses_publish_full_and_compact_results(tmp_path):
    from ml_inference import detector
    policy = load('transport_measured_policies', HERE.parent / 'association_pilot/policies.py')
    runner = load('transport_measured_runner', HERE / 'runner.py')
    accounting = load('transport_measured_accounting', HERE / 'accounting.py')
    peaks = [np.asarray([[4 + epoch, 4, 8., 1.]]) for epoch in range(4)]
    times = np.arange(4, dtype=float)
    pool, work = policy.build_hypotheses(peaks, times, .5, 60., 1.4, 3)
    assert pool and any(isinstance(value, np.integer) for links, _ in pool for pair in links for value in pair)
    kept, pruning = policy.pair_exclusive(pool)
    prediction = dict(pool=pool, features=[list(map(float, track.features())) + [0.] * 24 for _, track in pool],
        candidate_ids=[f'measured-{i}' for i in range(len(pool))], scores=[.5] * len(pool),
        kept={role: kept for role in runner.ROLES}, policy_work={role: pruning for role in runner.ROLES},
        hypothesis_work=work, peaks_per_epoch=[len(p) for p in peaks], peak_cap_reached=False,
        legacy_candidate_parity=True, legacy_feature_score_parity=True, parity_cpu_seconds=0.,
        prediction_wall_seconds=0., prediction_cpu_seconds=0.)
    runner.STATE.update(np=np, output=tmp_path, detector=detector, accounting=accounting)
    identity = dict(kind='synthetic', seed=3800805, case_id='development-transport', mode='noise_only', cadence_family=0)
    published = runner.emit(identity, np.zeros((4, 20, 20)), times, [], prediction)
    with gzip.open(published['full_pool']['path'], 'rt') as stream:
        full = json.load(stream)
    with gzip.open(published['compact']['path'], 'rt') as stream:
        compact = json.load(stream)
    assert len(full['candidates']) == len(pool) and compact['retained_union_count'] == len(kept)
    assert compact['error'] is None and compact['truth_count'] == 0
    for row, (links, _) in zip(full['candidates'], pool):
        assert row['links'] == [[int(epoch), int(index)] for epoch, index in links]
        assert all(type(value) is int for pair in row['links'] for value in pair)
    assert all(value['top1'] == value['top3'] == 0 for value in compact['policies'].values())
