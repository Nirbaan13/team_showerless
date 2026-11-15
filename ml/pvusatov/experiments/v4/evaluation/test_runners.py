import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('v4_synthetic_test', HERE / 'run_synthetic.py')
runner = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(runner)


def test_synthetic_generation_merges_measured_rows_without_duplicate_keyword_failure(monkeypatch):
    calls = []
    images = np.ones((3, 10, 10)); times = np.array([0., 1., 2.])
    def simulate(*args, **kwargs):
        calls.append('simulate'); return images, times, [], 'noise_only', {}
    def measure(*args):
        calls.append('observable_measure')
        return [], dict(features=[], features_v4=[], candidate_epochs=[], candidate_positions_xy=[],
                        candidate_ids=[], scores_c13=[], scores_v4=[], error=None)
    def record(*args):
        calls.append('labels_after_measurement')
        return dict(features=[], candidate_epochs=[], candidate_positions_xy=[], truth_count=0, matches=[], matched_geometry=[])
    monkeypatch.setattr(runner, 'FROZEN', dict(scope='development', synthetic={'seeds':[3800001]}))
    monkeypatch.setattr(runner, 'MODULES', SimpleNamespace(simulator=SimpleNamespace(simulate=simulate),
        scene=SimpleNamespace(measure=measure), latent=SimpleNamespace(_record=record)))
    result = runner.generate(3800001)
    assert result['features_v4'] == [] and result['truth_count'] == 0
    assert calls == ['simulate', 'observable_measure', 'labels_after_measurement']
