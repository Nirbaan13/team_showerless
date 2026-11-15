"""Real controlled generator API and reservation safeguards."""
from pathlib import Path
import importlib.util
import argparse
import numpy as np
import pytest

spec=importlib.util.spec_from_file_location('v4_synthetic_cache',Path(__file__).with_name('cache_synthetic.py'))
cache=importlib.util.module_from_spec(spec);spec.loader.exec_module(cache)


def test_final_seed_is_rejected_before_worker_or_image_generation(tmp_path):
    args=argparse.Namespace(partition='train',start=3900000,fields=1,workers=1,output=str(tmp_path/'never.json.gz'))
    with pytest.raises(ValueError,match='FINAL generation forbidden'):cache.run(args)
    assert list(tmp_path.iterdir())==[]


def test_controlled_fields_preserve_six_feature_prefix_and_development_partition():
    cache.initialize(cache.BASE/'backend/inference/training/calibration/instrument-epsf-bank.npz',{},'development')
    fields=[cache.generate(seed) for seed in [3800002,3800003,3800004]]
    assert all(f['error'] is None for f in fields),fields
    assert all(f['partition']=='development' for f in fields)
    assert sum(len(f['features']) for f in fields)>0
    for field in fields:
        six=np.asarray(field['features'],float).reshape(-1,6)
        rich=np.asarray(field['features_v4'],float).reshape(-1,30)
        np.testing.assert_array_equal(six,rich[:,:6])
        assert len(field['candidate_ids'])==len(six)==len(field['matches'])
