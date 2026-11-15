"""Native cutouts exercise actual FITS bytes over a strict HTTP Range fixture."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.parse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS, Sip

MODULE = Path(__file__).parents[1] / 'python' / 'irsa_cutout.py'
SOURCE = 'https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/dr1/level2/a.fits'
CUTOUT = 'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/a.fits?center=10,20deg&size=0.04deg'


def implementation():
    assert MODULE.exists(), 'native S3 range cutout implementation is missing'
    spec = importlib.util.spec_from_file_location('irsa_cutout', MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def archive(*, cube=False, compressed=False):
    w = WCS(naxis=2)
    w.wcs.crpix = [101, 81]
    w.wcs.crval = [10, 20]
    w.wcs.cd = np.array([[-0.001, 0.0002], [0.0002, 0.001]])
    w.wcs.ctype = ['RA---TAN-SIP', 'DEC--TAN-SIP']
    a = np.zeros((3, 3)); b = a.copy()
    a[2, 0] = 3e-5; b[0, 2] = -2e-5
    w.sip = Sip(a, b, None, None, w.wcs.crpix)
    h = w.to_header(relax=True)
    h['CRPIX1A'] = 0.; h['CRPIX2A'] = 0.
    h['CRPIX1W'] = 0.; h['CRPIX2W'] = 0.
    h['OBSID'] = 'original-observation'
    data = np.arange(160 * 200, dtype=np.float32).reshape(160, 200)
    image = fits.ImageHDU(data, h, name='IMAGE')
    if cube: image = fits.ImageHDU(data[None, ...], name='IMAGE')
    if compressed: image = fits.CompImageHDU(data, h, name='IMAGE')
    flags = (np.arange(data.size, dtype=np.uint32).reshape(data.shape) + 2**31)
    table = fits.BinTableHDU.from_columns([fits.Column(name='VALUES', format='3E', array=[[1., 2., 3.]])], name='WCS-WAVE')
    hdus = fits.HDUList([fits.PrimaryHDU(header=fits.Header({'VERSION': 'real-pipeline'})), image,
                        fits.ImageHDU(flags, h, name='FLAGS'), fits.ImageHDU(data + 0.5, h, name='VARIANCE'),
                        fits.ImageHDU(data + 2., h, name='ZODI'), fits.ImageHDU(data + 3., h, name='WAVELENGTH'), table])
    output = io.BytesIO(); hdus.writeto(output)
    return output.getvalue(), hdus


@contextmanager
def server(body, *, mode=None):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *args): pass
        def do_GET(self):
            requests.append(dict(self.headers))
            start, end = map(int, self.headers['Range'][6:].split('-'))
            if mode == 'redirect':
                self.send_response(302); self.send_header('Location', 'https://evil.test/a'); self.send_header('Content-Length','0'); self.end_headers(); return
            chunk = body[start:end + 1]
            if mode=='slow-headers' and len(requests)>1:time.sleep(0.08)
            self.send_response(200 if mode == 'full' else 206)
            self.send_header('Content-Range', f'bytes {start}-{end}/{len(body)}' if mode != 'wrong-range' else f'bytes 0-{end}/{len(body)}')
            self.send_header('Content-Length', str(len(chunk)))
            self.send_header('ETag', '"changed"' if mode == 'changed' and len(requests)>1 else '"fixture"')
            self.send_header('Content-Type', 'text/html' if mode == 'html' else 'application/fits')
            if mode == 'compressed': self.send_header('Content-Encoding', 'gzip')
            self.end_headers()
            if mode=='slow-headers' and len(requests)==1:time.sleep(0.08)
            try:self.wfile.write(chunk)
            except (BrokenPipeError,ConnectionResetError):pass
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    try: yield f'http://127.0.0.1:{http.server_port}/dr1/level2/a.fits', requests
    finally: http.shutdown(); http.server_close(); thread.join()


def test_native_planes_and_tables_keep_pixels_sip_and_alternate_coordinates(tmp_path):
    module = implementation()
    body, original = archive()
    path = tmp_path / 'cut.fits'
    with server(body) as (url, requests):
        result = module.cutout(url, CUTOUT, path, allow_loopback=True)
    assert result['ok'] is True
    x0, y0, x1, y1 = result['bounds']
    assert x0 < 100 < x1 and y0 < 80 < y1
    assert 35 <= x1-x0 <= 50 and 35 <= y1-y0 <= 50
    with fits.open(path) as cut:
        assert [h.name for h in cut] == [h.name for h in original]
        for name in ('IMAGE', 'FLAGS', 'VARIANCE', 'ZODI', 'WAVELENGTH'):
            np.testing.assert_array_equal(cut[name].data, original[name].data[y0:y1, x0:x1])
            assert cut[name].header['OBSID'] == 'original-observation'
            assert cut[name].header['CRPIX1W'] == -x0
            assert cut[name].header['CRPIX2A'] == -y0
            before = WCS(original[name].header).all_pix2world([[x0, y0], [x1-1,y1-1]], 0)
            after = WCS(cut[name].header).all_pix2world([[0,0], [x1-x0-1,y1-y0-1]],0)
            np.testing.assert_allclose(after, before, atol=1e-10, rtol=0)
        np.testing.assert_array_equal(cut['WCS-WAVE'].data, original['WCS-WAVE'].data)
        assert cut[0].header['SRCURL'] == url
    assert len(requests)>2
    assert all(r.get('If-Match') == '"fixture"' for r in requests[1:])
    assert result['networkBytes'] < len(body)


@pytest.mark.parametrize('source', [SOURCE.replace('https:', 'http:'), SOURCE+'?x=1', SOURCE.replace('.com/', '.com:443/'), SOURCE.replace('/a.fits','/../a.fits'), SOURCE.replace('/a.fits','/%2e%2e/a.fits'), SOURCE.replace('nasa-irsa-spherex.s3.us-east-1.amazonaws.com','evil.test'), 'http://127.0.0.1:80/a.fits'])
def test_untrusted_source_rejected_before_fetch(source,tmp_path):
    module=implementation()
    with pytest.raises(module.CutoutError): module.cutout(source,CUTOUT,tmp_path/'cut.fits')


@pytest.mark.parametrize('mode', ['full','wrong-range','redirect','changed','html','compressed'])
def test_bad_transport_leaves_no_partial_output(mode,tmp_path):
    module=implementation(); body,_=archive(); path=tmp_path/'cut.fits'
    with server(body,mode=mode) as (url,_):
        with pytest.raises(module.CutoutError): module.cutout(url,CUTOUT,path,allow_loopback=True)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('kind',['cube','compressed'])
def test_unsupported_arrays_fail_explicitly(kind,tmp_path):
    module=implementation(); body,_=archive(**{kind:True})
    with server(body) as (url,_):
        with pytest.raises(module.CutoutError,match='unsupported'): module.cutout(url,CUTOUT,tmp_path/'cut.fits',allow_loopback=True)
    assert list(tmp_path.iterdir()) == []


def test_off_image_and_budget_failure_do_not_publish(tmp_path):
    module=implementation(); body,_=archive()
    with server(body) as (url,_):
        with pytest.raises(module.CutoutError): module.cutout(url,CUTOUT.replace('10,20deg','50,60deg'),tmp_path/'cut.fits',allow_loopback=True)
        with pytest.raises(module.CutoutError): module.cutout(url,CUTOUT,tmp_path/'cut.fits',allow_loopback=True,max_network_bytes=100)
    assert list(tmp_path.iterdir()) == []


def test_cli_emits_structured_json_error_without_creating_output(tmp_path):
    implementation()
    result=subprocess.run([sys.executable,str(MODULE),'--source','https://evil.test/a.fits','--cutout',CUTOUT,'--output',str(tmp_path/'cut.fits')],capture_output=True,text=True)
    assert result.returncode != 0
    assert json.loads(result.stdout)['error']['code']
    assert result.stderr == ''
    assert not list(tmp_path.iterdir())


def test_plain_degrees_clipping_and_atomic_existing_output(tmp_path):
    module=implementation(); body,original=archive(); path=tmp_path/'cut.fits'
    world=WCS(original['IMAGE'].header).all_pix2world([[1,1]],0)[0]
    selection=CUTOUT.split('?')[0]+f'?center={world[0]},{world[1]}&size=0.02'
    with server(body) as (url,_):
        result=module.cutout(url,selection,path,allow_loopback=True,timeout_seconds=18)
    assert result['bounds'][0:2] == [0,0]
    with fits.open(path) as h:
        x0,y0,x1,y1=result['bounds']
        np.testing.assert_array_equal(h['IMAGE'].data,original['IMAGE'].data[y0:y1,x0:x1])
    existing=path.read_bytes()
    with server(body,mode='changed') as (url,_):
        with pytest.raises(module.CutoutError): module.cutout(url,CUTOUT,path,allow_loopback=True)
    assert path.read_bytes()==existing
    assert list(tmp_path.iterdir()) == [path]


def test_short_deadline_cannot_publish_a_cutout(tmp_path):
    module=implementation(); body,_=archive()
    with server(body) as (url,_):
        with pytest.raises(module.CutoutError):
            module.cutout(url,CUTOUT,tmp_path/'cut.fits',allow_loopback=True,timeout_seconds=1e-9)
    assert list(tmp_path.iterdir()) == []


def test_rice_flags_fetches_needed_tiles_and_preserves_unsigned_values(tmp_path):
    module=implementation(); _,hdus=archive()
    original_flags=np.random.default_rng(42).integers(0,2**32,size=hdus['FLAGS'].data.shape,dtype=np.uint32)
    hdus[2]=fits.CompImageHDU(original_flags,hdus['FLAGS'].header,name='FLAGS',compression_type='RICE_1',tile_shape=(1,200))
    stream=io.BytesIO();hdus.writeto(stream);body=stream.getvalue()
    with server(body) as (url,requests):
        result=module.cutout(url,CUTOUT,tmp_path/'cut.fits',allow_loopback=True)
    with fits.open(tmp_path/'cut.fits') as out:
        x0,y0,x1,y1=result['bounds']
        np.testing.assert_array_equal(out['FLAGS'].data,original_flags[y0:y1,x0:x1])
        assert isinstance(out['FLAGS'],fits.ImageHDU)
        assert out['FLAGS'].header['OBSID']=='original-observation'
    with fits.open(io.BytesIO(body),disable_image_compression=True) as source:
        compressed=source['FLAGS'];start=compressed.fileinfo()['datLoc']
        heap=start+compressed.header['NAXIS1']*compressed.header['NAXIS2']
        end=heap+compressed.header['PCOUNT']
    # A whole compressed heap fetch would defeat remote row-tile selection.
    ranges=[tuple(map(int,r['Range'][6:].split('-'))) for r in requests]
    assert not any(a<=heap and b>=end-1 for a,b in ranges)


def test_cli_network_budget_is_enforced_before_first_range(tmp_path):
    implementation()
    result=subprocess.run([sys.executable,str(MODULE),'--source',SOURCE,'--cutout',CUTOUT,'--output',str(tmp_path/'cut.fits'),'--max-bytes','100'],capture_output=True,text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)['error']['code']=='archive_cutout_limit'
    assert result.stderr==''
    assert list(tmp_path.iterdir())==[]


def test_header_scanning_coalesces_ranges_under_the_same_byte_budget(tmp_path):
    module=implementation();body,_=archive()
    with server(body) as (url,requests):
        result=module.cutout(url,CUTOUT,tmp_path/'cut.fits',allow_loopback=True)
    assert len(requests)<=20
    assert result['nRanges']==len(requests)
    assert result['elapsedSeconds']>0


def test_deadline_also_bounds_the_next_response_headers():
    module=implementation();body,_=archive()
    with server(body,mode='slow-headers') as (url,_):
        remote=module._Ranges(urllib.parse.urlsplit(url),module.MAX_BYTES,0.12)
        started=time.monotonic()
        try:
            remote.read(0,2880)
            with pytest.raises(module.CutoutError):remote.read(2880,2880)
            assert time.monotonic()-started < 0.15
        finally:remote.close()
