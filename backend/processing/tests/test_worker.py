"""Worker contract tests: every fixture is a real on-disk FITS file."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image
import pytest

WORKER = Path(__file__).resolve().parents[1] / 'worker.py'


def fixture_fits(tmp_path, **changes):
    image = np.arange(25, dtype=np.float32).reshape(5, 5) + 10
    flags = np.zeros((5, 5), dtype=np.int32)
    flags[0, 0] = 1
    flags[0, 1] = 8  # not in the team's bad-bit mask
    header = fits.Header({'BUNIT': 'MJy / sr', 'CTYPE1': 'RA---TAN',
        'CTYPE2': 'DEC--TAN', 'CRPIX1': 3., 'CRPIX2': 3., 'CRVAL1': 120.,
        'CRVAL2': -20., 'CDELT1': -1/3600, 'CDELT2': 1/3600,
        'MJD-AVG': 60000.25, 'DATE-AVG': '2023-02-25T06:00:00', 'DETECTOR': 1})
    hdus = [fits.PrimaryHDU(), fits.ImageHDU(image, header, name='IMAGE'),
        fits.ImageHDU(flags, name='FLAGS'),
        fits.ImageHDU(np.full((5,5), 4., dtype=np.float32),
            fits.Header({'BUNIT': 'MJy2 / sr2'}), name='VARIANCE'),
        fits.ImageHDU(np.full((5,5), 3., dtype=np.float32),
            fits.Header({'BUNIT': 'MJy / sr'}), name='ZODI'),
        fits.ImageHDU(np.array([[42]], dtype=np.int16), name='EXTRA')]
    h = fits.HDUList(hdus)
    for key, val in changes.items():
        if key == 'drop':
            del h[val]
        elif key == 'unit':
            h['ZODI'].header['BUNIT'] = val
        elif key == 'processed':
            h['IMAGE'].header['ZODISUB'] = val
        else:
            h[key].data = val
    p = tmp_path / 'input.fits'
    h.writeto(p)
    return p


def invoke(request):
    proc = subprocess.run([sys.executable, str(WORKER)], input=json.dumps(request),
        capture_output=True, text=True, timeout=30)
    assert proc.stdout.count('\n') == 1, proc
    return proc, json.loads(proc.stdout)


def request(operation, source, output=None, **kw):
    return dict(operation=operation, image_path=str(source),
        **({'output_path': str(output)} if output else {}), **kw)


def test_preview_uses_raw_values_and_masks_only_bad_bits(tmp_path):
    p = fixture_fits(tmp_path)
    out = tmp_path / 'preview.png'
    proc, result = invoke(request('preview', p, out))
    assert proc.returncode == 0, result
    assert result['status'] == 'ok'
    assert result['subtraction'] == 'raw_calibrated'
    assert result['data_min'] == 11.0
    assert result['data_max'] == 34.0
    assert result['masked_pixels'] == 1
    assert out.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
    with Image.open(out) as image:
        pixels = np.array(image.convert('RGBA'))
        assert image.size == (5, 5)
        assert pixels[0, 0, 3] == 0
        assert pixels[0, 1, 3] == 255
        assert pixels[4, 4, 0] == 255


def test_zodi_preserves_hdus_wcs_flags_and_prevents_double_subtraction(tmp_path):
    p = fixture_fits(tmp_path)
    out = tmp_path / 'clean.fits'
    proc, result = invoke(request('zodi', p, out))
    assert proc.returncode == 0, result
    assert result['subtraction'] == 'zodi_subtracted'
    with fits.open(out) as h, fits.open(p) as original:
        assert [x.name for x in h] == [x.name for x in original]
        assert np.isnan(h['IMAGE'].data[0,0])
        assert h['IMAGE'].data[2,2] == 19.
        assert h['IMAGE'].header['ZODISUB'] is True
        assert h['IMAGE'].header['CRVAL1'] == 120.
        assert h['IMAGE'].header['MJD-AVG'] == 60000.25
        assert 'HISTORY' in h['IMAGE'].header
        for name in ['FLAGS', 'VARIANCE', 'ZODI', 'EXTRA']:
            np.testing.assert_array_equal(h[name].data, original[name].data)
    proc, result = invoke(request('zodi', out, tmp_path/'twice.fits'))
    assert proc.returncode != 0
    assert result['error']['code'] == 'already_processed'
    proc, result = invoke(request('preview', out, tmp_path/'clean.png'))
    assert proc.returncode == 0, result
    assert result['data_min'] == 8.
    assert result['data_max'] == 31.
    assert result['subtraction'] == 'zodi_subtracted'


@pytest.mark.parametrize('changes,code', [
    ({'drop': 'ZODI'}, 'missing_hdu'),
    ({'ZODI': np.ones((2,2))}, 'invalid_shape'),
    ({'FLAGS': np.zeros((5,5),dtype=float)}, 'invalid_flags'),
    ({'unit': 'Jy / sr'}, 'unsupported_unit'),
    ({'ZODI': np.full((5,5),np.nan)}, 'nonfinite_data'),
    ({'processed': True}, 'already_processed'),
])
def test_zodi_rejects_invalid_science_input_without_output(tmp_path, changes, code):
    p = fixture_fits(tmp_path, **changes)
    out = tmp_path / 'output.fits'
    proc, result = invoke(request('zodi', p, out))
    assert proc.returncode != 0
    assert result['error']['code'] == code
    assert not out.exists()


def test_missing_file_never_creates_fallback(tmp_path):
    out = tmp_path / 'missing.png'
    proc, result = invoke(request('preview', tmp_path/'missing.fits', out))
    assert proc.returncode != 0
    assert result['error']['code'] == 'invalid_input'
    assert not out.exists()


@pytest.mark.parametrize('extra', [dict(ra_deg=float('nan'),dec_deg=0),
    dict(ra_deg=120,dec_deg=91), dict(ra_deg=120,dec_deg=-20,radius_pix=-1)])
def test_spectrum_rejects_invalid_coordinates(tmp_path, extra):
    proc, result = invoke(request('spectrum', fixture_fits(tmp_path), **extra))
    assert proc.returncode != 0
    assert result['error']['code'] == 'invalid_request'


def test_spectrum_requires_scientific_pixel_calibration(tmp_path):
    proc, result = invoke(request('spectrum', fixture_fits(tmp_path), ra_deg=120,dec_deg=-20))
    assert proc.returncode != 0
    assert result['status'] == 'error'
    assert result['error']['code'] == 'not_ready'
    assert result['error']['reason'] == 'missing_pixel_spectral_calibration'
    assert 'spectrum' not in result


def test_worker_import_does_not_import_service_or_alignment():
    # Importing the worker must remain usable with no FastAPI/reprojection installed.
    code = f'''import runpy,sys
runpy.run_path({str(WORKER)!r}, run_name="worker_import_test")
assert not any(n == 'service' or n.endswith('.service') or 'align_files' in n or n.endswith('.query') for n in sys.modules)
'''
    proc = subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize('payload', ['[]','{"operation":"align"}', '{} {}', 'x'*17000])
def test_cli_rejects_malformed_or_oversize_input(payload):
    proc = subprocess.run([sys.executable,str(WORKER)],input=payload,capture_output=True,text=True)
    assert proc.returncode != 0
    assert json.loads(proc.stdout)['error']['code'] == 'invalid_request'


def test_output_must_not_overwrite_source_or_existing_file(tmp_path):
    p=fixture_fits(tmp_path)
    before=p.read_bytes()
    proc, result=invoke(request('zodi',p,p))
    assert proc.returncode != 0
    assert result['error']['code'] == 'invalid_output'
    assert p.read_bytes() == before


def test_all_invalid_preview_is_an_error(tmp_path):
    p=fixture_fits(tmp_path,IMAGE=np.full((5,5),np.nan))
    proc,result=invoke(request('preview',p,tmp_path/'out.png'))
    assert proc.returncode != 0
    assert result['error']['code'] == 'no_valid_pixels'


def test_capabilities_needs_no_fits_and_reports_science_gate():
    proc, result=invoke({'operation':'capabilities'})
    assert proc.returncode == 0, result
    assert result['operations'] == ['preview','zodi']
    assert result['spectrum'] == {'status':'not_ready','code':'missing_pixel_spectral_calibration'}


@pytest.mark.parametrize('variance', [np.full((5,5),-1.),np.full((5,5),np.nan)])
def test_spectrum_rejects_invalid_variance_before_measurement(tmp_path,variance):
    p=fixture_fits(tmp_path,VARIANCE=variance)
    proc,result=invoke(request('spectrum',p,ra_deg=120,dec_deg=-20))
    assert proc.returncode != 0
    assert result['error']['code'] == 'invalid_variance'


def test_spectrum_never_enables_just_because_calibration_hdus_exist(tmp_path):
    p=fixture_fits(tmp_path)
    with fits.open(p,mode='update') as h:
        for name,value in [('CWAVE',.9),('CBAND',.02)]:
            h.append(fits.ImageHDU(np.full((5,5),value),name=name))
    proc,result=invoke(request('spectrum',p,ra_deg=120,dec_deg=-20))
    assert proc.returncode != 0
    assert result['error']['code'] == 'not_ready'
    assert result['error']['reason'] == 'unverified_spectral_photometry'


def test_corrupt_fits_never_creates_preview(tmp_path):
    p=tmp_path/'broken.fits'
    p.write_bytes(b'this is not FITS')
    out=tmp_path/'preview.png'
    proc,result=invoke(request('preview',p,out))
    assert proc.returncode != 0
    assert result['error']['code'] == 'invalid_fits'
    assert not out.exists()


def test_sparse_oversize_file_is_rejected_before_fits_read(tmp_path):
    p=tmp_path/'oversize.fits'
    with p.open('wb') as f:
        f.truncate(256*1024*1024+1)
    proc,result=invoke(request('preview',p,tmp_path/'preview.png'))
    assert proc.returncode != 0
    assert result['error']['code'] == 'invalid_input'


def test_preview_masks_nonfinite_pixels_without_fake_replacement(tmp_path):
    image=np.full((5,5),12.)
    image[1,1]=np.nan
    image[1,2]=np.inf
    p=fixture_fits(tmp_path,IMAGE=image)
    proc,result=invoke(request('preview',p,tmp_path/'preview.png'))
    assert proc.returncode == 0, result
    assert result['masked_pixels'] == 3
    with Image.open(tmp_path/'preview.png') as png:
        a=np.array(png.convert('RGBA'))
        assert a[1,1,3] == a[1,2,3] == 0
        assert a[2,2,3] == 255


def test_existing_output_bytes_are_untouched(tmp_path):
    p=fixture_fits(tmp_path)
    out=tmp_path/'preview.png'
    out.write_bytes(b'keep this content')
    proc,result=invoke(request('preview',p,out))
    assert proc.returncode != 0
    assert result['error']['code'] == 'invalid_output'
    assert out.read_bytes() == b'keep this content'
