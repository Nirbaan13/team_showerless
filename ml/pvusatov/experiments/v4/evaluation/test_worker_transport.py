"""Worker errors must remain readable when their defining module is child-only."""
import importlib.util
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
import sys

import pytest


PRIVATE_MODULE = '_v4_child_only_failure'


def raise_private(task):
    path, message = task
    spec = importlib.util.spec_from_file_location(PRIVATE_MODULE, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[PRIVATE_MODULE] = module
    spec.loader.exec_module(module)
    raise module.InferenceError('controlled_failure', message)


def load_transport():
    path = Path(__file__).with_name('worker_transport.py')
    assert path.is_file(), 'safe worker transport has not been implemented'
    name = '_v4_checked_transport_test'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


@pytest.fixture
def private_source(tmp_path):
    path = tmp_path / (PRIVATE_MODULE + '.py')
    path.write_text('''class InferenceError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
''')
    assert PRIVATE_MODULE not in sys.modules
    assert importlib.util.find_spec(PRIVATE_MODULE) is None
    return str(path)


def test_raw_child_only_exception_masks_original_error(private_source):
    # Characterize the actual failure: the parent cannot import the exception
    # module and loses the original code/message to BrokenProcessPool.
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('fork')) as pool:
        with pytest.raises(BrokenProcessPool) as failure:
            pool.submit(raise_private, (private_source, 'original diagnostic')).result(timeout=10)
    assert 'No module named' in str(failure.value.__cause__)
    assert PRIVATE_MODULE not in sys.modules


def test_wrapper_preserves_original_error_and_keeps_pool_usable(private_source):
    transport = load_transport()
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('fork')) as pool:
        with pytest.raises(RuntimeError) as failure:
            pool.submit(transport.safe_call, raise_private,
                        (private_source, 'original diagnostic')).result(timeout=10)
        assert type(failure.value) is RuntimeError
        message = str(failure.value)
        assert PRIVATE_MODULE + '.InferenceError' in message
        assert 'controlled_failure' in message
        assert 'original diagnostic' in message
        assert 'Traceback' in message and 'raise_private' in message
        assert len(failure.value.args) == 1 and type(failure.value.args[0]) is str
        assert pool.submit(transport.safe_call, abs, -7).result(timeout=10) == 7
    assert PRIVATE_MODULE not in sys.modules
    assert importlib.util.find_spec(PRIVATE_MODULE) is None


def test_wrapper_bounds_transport_text_without_losing_error_identity(private_source):
    transport = load_transport()
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context('fork')) as pool:
        with pytest.raises(RuntimeError) as failure:
            pool.submit(transport.safe_call, raise_private,
                        (private_source, 'large diagnostic ' + 'x' * 100000)).result(timeout=10)
    text = str(failure.value)
    assert len(text) <= 16384
    assert PRIVATE_MODULE + '.InferenceError' in text
    assert 'controlled_failure' in text and 'large diagnostic' in text
    assert 'Traceback' in text and 'raise_private' in text


def test_wrapper_returns_success_unchanged_and_does_not_catch_baseexception():
    transport = load_transport()
    value = {'scores': [.1, .9], 'inputs': ['unchanged']}
    assert transport.safe_call(lambda task: task, value) is value

    def interrupt(task):
        raise KeyboardInterrupt(task)

    with pytest.raises(KeyboardInterrupt, match='stop'):
        transport.safe_call(interrupt, 'stop')
