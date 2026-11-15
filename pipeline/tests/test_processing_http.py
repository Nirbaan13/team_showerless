"""HTTP boundary integration; operations run in real supervised child processes."""
import asyncio
import json
import os
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_worker import fixture_fits


def call(app, method, path, **kwargs):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://pipeline') as client:
            return await client.request(method, path, **kwargs)
    return asyncio.run(run())


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setenv('PROCESSING_DATA_ROOT', str(tmp_path))
    import service
    return service


def test_internal_capabilities_without_archive_import(service):
    response = call(service.app, 'GET', '/internal/capabilities')
    assert response.status_code == 200
    assert response.json()['operations'] == ['preview', 'zodi', 'spectrum_preview']
    assert 'spherex.query' not in sys.modules


def test_internal_preview_runs_real_fits_process(service, tmp_path):
    source = fixture_fits(tmp_path)
    output = tmp_path / 'preview.png'
    response = call(service.app, 'POST', '/internal/processing', json=dict(
        operation='preview', image_path=str(source), output_path=str(output)))
    assert response.status_code == 200, response.text
    assert response.json()['data_max'] == 34.
    assert output.read_bytes().startswith(b'\x89PNG')


@pytest.mark.parametrize('payload', [[], {'operation':'align'}, {'operation':'spectrum'}, {'operation':'preview'}])
def test_invalid_request_is_typed_422(service, payload):
    response = call(service.app, 'POST', '/internal/processing', json=payload)
    assert response.status_code == 422
    assert response.json()['status'] == 'error'
    assert response.json()['error']['code'] == 'invalid_request'


def test_input_and_output_paths_are_confined_to_shared_data(service, tmp_path):
    outside = tmp_path.parent / (tmp_path.name + '-outside')
    outside.mkdir()
    source = fixture_fits(outside)
    response = call(service.app, 'POST', '/internal/processing', json=dict(
        operation='preview', image_path=str(source), output_path=str(tmp_path / 'preview.png')))
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'invalid_path'
    link = tmp_path / 'escape.fits'
    link.symlink_to(source)
    response = call(service.app, 'POST', '/internal/processing', json=dict(
        operation='preview', image_path=str(link), output_path=str(tmp_path / 'preview.png')))
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'invalid_path'
    source = fixture_fits(tmp_path)
    response = call(service.app, 'POST', '/internal/processing', json=dict(
        operation='preview', image_path=str(source), output_path=str(outside / 'preview.png')))
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'invalid_path'


def test_bounded_request_body_and_invalid_json(service):
    for body in [b'x' * 65537, b'{} {}', b'{"operation":NaN}']:
        response = call(service.app, 'POST', '/internal/processing', content=body)
        assert response.status_code == 422
        assert response.json()['error']['code'] == 'invalid_request'


def test_worker_validation_errors_are_typed_422(service, tmp_path):
    source = tmp_path / 'bad.fits'
    source.write_bytes(b'not FITS')
    response = call(service.app, 'POST', '/internal/processing', json=dict(
        operation='zodi', image_path=str(source), output_path=str(tmp_path / 'clean.fits')))
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'invalid_fits'


def child_program(tmp_path, body):
    marker = tmp_path / 'child.pid'
    return marker, [sys.executable, '-c',
        f'import os,pathlib,time,sys; pathlib.Path({str(marker)!r}).write_text(str(os.getpid())); {body}']


def assert_child_dead(marker):
    assert marker.exists(), 'The test must start a real OS child'
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)


def test_deadline_waits_for_child_to_die(service, tmp_path, monkeypatch):
    marker, command = child_program(tmp_path, 'time.sleep(30)')
    monkeypatch.setattr(service, '_processing_command', lambda: command)
    monkeypatch.setattr(service, 'PROCESSING_TIMEOUT_SECONDS', .3)
    response = call(service.app, 'POST', '/internal/processing', json={'operation':'capabilities'})
    assert response.status_code == 504
    assert response.json()['error']['code'] == 'deadline_exceeded'
    assert_child_dead(marker)


@pytest.mark.parametrize('stream', ['stdout', 'stderr'])
def test_protocol_overflow_kills_child(service, tmp_path, monkeypatch, stream):
    marker, command = child_program(tmp_path, f'sys.{stream}.write("x"*70000); sys.{stream}.flush(); time.sleep(30)')
    monkeypatch.setattr(service, '_processing_command', lambda: command)
    response = call(service.app, 'POST', '/internal/processing', json={'operation':'capabilities'})
    assert response.status_code == 502
    assert response.json()['error']['code'] == 'invalid_response'
    assert_child_dead(marker)


def test_capacity_is_rejected_while_child_is_running(service, tmp_path, monkeypatch):
    marker, command = child_program(tmp_path, 'time.sleep(30)')
    monkeypatch.setattr(service, '_processing_command', lambda: command)
    monkeypatch.setattr(service, 'PROCESSING_TIMEOUT_SECONDS', .5)
    monkeypatch.setattr(service, 'PROCESSING_MAX_CONCURRENCY', 1)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=service.app), base_url='http://pipeline') as client:
            first = asyncio.create_task(client.post('/internal/processing', json={'operation':'capabilities'}))
            for _ in range(100):
                if marker.exists():
                    break
                await asyncio.sleep(.01)
            second = await client.post('/internal/processing', json={'operation':'capabilities'})
            assert second.status_code == 503
            assert second.json()['error']['code'] == 'capacity_exceeded'
            assert (await first).status_code == 504
    asyncio.run(run())
    assert_child_dead(marker)
    assert service._active_processing == 0


def test_disconnected_client_kills_child_before_return(service, tmp_path, monkeypatch):
    marker, command = child_program(tmp_path, 'time.sleep(30)')
    monkeypatch.setattr(service, '_processing_command', lambda: command)
    async def receive():
        return {'type':'http.disconnect'} if marker.exists() else {'type':'http.request','body':b'','more_body':False}
    async def run():
        request = service.Request({'type':'http'}, receive=receive)
        with pytest.raises(service.ProcessingHTTPError) as error:
            await service._supervised_processing(request, b'{"operation":"capabilities"}')
        assert error.value.code == 'client_disconnected'
    asyncio.run(run())
    assert_child_dead(marker)


def test_cancelled_asgi_task_waits_for_child_to_die(service, tmp_path, monkeypatch):
    marker, command = child_program(tmp_path, 'time.sleep(30)')
    monkeypatch.setattr(service, '_processing_command', lambda: command)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=service.app), base_url='http://pipeline') as client:
            task = asyncio.create_task(client.post('/internal/processing', json={'operation':'capabilities'}))
            for _ in range(100):
                if marker.exists():
                    break
                await asyncio.sleep(.01)
            assert marker.exists()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    asyncio.run(run())
    assert_child_dead(marker)
    assert service._active_processing == 0


def test_dangling_output_symlink_is_not_a_new_file(service, tmp_path):
    source = fixture_fits(tmp_path)
    output = tmp_path / 'preview.png'
    target = tmp_path / 'target.png'
    output.symlink_to(target)
    response = call(service.app, 'POST', '/internal/processing', json=dict(
        operation='preview', image_path=str(source), output_path=str(output)))
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'invalid_output'
    assert not target.exists()


def test_valid_but_oversized_request_never_launches_child(service, tmp_path, monkeypatch):
    marker, command = child_program(tmp_path, 'time.sleep(30)')
    monkeypatch.setattr(service, '_processing_command', lambda: command)
    response = call(service.app, 'POST', '/internal/processing', json=dict(operation='capabilities', padding='x'*65536))
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'invalid_request'
    assert not marker.exists()


def test_cancellation_during_subprocess_startup_still_reaps_child(service, tmp_path, monkeypatch):
    marker, command = child_program(tmp_path, 'time.sleep(30)')
    monkeypatch.setattr(service, '_processing_command', lambda: command)
    original_spawn = asyncio.create_subprocess_exec
    spawned = []
    async def run():
        ready = asyncio.Event()
        async def delayed_spawn(*args, **kwargs):
            child = await original_spawn(*args, **kwargs)
            spawned.append(child)
            ready.set()
            await asyncio.sleep(.1)
            return child
        monkeypatch.setattr(asyncio, 'create_subprocess_exec', delayed_spawn)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=service.app), base_url='http://pipeline') as client:
            task = asyncio.create_task(client.post('/internal/processing', json={'operation':'capabilities'}))
            await ready.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            try:
                with pytest.raises(ProcessLookupError):
                    os.kill(spawned[0].pid, 0)
            finally:
                if spawned[0].returncode is None:
                    spawned[0].kill()
                    await spawned[0].wait()
    asyncio.run(run())
