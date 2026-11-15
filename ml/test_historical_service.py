"""Transport contract checks; no archive retrieval or scientific acceptance fixtures."""

import hashlib
from pathlib import Path
from threading import BoundedSemaphore

from fastapi.testclient import TestClient
import pytest

import service

BODY = b'bounded NPZ transport fixture; decoder is substituted only in transport tests'
JOB = 'c1c9e87b-964a-40aa-91cd-28e4d194b46a'


def headers(body=BODY):
    return {'Content-Type': 'application/octet-stream', 'X-Unification-Id': JOB,
            'X-Artifact-Sha256': hashlib.sha256(body).hexdigest()}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(service, 'MOTION_SLOTS', BoundedSemaphore(2))
    return TestClient(service.app)


def test_prepared_upload_verifies_complete_bytes_before_analysis_and_cleans_tempfile(client, monkeypatch):
    paths = []

    def analyze(path, unification_id, *, track_limit=20):
        paths.append(Path(path))
        assert Path(path).read_bytes() == BODY
        assert unification_id == JOB
        assert track_limit == 7
        return {'id': unification_id, 'tracks': []}

    monkeypatch.setattr(service, 'analyze_prepared', analyze, raising=False)
    response = client.post('/internal/motion/prepared?track_limit=7', content=BODY, headers=headers())
    assert response.status_code == 200, response.text
    assert response.json() == {'id': JOB, 'tracks': []}
    assert paths and not paths[0].exists()


@pytest.mark.parametrize('field,value', [('X-Unification-Id', ''), ('X-Unification-Id', 'bad-id'),
                                       ('X-Artifact-Sha256', ''), ('X-Artifact-Sha256', 'bad-hash')])
def test_prepared_identity_and_hash_are_required(client, field, value):
    request_headers = headers()
    request_headers[field] = value
    response = client.post('/internal/motion/prepared', content=BODY, headers=request_headers)
    assert response.status_code == 422


def test_hash_mismatch_never_enters_decoder(client, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('checksum mismatch must be rejected before decoding')

    monkeypatch.setattr(service, 'analyze_prepared', forbidden, raising=False)
    response = client.post('/internal/motion/prepared', content=BODY + b'!', headers=headers())
    assert response.status_code == 422
    assert 'checksum' in response.text.lower()


@pytest.mark.parametrize('declared,body', [('1025', b'x'), (None, b'x' * 1025)])
def test_prepared_upload_bounds_declared_and_streamed_bytes(client, monkeypatch, declared, body):
    monkeypatch.setattr(service, 'MAX_PREPARED_BYTES', 1024, raising=False)
    request_headers = headers(body)
    if declared is not None:
        request_headers['Content-Length'] = declared
        response = client.post('/internal/motion/prepared', content=body, headers=request_headers)
    else:
        response = client.post('/internal/motion/prepared', content=iter([body[:500], body[500:]]),
                               headers=request_headers)
    assert response.status_code == 413


def test_prepared_concurrency_reuses_existing_motion_slots(client):
    service.MOTION_SLOTS.acquire()
    service.MOTION_SLOTS.acquire()
    try:
        response = client.post('/internal/motion/prepared', content=BODY, headers=headers())
        assert response.status_code == 503
    finally:
        service.MOTION_SLOTS.release()
        service.MOTION_SLOTS.release()


def test_decoder_failure_releases_slot_and_cleans_temporary_file(client, monkeypatch):
    paths = []

    def fail(path, *args, **kwargs):
        paths.append(Path(path))
        raise ValueError('unsupported prepared product')

    monkeypatch.setattr(service, 'analyze_prepared', fail, raising=False)
    response = client.post('/internal/motion/prepared', content=BODY, headers=headers())
    assert response.status_code == 422
    assert paths and not paths[0].exists()
    assert service.MOTION_SLOTS.acquire(blocking=False)
    assert service.MOTION_SLOTS.acquire(blocking=False)
    service.MOTION_SLOTS.release()
    service.MOTION_SLOTS.release()


@pytest.mark.parametrize('query', ['url=https://example.com/image', 'track_limit=101',
                                  'track_limit=0', 'profile=unknown'])
def test_prepared_does_not_accept_acquisition_urls_or_unbounded_profiles(client, query):
    response = client.post('/internal/motion/prepared?' + query, content=BODY, headers=headers())
    assert response.status_code == 422


def test_prepared_upload_decodes_actual_npz_and_runs_existing_review(client, tmp_path):
    from science.motion.test_prepared import qualified_bundle, write_bundle

    body = write_bundle(tmp_path / 'transport-fixture.npz', qualified_bundle()).read_bytes()
    response = client.post('/internal/motion/prepared?profile=stellar_proper_motion',
                           content=body, headers=headers(body))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['unification_id'] == JOB
    assert result['profile'] == 'stellar_proper_motion'
    assert result['historical_preparation']['band'] == 'W2'
    assert result['comparison']['random_forest'] is None
    assert [f['time'] for f in result['frames']] == [
        '2010-01-01T00:00:00Z', '2011-01-01T00:00:00Z', '2012-01-01T00:00:00Z']


def test_prepared_invalid_npz_is_explicit_validation_failure(client):
    response = client.post('/internal/motion/prepared', content=BODY, headers=headers())
    assert response.status_code == 422


def test_prepared_missing_mandatory_headers_are_rejected(client):
    response = client.post('/internal/motion/prepared', content=BODY,
                           headers={'Content-Type': 'application/octet-stream'})
    assert response.status_code == 422


def test_health_advertises_prepared_profile_from_actual_runtime(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['historical_motion'] == {'profile': 'stellar_proper_motion', 'available': True}
