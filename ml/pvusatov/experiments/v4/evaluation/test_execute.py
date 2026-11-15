import hashlib
import importlib.util
import json
import os
from pathlib import Path
import py_compile

import pytest

SPEC = importlib.util.spec_from_file_location('v4_execute_test', Path(__file__).with_name('execute.py'))
executor = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(executor)


def test_bootstrap_never_imports_a_stale_validator_pyc(tmp_path):
    path = tmp_path / 'validator.py'
    prefix = 'import json\ndef validate_freeze(path, anchor): return json.load(open(path))\n'
    path.write_text(prefix + "VALUE='old'\n")
    os.utime(path, (1700000000, 1700000000)); py_compile.compile(str(path), doraise=True)
    path.write_text(prefix + "VALUE='new'\n"); os.utime(path, (1700000000, 1700000000))
    payload = dict(sources={'freeze':dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())})
    freeze_path = tmp_path / 'freeze.json'; freeze_path.write_text(json.dumps(payload))
    value, checked = executor.bootstrap(freeze_path, hashlib.sha256(freeze_path.read_bytes()).hexdigest())
    assert checked.VALUE == 'new'
    assert checked.__source_sha256__ == payload['sources']['freeze']['sha256']


def test_wrong_outer_anchor_prevents_even_validator_execution(tmp_path):
    path = tmp_path / 'freeze.json'; path.write_text('{}')
    with pytest.raises(ValueError, match='anchor'):
        executor.bootstrap(path, '0' * 64)
