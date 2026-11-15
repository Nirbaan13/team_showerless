import importlib.util
import hashlib
import os
from pathlib import Path
import py_compile
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location('v4_cache_native', Path(__file__).with_name('cache_native.py'))
cache = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cache)


def test_final_scope_rejects_before_opening_any_input():
    group = dict(parent_id='renamed-development', split='final', downloads_manifest={'path': '/does/not/exist', 'sha256': '0' * 64})
    with pytest.raises(ValueError, match='TRAIN or DEVELOPMENT'):
        cache.validate_development_group(group)


def test_changed_input_manifest_is_rejected_before_native_reader(tmp_path):
    path = tmp_path / 'downloads.json'
    path.write_text('[]')
    group = dict(parent_id='train01', split='train', downloads_manifest={'path': str(path), 'sha256': '0' * 64})
    with pytest.raises(ValueError, match='hash'):
        cache.validate_development_group(group)


def tracks():
    return [SimpleNamespace(epochs=(0, 1, 2), positions_xy=((1., 1.), (2., 1.), (3., 1.))),
            SimpleNamespace(epochs=(0, 1, 2), positions_xy=((8., 8.),) * 3)]


def test_unknown_native_competitors_are_never_negative_training_labels():
    labels = cache.label_native_tracks(tracks(), [[1., 1.], [2., 1.], [3., 1.]], stationary=False, preexisting=False)
    assert labels == [0, -2]


def test_only_attributable_injected_stationary_artifact_can_be_negative():
    expected = [[1., 1.], [2., 1.], [3., 1.]]
    assert cache.label_native_tracks(tracks(), expected, stationary=True, preexisting=False) == [-1, -2]
    assert cache.label_native_tracks(tracks(), expected, stationary=True, preexisting=True) == [-2, -2]


def test_exact_source_is_executed_even_when_timestamp_pyc_is_stale(tmp_path):
    path = tmp_path / 'source.py'
    path.write_text("VALUE = 'old'\n")
    os.utime(path, (1700000000, 1700000000))
    py_compile.compile(str(path), doraise=True)
    path.write_text("VALUE = 'new'\n")
    os.utime(path, (1700000000, 1700000000))
    loaded = cache.load_module('v4_test_source_binding', path)
    assert loaded.VALUE == 'new'
    assert loaded.__source_sha256__ == hashlib.sha256(path.read_bytes()).hexdigest()


def test_changed_closure_is_rejected(tmp_path):
    path = tmp_path / 'source.py'
    path.write_text('before')
    closure = {str(path): cache.digest(path)}
    path.write_text('after')
    with pytest.raises(ValueError, match='source closure'):
        cache.verify_source_closure(closure)
