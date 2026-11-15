"""Runtime limits reject unsafe configuration and bound actual work."""
import importlib
from datetime import date
from pathlib import Path
import sys
from threading import Lock
from time import sleep

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'ml'))


@pytest.mark.parametrize('configured,capacity', [(None, 2), ('1', 1), ('4', 4)])
def test_motion_search_admission_uses_configured_slots(monkeypatch, tmp_path, configured, capacity):
    monkeypatch.delenv('MOTION_SEARCH_SLOTS', raising=False)
    if configured is not None:
        monkeypatch.setenv('MOTION_SEARCH_SLOTS', configured)
    monkeypatch.setenv('VERIFICATIONS_DB_PATH', str(tmp_path / 'verifications.sqlite'))
    import service
    service = importlib.reload(service)
    for _ in range(capacity):
        assert service.MOTION_SLOTS.acquire(blocking=False)
    assert not service.MOTION_SLOTS.acquire(blocking=False)
    for _ in range(capacity):
        service.MOTION_SLOTS.release()


@pytest.mark.parametrize('name,invalid', [
    ('MOTION_SEARCH_SLOTS', '0'), ('MOTION_SEARCH_SLOTS', '5'),
    ('MOTION_SEARCH_SLOTS', 'many'), ('MOTION_SEARCH_SLOTS', ''),
    ('MOTION_FETCH_WORKERS', '0'), ('MOTION_FETCH_WORKERS', '9'),
    ('MOTION_FETCH_WORKERS', '1.5'), ('MOTION_FETCH_WORKERS', ''),
])
def test_invalid_limits_fail_at_import(monkeypatch, tmp_path, name, invalid):
    monkeypatch.setenv(name, invalid)
    monkeypatch.setenv('VERIFICATIONS_DB_PATH', str(tmp_path / 'verifications.sqlite'))
    from science.motion import live
    with pytest.raises(ValueError, match=name + ' must be an integer between 1 and '):
        if name == 'MOTION_FETCH_WORKERS':
            importlib.reload(live)
        else:
            import service
            importlib.reload(service)


@pytest.mark.parametrize('configured,maximum', [(None, 4), ('1', 1), ('8', 8)])
def test_fetch_workers_bound_parallel_visit_loading(monkeypatch, configured, maximum):
    monkeypatch.delenv('MOTION_FETCH_WORKERS', raising=False)
    if configured is not None:
        monkeypatch.setenv('MOTION_FETCH_WORKERS', configured)
    from science.motion import live
    live = importlib.reload(live)
    lock = Lock()
    active = peak = 0

    def load_visit(*args):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        sleep(0.04)
        with lock:
            active -= 1
        return None, None, []

    monkeypatch.setattr(live, 'discover', lambda *args: list(range(8)))
    monkeypatch.setattr(live, 'sample_visits', lambda exposures: ([[i] for i in exposures], 8))
    monkeypatch.setattr(live, 'grid_coordinates', lambda *args: (None, None))
    monkeypatch.setattr(live, 'load_visit', load_visit)
    with pytest.raises(live.SearchError, match='Only 0 of 8 selected visits'):
        live.search_motion(10, 20, 1, date(2025, 1, 1), date(2025, 1, 1), 2, True)
    assert peak == maximum
