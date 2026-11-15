from pathlib import Path
import importlib.util
import os
import py_compile
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from code_binding import verify_module


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_same_size_same_second_stale_bytecode_is_rejected(tmp_path):
    path=tmp_path/'numeric_policy.py';path.write_text('CUT=1\ndef value(x=1):\n    return x+CUT\n')
    original=path.stat();py_compile.compile(str(path),doraise=True,invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
    path.write_text('CUT=2\ndef value(x=2):\n    return x+CUT\n');os.utime(path,ns=(original.st_atime_ns,original.st_mtime_ns))
    stale=load(path,'stale_numeric_policy')
    assert stale.value()==2
    with pytest.raises(ValueError,match='bytecode|globals|defaults'):verify_module(stale)


def test_fresh_source_defaults_and_functions_verify(tmp_path):
    path=tmp_path/'fresh_policy.py';path.write_text('CUT=2\ndef value(x=2):\n    return x+CUT\n')
    module=load(path,'fresh_numeric_policy');result=verify_module(module)
    assert result['function_count']==1 and len(result['source_sha256'])==64
