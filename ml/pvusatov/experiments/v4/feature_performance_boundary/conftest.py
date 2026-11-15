"""Relocate the identical frozen scorer for portable tests only.

The original boundary harness/protocol remain unchanged historical evidence.
No test depends on the author's populated /tmp development-model cache.
"""
import pytest
from ml.pvusatov.experiments.v4.feature_performance_boundary import boundary


@pytest.fixture(autouse=True)
def packaged_fixed_scorer(monkeypatch):
    model = boundary.ROOT / 'ml/pvusatov/releases/v4/model'
    assert boundary.digest_file(model / 'ranker.onnx') == boundary.MODEL_SHA
    assert boundary.digest_file(model / 'metadata.json') == '472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13'
    monkeypatch.setattr(boundary, 'MODEL_DIR', model)
