"""Production callers share the gateway without inventing native science metadata."""
import copy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading

import pytest
from astropy.coordinates import SkyCoord
import astropy.units as u

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'pipeline'))
from spherex import query
from science.motion import live

KEY = 'qr2/level2/2025W17_4B/SCIENCE/1/level2_2025W17_4B_0001_1D1_spx_l2b-v1.fits'
MIRROR = 'https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/' + KEY
IBE = 'https://irsa.ipac.caltech.edu/ibe/data/spherex/' + KEY


def image(**changes):
    item = {'observation': {'frame_id': 'actual-archive-product-id',
            'observation_date': '2025-04-24T18:01:05.843Z', 'detector_array': 1, 'release': 'QR2',
            'header_metadata': {'discovery_source': 's3_mirror', 'dataproduct_subtype': 'science'}},
            'accessUrl': MIRROR}
    item.update(changes)
    return item


@pytest.fixture
def gateway(monkeypatch):
    state = {'body': {'images': [image()], 'discovery_complete': False}, 'status': 200, 'requests': []}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            state['requests'].append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            body = state.get('raw', json.dumps(state['body']).encode())
            self.send_response(state['status'])
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    monkeypatch.setenv('IRSA_DISCOVERY_URL', f'http://127.0.0.1:{server.server_port}/api/irsa/discovery')
    def forbidden(*args, **kwargs):
        raise AssertionError('Configured caller attempted direct SIA')
    monkeypatch.setattr(query.Irsa, 'query_sia', forbidden)
    monkeypatch.setattr(live, 'read_archive', forbidden)
    yield state
    server.shutdown()
    server.server_close()
    worker.join()


def search():
    return query.image_search(SkyCoord(359.9 * u.deg, 1 * u.deg), 0.2, query.DEFAULT, allow_release_fallback=True)


def test_pipeline_table_keeps_actual_release_date_and_native_cutout_url(gateway):
    table = search()
    assert list(table['access_url']) == [IBE]
    assert list(table['energy_bandpassname']) == ['SPHEREx-D1']
    assert list(table['dataproduct_subtype']) == ['science']
    assert list(table['obs_collection']) == ['spherex_qr2']
    assert table[0]['t_min'] == pytest.approx(60789.75076207176)
    assert table[0]['source_url'] == MIRROR
    assert table.meta['discovery_complete'] is False
    assert table.meta['discovery_source'] == ['s3_mirror']
    assert gateway['requests'] == [('/api/irsa/discovery', {
        'right_ascension_deg': 359.9, 'declination_deg': 1.0, 'radius_degrees': 0.1})]
    # Native pipeline consumers iterate Astropy Rows and append the IBE cutout arguments.
    assert query.detector(table[0]) == 'SPHEREx-D1'
    assert str(table[0]['access_url']).split('?')[0] + '?center=359.9,1&size=0.1' == IBE + '?center=359.9,1&size=0.1'


def test_motion_uses_gateway_with_detector_and_utc_bounds(gateway):
    exposures = live.discover(359.9, 1.0, 1, 60789, 60790)
    assert len(exposures) == 1
    assert exposures[0].id == '2025W17_4B_0001_1D1'
    assert exposures[0].release == 'QR2'
    assert exposures[0].url == IBE
    assert exposures[0].mjd == pytest.approx(60789.75076207176)
    assert exposures.discovery_complete is False
    assert exposures.discovery_source == ['s3_mirror']
    assert gateway['requests'][0][1] == {
        'right_ascension_deg': 359.9, 'declination_deg': 1.0, 'radius_degrees': 0.001,
        'detector_array': 1, 'observed_after': '2025-04-24T00:00:00Z', 'observed_before': '2025-04-25T00:00:00Z'}


@pytest.mark.parametrize('status,raw', [(503, b'{"error":"archive_mirror_index_warming"}'),
                                        (200, b'not json'), (200, b'{"images":[]}')])
def test_configured_gateway_error_never_falls_through_to_sia(gateway, status, raw):
    gateway.update(status=status, raw=raw)
    with pytest.raises(ValueError):
        search()
    with pytest.raises(live.SearchError) as exc:
        live.discover(359.9, 1, 1, 60789, 60790)
    assert exc.value.status == (503 if status == 503 else 502)


@pytest.mark.parametrize('mutation', ['untrusted', 'traversal', 'query', 'missing_date', 'bad_detector', 'release_mismatch', 'bad_identity'])
def test_untrusted_or_malformed_scientific_rows_are_rejected(gateway, mutation):
    bad = copy.deepcopy(image())
    if mutation == 'untrusted':
        bad['accessUrl'] = 'https://evil.example/' + KEY
    elif mutation == 'traversal':
        bad['accessUrl'] = MIRROR.replace('/SCIENCE/', '/../SCIENCE/')
    elif mutation == 'query':
        bad['accessUrl'] += '?center=1,2'
    elif mutation == 'missing_date':
        bad['observation']['observation_date'] = ''
    elif mutation == 'bad_detector':
        bad['observation']['detector_array'] = 7
    elif mutation == 'release_mismatch':
        bad['observation']['release'] = 'DR1'
    else:
        bad['observation']['frame_id'] = ''
    gateway['body']['images'] = [bad]
    with pytest.raises(ValueError):
        search()


def test_unknown_science_type_is_not_promoted_to_science(gateway):
    bad = image(accessUrl=IBE.replace('/SCIENCE/', '/UNKNOWN/'))
    bad['observation']['header_metadata'] = {'discovery_source': 'sia'}
    gateway['body']['images'] = [bad]
    assert len(search()) == 0


def test_records_are_sorted_by_real_time_and_keep_each_release(gateway):
    later = image(accessUrl=IBE.replace('/qr2/', '/dr1/'))
    later['observation'].update(frame_id='later-native-product', release='DR1', observation_date='2025-04-25T00:00:00Z')
    gateway['body']['images'] = [later, image()]
    table = search()
    assert list(table['obs_collection']) == ['spherex_qr2', 'spherex_dr1']
    assert list(table['t_min']) == sorted(table['t_min'])


def test_gateway_response_is_bounded(gateway):
    from science import archive_gateway
    gateway['raw'] = b' ' * (archive_gateway.MAX_RESPONSE_BYTES + 1)
    with pytest.raises(ValueError, match='limit'):
        search()


def test_motion_rechecks_detector_time_and_native_filename(gateway):
    assert live.discover(359.9, 1, 2, 60789, 60790) == []
    assert live.discover(359.9, 1, 1, 60790, 60791) == []
    gateway['body']['images'] = [image(accessUrl=IBE.replace('level2_2025W17_4B_0001_1D1_spx_l2b-v1.fits', 'invented.fits'))]
    assert live.discover(359.9, 1, 1, 60789, 60790) == []


def test_unconfigured_standalone_pipeline_import_needs_no_shared_package(monkeypatch):
    import os
    import subprocess
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'pipeline'))
    env.pop('IRSA_DISCOVERY_URL', None)
    result = subprocess.run([sys.executable, '-c', 'from spherex.query import DEFAULT; assert DEFAULT.startswith("spherex_")'],
                            cwd=ROOT / 'pipeline', env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_nondefault_collection_filters_using_actual_gateway_release(gateway):
    result = query.image_search(SkyCoord(359.9 * u.deg, 1 * u.deg), 0.2, 'spherex_qr3')
    assert len(result) == 0
    assert result.meta['discovery_complete'] is False


def test_direct_votable_parser_accepts_real_qr2_and_rejects_calibration():
    columns = ['access_url', 'energy_bandpassname', 'dataproduct_subtype', 'obs_collection', 't_min']
    fields = ''.join(f'<FIELD name="{c}"/>' for c in columns)
    values = ''.join(f'<TD>{v}</TD>' for v in [IBE, 'SPHEREx-D1', 'science', 'spherex_qr2', '60789.75'])
    xml = f'<VOTABLE><RESOURCE><INFO name="QUERY_STATUS" value="OK"/><TABLE>{fields}<DATA><TABLEDATA><TR>{values}</TR></TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>'.encode()
    exposures = live.parse_exposures(xml, 1, 60789, 60790)
    assert len(exposures) == 1
    assert exposures[0].release == 'QR2'
    assert exposures[0].mjd == 60789.75
    assert live.parse_exposures(xml.replace(b'>science<', b'>calibration<'), 1, 60789, 60790) == []


@pytest.mark.parametrize('route,method', [('/api/cutout/search', 'post'), ('/api/cutout/render?ra=359.9&dec=1', 'get'),
                                         ('/api/spectrum?ra=359.9&dec=1', 'get')])
def test_pipeline_http_routes_propagate_warming_instead_of_empty_sky(gateway, route, method):
    from fastapi.testclient import TestClient
    from pipeline.service import app
    gateway['status'] = 503
    client = TestClient(app)
    response = client.post(route, json={'ra': 359.9, 'dec': 1}) if method == 'post' else client.get(route)
    assert response.status_code == 503
    assert 'total' not in response.json()


def test_pipeline_http_search_preserves_fallback_provenance(gateway):
    from fastapi.testclient import TestClient
    from pipeline.service import app
    response = TestClient(app).post('/api/cutout/search', json={'ra': 359.9, 'dec': 1})
    assert response.status_code == 200
    result = response.json()
    assert result['discovery_complete'] is False
    assert result['discovery_source'] == ['s3_mirror']
    assert result['results'][0]['release'] == 'QR2'
    assert result['results'][0]['source_url'] == MIRROR
    assert result['results'][0]['observation_date'] == '2025-04-24T18:01:05.843Z'


def test_pipeline_render_downloads_ibe_cutout_and_exposes_native_provenance(gateway, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from astropy.io import fits
    import numpy as np
    from pipeline import service
    monkeypatch.setattr(service, 'CUTOUT_CACHE_DIR', tmp_path)
    def cutout(url, path, **kwargs):
        assert url == IBE + '?center=359.9,1.0&size=0.05'
        hdus = [fits.PrimaryHDU()]
        for name in ('IMAGE', 'ZODI', 'FLAGS', 'VARIANCE'):
            hdus.append(fits.ImageHDU(np.ones((4, 4)), name=name))
        fits.HDUList(hdus).writeto(path)
        return 'good'
    monkeypatch.setattr(service, 'cutout', cutout)
    response = TestClient(service.app).get('/api/cutout/render?ra=359.9&dec=1')
    assert response.status_code == 200
    assert response.content.startswith(b'\x89PNG\r\n\x1a\n')
    assert response.headers['X-IRSA-Discovery-Complete'] == 'false'
    assert response.headers['X-IRSA-Release'] == 'QR2'
    assert response.headers['X-IRSA-Discovery-Source'] == 's3_mirror'
    assert response.headers['X-IRSA-Source-Url'] == MIRROR


def test_motion_retains_original_mirror_source_per_exposure(gateway):
    exposure = live.discover(359.9, 1, 1, 60789, 60790)[0]
    assert exposure.source_url == MIRROR
    assert exposure.discovery_source == 's3_mirror'


@pytest.mark.parametrize('url', [MIRROR.replace('/SCIENCE/', '/SCI\nENCE/'), MIRROR + '/more', MIRROR.replace('https:', 'http:')])
def test_url_normalization_cannot_silently_change_original_object(gateway, url):
    gateway['body']['images'] = [image(accessUrl=url)]
    with pytest.raises(ValueError):
        search()


@pytest.mark.parametrize('route', ['/api/cutout/render?ra=359.9&dec=1', '/api/spectrum?ra=359.9&dec=1'])
def test_partial_empty_discovery_is_not_reported_as_absent_coverage(gateway, route):
    from fastapi.testclient import TestClient
    from pipeline.service import app
    gateway['body']['images'] = []
    response = TestClient(app).get(route)
    assert response.status_code == 503
    assert 'incomplete' in response.json()['detail'].lower()


def test_pipeline_spectrum_keeps_source_and_actual_release(gateway, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from pipeline import service
    monkeypatch.setattr(service, 'CUTOUT_CACHE_DIR', tmp_path)
    def cutout(url, path, **kwargs):
        assert url.startswith(IBE + '?center=')
        path.write_bytes(b'external-cutout')
        return 'good'
    monkeypatch.setattr(service, 'cutout', cutout)
    # Photometry is a separate tested boundary; this test verifies archive provenance survives its result.
    monkeypatch.setattr(service, 'measure_cutout_point', lambda *a, **k: {
        'detector': 'D1', 'wavelength_um': 1.0, 'bandwidth_um': 0.02, 'flux_mjy': 2.0,
        'uncertainty_mjy': 0.1, 'snr': 20.0, 'mjd': 60789.75})
    response = TestClient(service.app).get('/api/spectrum?ra=359.9&dec=1')
    assert response.status_code == 200
    payload = response.json()
    assert payload['discovery_complete'] is False
    assert payload['discovery_source'] == ['s3_mirror']
    assert payload['spectrum'][0]['release'] == 'QR2'
    assert payload['spectrum'][0]['source_url'] == MIRROR


def test_partial_motion_index_cannot_establish_insufficient_sky_visits(gateway):
    from datetime import date
    with pytest.raises(live.SearchError) as exc:
        live.search_motion(359.9, 1, 1, date(2025, 4, 24), date(2025, 4, 24), 3, True)
    assert exc.value.status == 503
    assert 'incomplete' in str(exc.value).lower()


def test_gateway_product_id_is_not_relabelled_as_native_publisher_did(gateway):
    table = search()
    assert table[0]['frame_id'] == 'actual-archive-product-id'
    assert 'obs_publisher_did' not in table.colnames


def test_configured_standalone_script_locates_shared_client(gateway):
    import os
    import subprocess
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'pipeline'))
    result = subprocess.run([sys.executable, '-c',
        'from astropy.coordinates import SkyCoord; from spherex.query import image_search,DEFAULT; '
        'r=image_search(SkyCoord(359.9,1,unit="deg"),0.2,DEFAULT,allow_release_fallback=True); print(r[0]["obs_collection"])'],
        cwd=ROOT / 'pipeline', env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'spherex_qr2'
    assert len(gateway['requests']) == 1


def test_explicit_default_collection_is_an_exact_release_filter(gateway):
    result = query.image_search(SkyCoord(359.9 * u.deg, 1 * u.deg), 0.2, 'spherex_dr1')
    assert len(result) == 0


@pytest.mark.parametrize('collection,expected_total', [(None, 1), ('spherex_dr1', 0), ('spherex_qr2', 1)])
def test_http_collection_fallback_only_when_collection_is_omitted(gateway, collection, expected_total):
    from fastapi.testclient import TestClient
    from pipeline.service import app
    body = {'ra': 359.9, 'dec': 1}
    if collection is not None:
        body['collection'] = collection
    response = TestClient(app).post('/api/cutout/search', json=body)
    assert response.status_code == 200
    payload = response.json()
    assert payload['total'] == expected_total
    if expected_total:
        assert payload['results'][0]['release'] == 'QR2'
        assert payload['results'][0]['obs_collection'] == 'spherex_qr2'


@pytest.fixture
def native_cutout(monkeypatch):
    """Replace only external S3 transport; consumers still read real FITS pixels."""
    from astropy.io import fits
    import numpy as np
    from backend.python import irsa_cutout
    calls = []
    def crop(source, selection, output, **limits):
        assert source == MIRROR
        assert selection.startswith(IBE + '?center=359.9,1.0&size=')
        assert limits['max_output_bytes'] == 24 * 1024 * 1024
        assert limits['max_network_bytes'] == 24 * 1024 * 1024
        assert limits['timeout_seconds'] == 18
        calls.append(selection)
        header = live.grid_coordinates(359.9, 1, 12, 12, live.PIXEL_SCALE)[0].to_header()
        header.update({'MJD-AVG': 60789.75, 'DATE-AVG': '2025-04-24T18:00:00'})
        hdus = [fits.PrimaryHDU()]
        for name, data in [('IMAGE', np.arange(144).reshape(12, 12) + 10),
                           ('ZODI', np.ones((12, 12))), ('FLAGS', np.zeros((12, 12), dtype='int32')),
                           ('VARIANCE', np.ones((12, 12)))]:
            hdus.append(fits.ImageHDU(data, header=header, name=name))
        fits.HDUList(hdus).writeto(output, overwrite=True)
        return {'ok': True}
    monkeypatch.setattr(irsa_cutout, 'cutout', crop)
    def no_ibe(*args, **kwargs):
        raise AssertionError('Explicit mirror selection attempted IBE transport')
    from science import archive_gateway
    monkeypatch.setattr(archive_gateway, 'read_cutout', no_ibe)
    monkeypatch.setattr(live, 'read_archive', no_ibe)
    return calls


def test_motion_selected_mirror_loads_real_pixels_without_ibe(native_cutout, tmp_path):
    exposure = live.Exposure('2025W17_4B_0001_1D1', 60789.75, IBE, 'QR2', MIRROR, 's3_mirror')
    _, sky = live.grid_coordinates(359.9, 1, 8, 8, live.PIXEL_SCALE)
    row, reason = live.load_exposure(exposure, tmp_path, (359.9, 1.0), 0.05, sky, False)
    assert reason is None
    assert row[0] == 60789.75
    assert row[3].shape == (8, 8)
    assert len(native_cutout) == 1


def test_pipeline_selected_mirror_downloads_without_ibe(native_cutout, tmp_path):
    from astropy.io import fits
    out = tmp_path / 'cutout.fits'
    status = query.cutout(IBE + '?center=359.9,1.0&size=0.05', out,
                          source_url=MIRROR, discovery_source='s3_mirror')
    assert status == 'good'
    with fits.open(out) as hdus:
        assert hdus['IMAGE'].data[0, 0] == 10
    assert len(native_cutout) == 1


def test_pipeline_render_uses_selected_mirror_during_ibe_outage(gateway, native_cutout, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from pipeline import service
    monkeypatch.setattr(service, 'CUTOUT_CACHE_DIR', tmp_path)
    response = TestClient(service.app).get('/api/cutout/render?ra=359.9&dec=1')
    assert response.status_code == 200
    assert response.content.startswith(b'\x89PNG\r\n\x1a\n')
    assert len(native_cutout) == 1


def test_pipeline_retryable_ibe_fault_uses_exact_mirror_key(native_cutout, monkeypatch, tmp_path):
    from urllib.error import HTTPError
    from science import archive_gateway
    def unavailable(*args, **kwargs):
        raise HTTPError(IBE, 503, 'unavailable', {}, None)
    monkeypatch.setattr(archive_gateway, 'read_cutout', unavailable, raising=False)
    status = query.cutout(IBE + '?center=359.9,1.0&size=0.05', tmp_path / 'recovered.fits')
    assert status == 'good'
    assert len(native_cutout) == 1


@pytest.mark.parametrize('status', [400, 403, 404])
def test_nonretryable_ibe_status_does_not_request_mirror(native_cutout, monkeypatch, tmp_path, status):
    from urllib.error import HTTPError
    from science import archive_gateway
    def rejected(*args, **kwargs):
        raise HTTPError(IBE, status, 'rejected', {}, None)
    monkeypatch.setattr(archive_gateway, 'read_cutout', rejected, raising=False)
    result = query.cutout(IBE + '?center=359.9,1.0&size=0.05', tmp_path / 'absent.fits', retries=1)
    assert f'HTTP Error {status}' in result
    assert native_cutout == []


def test_conflicting_mirror_source_cannot_select_another_object(native_cutout, tmp_path):
    result = query.cutout(IBE + '?center=359.9,1.0&size=0.05', tmp_path / 'unsafe.fits', retries=1,
                          source_url=MIRROR.replace('0001_', '0002_'), discovery_source='s3_mirror')
    assert result.startswith('failure:')
    assert native_cutout == []


def test_primary_ibe_provenance_can_fallback_to_identical_mirror(native_cutout, monkeypatch, tmp_path):
    from urllib.error import URLError
    from science import archive_gateway
    def unavailable(*args, **kwargs):
        raise URLError('connection unavailable')
    monkeypatch.setattr(archive_gateway, 'read_cutout', unavailable)
    status = query.cutout(IBE + '?center=359.9,1.0&size=0.05', tmp_path / 'primary.fits', retries=1,
                          source_url=IBE, discovery_source='sia')
    assert status == 'good'
    assert len(native_cutout) == 1


def test_invalid_ibe_content_never_selects_mirror(native_cutout, monkeypatch, tmp_path):
    from science import archive_gateway
    monkeypatch.setattr(archive_gateway, 'read_cutout', lambda *a: b'not FITS')
    out = tmp_path / 'invalid.fits'
    result = query.cutout(IBE + '?center=359.9,1.0&size=0.05', out, retries=1)
    assert result.startswith('failure:')
    assert not out.exists()
    assert not out.with_suffix('.part').exists()
    assert native_cutout == []


def test_pipeline_spectrum_uses_selected_mirror_during_ibe_outage(gateway, native_cutout, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from pipeline import service
    monkeypatch.setattr(service, 'CUTOUT_CACHE_DIR', tmp_path)
    monkeypatch.setattr(service, 'measure_cutout_point', lambda *a, **k: {
        'detector': 'D1', 'wavelength_um': 1.0, 'bandwidth_um': 0.02, 'flux_mjy': 2.0,
        'uncertainty_mjy': 0.1, 'snr': 20.0, 'mjd': 60789.75})
    response = TestClient(service.app).get('/api/spectrum?ra=359.9&dec=1')
    assert response.status_code == 200
    assert response.json()['spectrum'][0]['source_url'] == MIRROR
    assert len(native_cutout) == 1


def test_selected_mirror_failure_has_no_ibe_retry_delay(monkeypatch, tmp_path):
    from backend.python import irsa_cutout
    attempts = []
    def unavailable(*args, **kwargs):
        attempts.append(args[0])
        raise irsa_cutout.CutoutError('archive_cutout_http', 'S3 temporarily unavailable')
    def no_delay(*args):
        raise AssertionError('Selected mirror entered the legacy IBE retry loop')
    monkeypatch.setattr(irsa_cutout, 'cutout', unavailable)
    monkeypatch.setattr(query.time, 'sleep', no_delay)
    result = query.cutout(IBE + '?center=359.9,1.0&size=0.05', tmp_path / 'unavailable.fits',
                          source_url=MIRROR, discovery_source='s3_mirror')
    assert result.startswith('failure:')
    assert attempts == [MIRROR]


@pytest.mark.parametrize('declare_length', [False, True])
def test_ibe_reader_enforces_byte_budget_on_real_http_response(declare_length):
    from science import archive_gateway
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            self.send_response(200)
            if declare_length:
                self.send_header('Content-Length', '256')
            self.end_headers()
            self.wfile.write(b'x' * 256)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with pytest.raises(ValueError, match='byte limit'):
            archive_gateway.read_cutout(f'http://127.0.0.1:{server.server_port}/cutout', 128)
    finally:
        server.shutdown()
        server.server_close()
        worker.join()
