"""Mirror integration tests use valid FITS headers and a real bounded HTTP transport."""
import importlib.util
import io
from functools import lru_cache
import json
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from xml.sax.saxutils import escape

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS

SCRIPT = Path(__file__).parents[1] / 'python' / 'irsa_mirror.py'

@lru_cache(maxsize=1)
def module():
    spec = importlib.util.spec_from_file_location('irsa_mirror', SCRIPT)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def image(ra=359.9, dec=1.0, date='2025-04-24T18:01:05.843', detector=1, padding=0):
    h = fits.Header({'DATE-OBS': date, 'DETECTOR': detector, 'OBSID': '2025W17_4B_0001'})
    for n in range(padding):
        h[f'H{n:07d}'] = 'padding'
    w = WCS(naxis=2)
    w.wcs.crpix = [20.5, 20.5]
    w.wcs.cdelt = [-0.02, 0.02]
    w.wcs.crval = [ra, dec]
    w.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    b = io.BytesIO()
    fits.HDUList([fits.PrimaryHDU(header=h), fits.ImageHDU(np.zeros((40, 40), dtype=np.float32), header=w.to_header(), name='IMAGE')]).writeto(b)
    return b.getvalue()


@pytest.fixture
def s3():
    state = {'objects': {}, 'requests': [], 'bad_range': False, 'bad_content_range': False, 'fail': set(), 'page': 1}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            p = urlsplit(self.path)
            q = parse_qs(p.query)
            if q.get('list-type') == ['2']:
                keys = sorted(k for k in state['objects'] if k.startswith(q['prefix'][0]))
                start = int(q.get('continuation-token', ['0'])[0])
                count = min(int(q.get('max-keys', ['100'])[0]), state['page'])
                end = start + count
                more = end < len(keys)
                body = '<ListBucketResult><IsTruncated>' + str(more).lower() + '</IsTruncated>'
                if more:
                    body += f'<NextContinuationToken>{end}</NextContinuationToken>'
                for k in keys[start:end]:
                    body += f'<Contents><Key>{escape(k)}</Key><Size>{len(state["objects"][k])+state.get('declared_size_delta', 0)}</Size><ETag>"identity-{escape(k)}"</ETag><LastModified>2026-01-01T00:00:00Z</LastModified></Contents>'
                body = (body + '</ListBucketResult>').encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            key = p.path.lstrip('/')
            state['requests'].append((key, self.headers.get('Range')))
            if key in state['fail']:
                self.send_error(503)
                return
            data = state['objects'][key]
            end = min(int(self.headers['Range'].split('-')[1]), len(data)-1)
            self.send_response(200 if state['bad_range'] else 206)
            self.send_header('Content-Range', f'bytes {1 if state["bad_content_range"] else 0}-{end}/{len(data)}')
            self.send_header('Content-Length', str(end+1))
            self.end_headers()
            self.wfile.write(data[:end+1])
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    state['root'] = f'http://127.0.0.1:{server.server_port}/'
    yield state
    server.shutdown()
    server.server_close()
    t.join()


def add(s3, name='a', **kwargs):
    key = f'qr2/level2/2025W17_4B/version/1/{name}.fits'
    s3['objects'][key] = image(**kwargs)
    return key


def index(tmp_path, s3):
    return module().MirrorIndex(tmp_path / 'mirror.sqlite', s3['root'], ['qr2'])


def test_missing_index_is_warming_not_empty_sky(tmp_path, s3):
    m = module()
    with pytest.raises(m.MirrorError, match='archive_mirror_index_warming'):
        index(tmp_path, s3).search({'position': 'CIRCLE 0 1 0.1'})


def test_resume_pagination_partial_provenance_and_native_identity(tmp_path, s3):
    key = add(s3)
    add(s3, 'b', ra=60)
    idx = index(tmp_path, s3)
    first = idx.scan(max_pages=1, workers=2)
    assert first['index']['complete'] is False
    found = idx.search({'position': 'POLYGON 359.7 0.8 0.2 0.8 0.2 1.2 359.7 1.2'})
    assert len(found['images']) == 1
    item = found['images'][0]
    assert item['accessUrl'] == s3['root'] + key
    assert item['observation']['observation_date'] == '2025-04-24T18:01:05.843Z'
    assert item['observation']['release'] == 'QR2'
    assert item['observation']['detector_array'] == 1
    assert item['observation']['header_metadata']['discovery_complete'] == 'false'
    assert item['observation']['header_metadata']['survey'] == 'unknown'
    second = index(tmp_path, s3).scan(max_pages=1)
    assert second['index']['complete'] is True
    assert len(s3['requests']) == 2
    index(tmp_path, s3).scan(max_pages=1)
    assert len(s3['requests']) == 2


def test_failed_object_is_durable_and_does_not_pin_later_pages(tmp_path, s3, monkeypatch):
    import time
    clock = [time.time()]
    monkeypatch.setattr(module().time, 'time', lambda: clock[0])
    key = add(s3)
    add(s3, 'b')
    s3['fail'].add(key)
    idx = index(tmp_path, s3)
    result = idx.scan(max_pages=1)
    assert result['errors']
    assert not result['index']['complete']
    assert result['index']['failed_objects'] == 1
    assert result['index']['releases'][0]['token'] == '1'
    # A fresh process resumes listing despite the still-failing first object.
    second = index(tmp_path, s3).scan(max_pages=1)
    assert second['index']['listing_complete']
    assert not second['index']['complete']
    assert len(idx.search({'position': 'CIRCLE 359.9 1 0.01'})['images']) == 1
    # Backoff prevents busy retries on every scanner cycle.
    assert sum(request[0] == key for request in s3['requests']) == 2
    s3['fail'].clear()
    clock[0] += 61
    final = index(tmp_path, s3).scan(max_pages=1)
    assert final['index']['complete']
    assert final['index']['failed_objects'] == 0
    assert len(idx.search({'position': 'CIRCLE 359.9 1 0.01'})['images']) == 2


@pytest.mark.parametrize('bad', ['bad_range', 'bad_content_range'])
def test_range_contract_rejected_and_never_marks_complete(tmp_path, s3, bad):
    add(s3)
    s3[bad] = True
    result = index(tmp_path, s3).scan(max_pages=1)
    assert result['errors']
    assert not result['index']['complete']
    assert all(r == 'bytes=0-65535' for _, r in s3['requests'])


def test_date_detector_real_footprint_and_empty_complete(tmp_path, s3):
    add(s3)
    idx = index(tmp_path, s3)
    assert idx.scan()['index']['complete']
    for query in [
        {'position': 'CIRCLE 180 -1 1'},
        {'position': 'CIRCLE 359.9 1 0.1', 'detector': 2},
        {'position': 'CIRCLE 359.9 1 0.1', 'after': '2025-04-25T00:00:00Z'},
        {'position': 'CIRCLE 359.9 1 0.1', 'before': '2025-04-24T18:01:05Z'},
    ]:
        assert idx.search(query)['images'] == []
    assert len(idx.search({'position': 'RANGE 359.8 0.1 0.9 1.1', 'detector': 1, 'after': '2025-04-24T18:01:05.843Z'})['images']) == 1
    # Query centre lies outside image, but the query circle overlaps an edge.
    assert len(idx.search({'position': 'CIRCLE 0.4 1 0.2'})['images']) == 1


def test_unsupported_science_selection_and_overflow_explicit(tmp_path, s3):
    add(s3)
    add(s3, 'b')
    s3['page'] = 100
    idx = index(tmp_path, s3)
    idx.scan()
    m = module()
    # Different imports produce distinct exception types; assert the stable error codes.
    for query, code in [({'deep': True}, 'archive_mirror_survey_unsupported'), ({'channel': 1}, 'archive_mirror_channel_unsupported')]:
        with pytest.raises(Exception, match=code):
            idx.search({'position': 'CIRCLE 359.9 1 0.01', **query})
    with pytest.raises(Exception, match='archive_mirror_result_overflow'):
        idx.search({'position': 'CIRCLE 359.9 1 0.01'}, limit=1)


def test_large_header_grows_range_but_never_downloads_image(tmp_path, s3):
    add(s3, padding=1000)
    idx = index(tmp_path, s3)
    assert idx.scan()['index']['complete']
    assert [r for _, r in s3['requests']] == ['bytes=0-65535', 'bytes=0-131071']


def test_nonofficial_root_and_traversal_rejected(tmp_path):
    m = module()
    for root in ['https://evil.example/', 'http://169.254.169.254/', 'https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/../']:
        with pytest.raises(m.MirrorError):
            m.MirrorIndex(tmp_path / 'x', root, ['qr2'])


def test_gateway_evidence_comes_from_fits_identity_and_actual_epoch(tmp_path, s3):
    key = add(s3, 'level2_2025W17_4B_0001_1D1_spx_l2b-v27')
    idx = index(tmp_path, s3)
    idx.scan()
    metadata = idx.search({'position': 'CIRCLE 359.9 1 0.01'})['images'][0]['observation']['header_metadata']
    assert metadata['dataproduct_subtype'] == 'science'
    assert metadata['energy_bandpassname'] == 'SPHEREx-D1'
    assert metadata['obs_collection'] == 'spherex_qr2'
    assert float(metadata['t_min']) == pytest.approx(60789.750762072, abs=1e-8)
    assert metadata['source_key'] == key


def test_header_limit_is_a_failed_object_not_complete(tmp_path, s3):
    add(s3, padding=4000)
    result = index(tmp_path, s3).scan()
    assert not result['index']['complete']
    assert result['errors'][0]['code'] == 'archive_mirror_header_limit'
    assert [r for _, r in s3['requests']] == ['bytes=0-65535', 'bytes=0-131071', 'bytes=0-262143']


def test_reset_does_not_keep_deleted_objects_as_current_sky(tmp_path, s3):
    add(s3)
    idx = index(tmp_path, s3)
    idx.scan()
    s3['objects'].clear()
    idx.reset()
    idx.scan()
    assert idx.search({'position': 'CIRCLE 359.9 1 1'})['images'] == []


def test_cli_returns_machine_readable_warming_and_success(tmp_path, s3):
    import subprocess
    import sys
    command = [sys.executable, str(SCRIPT), '--db', str(tmp_path / 'cli.sqlite'), '--root', s3['root'], '--releases', 'qr2']
    query = json.dumps({'position': 'CIRCLE 359.9 1 0.1'})
    warming = subprocess.run(command + ['search'], input=query, text=True, capture_output=True)
    assert warming.returncode == 2
    assert json.loads(warming.stdout)['error']['code'] == 'archive_mirror_index_warming'
    add(s3)
    scanned = subprocess.run(command + ['scan', '--max-pages', '1'], text=True, capture_output=True)
    assert scanned.returncode == 0
    assert json.loads(scanned.stdout)['index']['complete']
    found = subprocess.run(command + ['search', '--limit', '256'], input=query, text=True, capture_output=True)
    assert found.returncode == 0
    assert len(json.loads(found.stdout)['images']) == 1


def test_range_handles_full_sky_and_polar_coordinates(tmp_path, s3):
    add(s3, ra=25, dec=89.7)
    idx = index(tmp_path, s3)
    idx.scan()
    assert len(idx.search({'position': 'RANGE 0 360 -90 90'})['images']) == 1
    assert len(idx.search({'position': 'RANGE 0 360 89 90'})['images']) == 1
    assert idx.search({'position': 'RANGE 90 180 -1 1'})['images'] == []


def test_native_ids_cannot_collide_across_release_or_processing_path(tmp_path, s3):
    first = add(s3, 'level2_native')
    second = first.replace('/version/', '/another-version/')
    s3['objects'][second] = image()
    s3['page'] = 100
    idx = index(tmp_path, s3)
    idx.scan()
    images = idx.search({'position': 'CIRCLE 359.9 1 0.01'})['images']
    assert len({item['observation']['frame_id'] for item in images}) == 2
    assert {item['accessUrl'] for item in images} == {s3['root']+first, s3['root']+second}
    assert all(item['observation']['header_metadata']['native_frame_id'] == 'level2_native' for item in images)


def test_traversal_key_fails_before_any_header_request(tmp_path, s3):
    s3['objects']['qr2/level2/../secret.fits'] = image()
    result = index(tmp_path, s3).scan()
    assert not result['index']['complete']
    assert result['errors'][0]['code'] == 'archive_mirror_object_invalid'
    assert not s3['requests']


def test_object_changed_since_listing_is_not_recorded_as_verified(tmp_path, s3):
    add(s3)
    s3['declared_size_delta'] = 1
    result = index(tmp_path, s3).scan()
    assert not result['index']['complete']
    assert result['index']['objects_indexed'] == 0
    assert result['errors'][0]['code'] == 'archive_mirror_object_changed'


def test_optional_live_known_dr1_header(tmp_path):
    import os
    if os.environ.get('SPHEREX_MIRROR_LIVE_SMOKE') != '1':
        pytest.skip('Set SPHEREX_MIRROR_LIVE_SMOKE=1 for bounded public S3 header smoke')
    m = module()
    key = 'dr1/level2/2025W17_4B/l2b-v27-2026-196/1/level2_2025W17_4B_0001_1D1_spx_l2b-v27-2026-196.fits'
    _, headers = m._http(m.OFFICIAL_ROOT+key, 65536, {'Range': 'bytes=0-65535'}, ranged=True)
    total = headers['content-range'].split('/')[1]
    identity = json.dumps([headers.get('etag'), total, headers.get('last-modified')])
    idx = m.MirrorIndex(tmp_path/'live.sqlite', releases=['dr1'])
    row = idx._object(key, identity)
    result = json.loads(row[3])
    assert result['observation']['observation_date'] == '2025-04-24T18:01:05.843Z'
    assert result['observation']['detector_array'] == 1
    assert result['observation']['release'] == 'DR1'
    assert result['accessUrl'] == m.OFFICIAL_ROOT+key
    footprint = np.asarray(json.loads(row[4]))
    assert m._region('CIRCLE 160.6175 30.6694 0.01')(footprint)
    assert not m._region('CIRCLE 20 -50 0.01')(footprint)


def test_capacity_limit_preserves_partial_results_and_resume_cursor(tmp_path, s3, monkeypatch):
    add(s3)
    add(s3, 'b', ra=50)
    idx = index(tmp_path, s3)
    assert not idx.scan(max_pages=1)['index']['complete']
    cursor = idx.status()['releases'][0]['token']
    monkeypatch.setenv('IRSA_MIRROR_MAX_INDEX_BYTES', '1')
    bounded = index(tmp_path, s3).scan(max_pages=1)
    assert bounded['errors'][0]['code'] == 'archive_mirror_capacity'
    assert not bounded['index']['complete']
    assert bounded['index']['objects_indexed'] == 1
    assert bounded['index']['releases'][0]['token'] == cursor
    assert len(s3['requests']) == 1
    partial = index(tmp_path, s3).search({'position': 'CIRCLE 359.9 1 0.01'})
    assert len(partial['images']) == 1
    assert partial['images'][0]['observation']['header_metadata']['discovery_complete'] == 'false'
    monkeypatch.delenv('IRSA_MIRROR_MAX_INDEX_BYTES')
    assert index(tmp_path, s3).scan(max_pages=1)['index']['complete']


def test_capacity_limit_before_initial_scan_never_claims_complete(tmp_path, s3, monkeypatch):
    add(s3)
    monkeypatch.setenv('IRSA_MIRROR_MAX_INDEX_BYTES', '1')
    result = index(tmp_path, s3).scan()
    assert result['errors'][0]['code'] == 'archive_mirror_capacity'
    assert not result['index']['complete']
    assert result['index']['objects_indexed'] == 0
    assert not s3['requests']


def test_release_round_robin_does_not_starve_sky_after_bad_first_object(tmp_path, s3):
    first = add(s3)
    add(s3, 'b')
    s3['fail'].add(first)
    s3['objects']['dr1/level2/visit/version/1/dr1.fits'] = image(ra=80)
    s3['objects']['qr3/level2/visit/version/1/qr3.fits'] = image(ra=120)
    m = module()
    def reopen():
        return m.MirrorIndex(tmp_path/'round-robin.sqlite', s3['root'], ['qr2', 'dr1', 'qr3'])
    for _ in range(3):
        result = reopen().scan(max_pages=1)
    assert result['index']['failed_objects'] == 1
    assert not result['index']['complete']
    assert result['index']['objects_indexed'] == 2
    for position, release in [('CIRCLE 80 1 0.01', 'DR1'), ('CIRCLE 120 1 0.01', 'QR3')]:
        found = reopen().search({'position': position})
        assert found['images'][0]['observation']['release'] == release
        assert found['images'][0]['observation']['header_metadata']['discovery_complete'] == 'false'
    assert reopen().scan(max_pages=1)['index']['objects_indexed'] == 3


def test_retry_backoff_is_persisted_and_errors_are_bounded(tmp_path, s3, monkeypatch):
    import time
    clock = [time.time()]
    monkeypatch.setattr(module().time, 'time', lambda: clock[0])
    key = add(s3)
    s3['fail'].add(key)
    result = index(tmp_path, s3).scan()
    assert result['index']['listing_complete']
    assert not result['index']['complete']
    row = index(tmp_path, s3).db.execute('SELECT * FROM mirror_retries').fetchone()
    assert row['key'] == key
    assert row['identity']
    assert row['attempts'] == 1
    assert row['last_attempt'] == clock[0]
    assert row['next_attempt'] > clock[0]
    assert len(row['error']) <= 640
    clock[0] += 61
    index(tmp_path, s3).scan()
    retried = index(tmp_path, s3).db.execute('SELECT * FROM mirror_retries').fetchone()
    assert retried['attempts'] == 2
    assert retried['next_attempt'] >= clock[0]+120


def test_capacity_does_not_persist_failed_queue_or_move_cursor(tmp_path, s3, monkeypatch):
    key = add(s3)
    s3['fail'].add(key)
    idx = index(tmp_path, s3)
    monkeypatch.setattr(idx, '_capacity', lambda extra=0: (_ for _ in ()).throw(module().MirrorError('archive_mirror_capacity', 'full')) if extra else None)
    result = idx.scan()
    assert result['errors'][-1]['code'] == 'archive_mirror_capacity'
    assert not result['index']['complete']
    assert result['index']['failed_objects'] == 0
    assert result['index']['releases'][0]['token'] is None
    assert not result['index']['releases'][0]['complete']


def test_many_bad_objects_have_bounded_report_and_retry_batch(tmp_path, s3, monkeypatch):
    import time
    clock = [time.time()]
    monkeypatch.setattr(module().time, 'time', lambda: clock[0])
    for n in range(30):
        add(s3, f'bad{n:02d}')
    s3['page'] = 100
    s3['bad_range'] = True
    first = index(tmp_path, s3).scan(page_size=100)
    assert first['index']['listing_complete']
    assert first['index']['failed_objects'] == 30
    assert first['errors_total'] == 30
    assert len(first['errors']) == 20
    assert len(s3['requests']) == 30
    clock[0] += 61
    second = index(tmp_path, s3).scan(page_size=100, workers=1)
    assert second['retry_objects_processed'] == 2
    assert len(s3['requests']) == 32
    assert second['index']['failed_objects'] == 30
    assert not second['index']['complete']


def test_spatial_catalog_filters_before_exact_geometry(tmp_path, s3, monkeypatch):
    add(s3, 'near')
    add(s3, 'far', ra=180, dec=-20)
    s3['page'] = 100
    idx = index(tmp_path, s3)
    idx.scan()
    m = module()
    original = m._region
    calls = []
    def counted(position):
        exact = original(position)
        def check(poly):
            calls.append(poly)
            return exact(poly)
        return check
    monkeypatch.setattr(m, '_region', counted)
    found = idx.search({'position': 'CIRCLE 359.9 1 0.01'})
    assert len(found['images']) == 1
    assert len(calls) == 1
    assert idx.db.execute('SELECT COUNT(*) FROM mirror_spatial').fetchone()[0] == 2


def test_spatial_catalog_migrates_old_rows_without_redownload(tmp_path, s3):
    add(s3)
    idx = index(tmp_path, s3)
    idx.scan()
    idx.db.execute('DROP TABLE IF EXISTS mirror_spatial')
    idx.db.commit()
    idx.db.close()
    resumed = index(tmp_path, s3)
    assert len(resumed.search({'position': 'RANGE 359.8 0.1 0.9 1.1'})['images']) == 1
    assert len(s3['requests']) == 1
    assert resumed.db.execute('SELECT COUNT(*) FROM mirror_spatial').fetchone()[0] == 1


@pytest.mark.parametrize('position', [
    'CIRCLE 0 89.9 0.2', 'CIRCLE 359.95 1 0.1',
    'RANGE 350 10 -2 3', 'RANGE 0 360 89 90',
    'RANGE 170 190 -30 30',
    'POLYGON 359 -1 1 -1 1 3 359 3',
    'POLYGON 0 88 120 88 240 88',
])
def test_spatial_prefilter_preserves_exact_spherical_results(tmp_path, s3, position):
    for n, (ra, dec) in enumerate([(359.9, 1), (0, 89.8), (180, 0), (100, -30)]):
        add(s3, str(n), ra=ra, dec=dec)
    s3['page'] = 100
    idx = index(tmp_path, s3)
    idx.scan()
    m = module()
    expected = {m._decode(row['body'])['observation']['frame_id'] for row in idx.db.execute('SELECT body,footprint FROM mirror_objects')
                if m._region(position)(np.asarray(m._decode(row['footprint'])))}
    actual = {item['observation']['frame_id'] for item in idx.search({'position': position})['images']}
    assert actual == expected
