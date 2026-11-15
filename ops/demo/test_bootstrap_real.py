"""Synthetic FITS HTTP fixtures test integrity; these files are never demo data."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.visualization import ZScaleInterval
from PIL import Image

SPEC = importlib.util.spec_from_file_location('bootstrap_real', Path(__file__).with_name('bootstrap_real.py'))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class BootstrapTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        wcs = WCS(naxis=2)
        wcs.wcs.ctype = ['RA---TAN', 'DEC--TAN']
        wcs.wcs.crval = [269.452075, 4.693365]
        wcs.wcs.crpix = [5, 5]
        wcs.wcs.cdelt = [-.001, .001]
        header = wcs.to_header()
        header['DETECTOR'] = 2
        header['DATE-OBS'] = '2025-09-22T01:02:03.456'
        out = io.BytesIO()
        fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(np.ones((10, 10)), header, name='IMAGE')]).writeto(out)
        self.body = out.getvalue()
        body = self.body
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *_): pass
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.manifest = {'schema_version': 1, 'dataset_kind': 'real_archive', 'targets': [{
            'id': 'barnards-star', 'name': "Barnard's Star", 'ra_deg': 269.452075,
            'dec_deg': 4.693365, 'recommended_detector': 2, 'availability': 'available',
            'observations': [{'id': 'test-only-synthetic', 'detector': 2,
                'observation_date': '2025-09-22T01:02:03.456', 'release': 'DR1',
                'source_url': 'https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/dr1/level2/test.fits',
                'download_url': f'http://127.0.0.1:{self.http.server_port}/fixture.fits',
                'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body),
                'path': 'fits/barnards-star/test.fits'}]}]}
        self.lock = self.root / 'lock.json'
        self.output = self.root / 'seed'
    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.temp.cleanup()
    def run_bootstrap(self, **kwargs):
        self.lock.write_text(json.dumps(self.manifest))
        return module.bootstrap(self.lock, self.output, allow_test_http=True, **kwargs)
    def test_download_checks_native_identity_and_offline_verifies(self):
        result = self.run_bootstrap()
        self.assertEqual(result['observations'], 1)
        self.assertEqual((self.output / 'api-data/demo/fits/barnards-star/test.fits').read_bytes(), self.body)
        self.assertTrue((self.output / 'ml-data/demo/manifest.json').exists())
        self.assertTrue((self.output / 'api-data/irsa-mirror.sqlite').exists())
        self.http.shutdown()
        self.assertEqual(self.run_bootstrap(verify_only=True)['observations'], 1)
    def test_tampered_existing_file_is_rejected_offline(self):
        self.run_bootstrap()
        (self.output / 'api-data/demo/fits/barnards-star/test.fits').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum|size'):
            self.run_bootstrap(verify_only=True)
    def test_offline_index_geometry_tampering_is_rejected(self):
        obs = self.manifest['targets'][0]['observations'][0]
        obs['native_index_row'] = {'key': 'dr1/level2/test.fits', 'release': 'dr1',
            'identity': '["fixture-only", "5760", "2026-01-01"]',
            'body': {'observation': {'frame_id': 'test-fixture', 'detector_array': 2,
                    'observation_date': obs['observation_date']}},
            'footprint': [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
            'observed': 1758502923.456, 'detector': 2}
        self.run_bootstrap()
        with sqlite3.connect(self.output / 'api-data/irsa-mirror.sqlite') as db:
            db.execute("UPDATE mirror_objects SET footprint='[]'")
        with self.assertRaisesRegex(ValueError, 'metadata|geometry'):
            self.run_bootstrap(verify_only=True)
    def test_archive_header_cannot_be_relabelled(self):
        self.manifest['targets'][0]['observations'][0]['detector'] = 5
        with self.assertRaisesRegex(ValueError, 'detector'):
            self.run_bootstrap()
    def test_coordinate_outside_actual_image_is_rejected(self):
        self.manifest['targets'][0]['ra_deg'] = 10
        with self.assertRaisesRegex(ValueError, 'coverage|footprint'):
            self.run_bootstrap()
    def test_archive_outage_is_not_reported_as_no_coverage(self):
        t = self.manifest['targets'][0]
        t.update(availability='discovery_unavailable', observations=[], reason='IRSA HTTP 502')
        result = self.run_bootstrap()
        self.assertEqual(result['observations'], 0)
        stored = json.loads((self.output / 'api-data/demo/manifest.json').read_text())
        self.assertEqual(stored['targets'][0]['availability'], 'discovery_unavailable')
    def test_finite_wrong_sip_inverse_is_rejected_by_forward_roundtrip(self):
        # Astropy can return an in-bounds best iterate after a divergent inverse.
        fake = MagicMock()
        fake.celestial.all_world2pix.return_value = np.array([[4., 4.]])
        fake.celestial.all_pix2world.return_value = np.array([[152., 42.]])
        with patch.object(module, 'WCS', return_value=fake):
            with self.assertRaisesRegex(ValueError, 'roundtrip'):
                self.run_bootstrap()
    def install_clipped_pattern_fixture(self):
        # A synthetic 9x5 HTTP-test fixture, never a production archive asset.
        data = np.arange(45, dtype=float).reshape(5, 9)
        data[0, 0] = np.nan
        data[0, 1] = np.inf
        with fits.open(io.BytesIO(self.body)) as hdus:
            header = hdus['IMAGE'].header.copy()
        header['CRPIX2'] = 3
        buffer = io.BytesIO()
        fits.HDUList([fits.PrimaryHDU(), fits.ImageHDU(data, header, name='IMAGE'),
                      fits.ImageHDU(np.zeros((5, 9), dtype=np.int32), name='FLAGS')]).writeto(buffer)
        body = buffer.getvalue()
        obs = self.manifest['targets'][0]['observations'][0]
        obs.update(sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
        path = self.output / 'api-data/demo' / obs['path']
        path.parent.mkdir(parents=True)
        path.write_bytes(body)
        return data
    def test_preview_preserves_clipped_native_grid_and_actual_pixel_pattern(self):
        data = self.install_clipped_pattern_fixture()
        self.run_bootstrap()
        manifest = json.loads((self.output / 'api-data/demo/preview-manifest.json').read_text())
        preview = manifest['targets'][0]['observations'][0]
        self.assertEqual(preview['source_sha256'], self.manifest['targets'][0]['observations'][0]['sha256'])
        self.assertEqual((preview['image_width'], preview['image_height']), (9, 5))
        self.assertFalse(manifest['discovery_complete'])
        self.assertTrue(preview['field_only'])
        path = self.output / 'api-data' / preview['preview_url'].lstrip('/')
        with Image.open(path) as image:
            pixels = np.array(image)
            self.assertEqual(image.size, (9, 5))
        self.assertEqual(pixels[0, 0, 3], 0)
        self.assertEqual(pixels[0, 1, 3], 0)
        self.assertTrue(np.all(pixels[1:, :, 3] == 255))
        finite = np.isfinite(data)
        lo, hi = ZScaleInterval().get_limits(data[finite])
        expected = np.rint(np.clip((data[finite] - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)
        np.testing.assert_array_equal(pixels[:, :, 0][finite], expected)
        np.testing.assert_array_equal(pixels[:, :, 0], pixels[:, :, 1])
        self.assertGreater(len(np.unique(pixels[:, :, 0])), 10)
        self.assertEqual(self.run_bootstrap(verify_only=True)['observations'], 1)
    def test_preview_manifest_cannot_relabel_the_source(self):
        self.run_bootstrap()
        path = self.output / 'api-data/demo/preview-manifest.json'
        manifest = json.loads(path.read_text())
        manifest['targets'][0]['observations'][0]['source_sha256'] = '0' * 64
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'preview.*metadata|source'):
            self.run_bootstrap(verify_only=True)
    def test_preview_modified_pixels_rejected_even_with_updated_png_hash(self):
        self.install_clipped_pattern_fixture()
        self.run_bootstrap()
        manifest_path = self.output / 'api-data/demo/preview-manifest.json'
        manifest = json.loads(manifest_path.read_text())
        preview = manifest['targets'][0]['observations'][0]
        path = self.output / 'api-data' / preview['preview_url'].lstrip('/')
        with Image.open(path) as image:
            pixels = np.array(image)
        pixels[2, 3, :3] = 255 - pixels[2, 3, :3]
        Image.fromarray(pixels).save(path)
        preview['preview_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'preview.*pixels'):
            self.run_bootstrap(verify_only=True)
    def test_manifest_rejects_path_escape(self):
        self.manifest['targets'][0]['observations'][0]['path'] = '../escape.fits'
        with self.assertRaisesRegex(ValueError, 'path'):
            self.run_bootstrap()

if __name__ == '__main__': unittest.main()
