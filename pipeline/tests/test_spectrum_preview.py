"""Diagnostic spectrum integration uses measured FITS pixels, never fake bands."""
import json
import numpy as np
from astropy.io import fits
import pytest

from test_worker import invoke
from test_spectra_characterization import spectral_fixture


def batch(source, output, **extra):
    return dict(operation='spectrum_preview', output_path=str(output),
                observations=[dict(frame_id='frame-1', image_path=str(source))],
                ra_deg=120., dec_deg=-20., radius_pix=1.1,
                subtraction='zodi_subtracted', **extra)


def test_preview_spectrum_measures_one_real_point_without_exposing_local_paths(tmp_path):
    source=spectral_fixture(tmp_path)
    output=tmp_path/'result.json'
    proc,result=invoke(batch(source,output))
    assert proc.returncode == 0, result
    data=json.loads(output.read_text())
    assert data['quality']=='experimental_visualization_photometry'
    assert data['scientifically_calibrated'] is False
    assert data['total_channels']==1
    assert data['molecular_detections']==[]
    point=data['spectrum'][0]
    assert point['frame_id']=='frame-1'
    assert point['flux_mjy']==pytest.approx(2.232920901214299, rel=1e-10)
    assert point['wavelength_um']==.9
    assert point['bandwidth_um']==.02
    assert str(tmp_path) not in output.read_text()
    assert 'wcs_wave_visualization_only' in data['warnings']


def test_raw_and_zodi_spectrum_modes_measure_different_input_pixels(tmp_path):
    source=spectral_fixture(tmp_path)
    request=batch(source,tmp_path/'zodi.json')
    proc,result=invoke(request)
    assert proc.returncode==0, result
    request.update(output_path=str(tmp_path/'raw.json'),subtraction='raw_calibrated')
    proc,result=invoke(request)
    assert proc.returncode==0, result
    raw=json.loads((tmp_path/'raw.json').read_text())
    # The five raw pixels sum to 110 MJy/sr (ZODI contributes 15).
    assert raw['spectrum'][0]['flux_mjy']==pytest.approx(2.585487359300767,rel=1e-10)
    assert raw['subtraction_mode']=='raw_calibrated'


def test_preview_spectrum_reports_missing_wavelength_data_without_inventing_channels(tmp_path):
    source=spectral_fixture(tmp_path)
    with fits.open(source,mode='update') as hdus:
        del hdus['WCS-WAVE']
    proc,result=invoke(batch(source,tmp_path/'result.json'))
    assert proc.returncode!=0
    assert result['error']['code']=='no_measurements'
    assert not (tmp_path/'result.json').exists()


@pytest.mark.parametrize('change', ['edge','masked','zero_variance','processed'])
def test_preview_spectrum_rejects_unusable_measurements(tmp_path,change):
    source=spectral_fixture(tmp_path)
    request=batch(source,tmp_path/'result.json')
    with fits.open(source,mode='update') as hdus:
        if change=='edge': request['radius_pix']=3
        if change=='masked': hdus['FLAGS'].data[2,2]=1<<26
        if change=='zero_variance': hdus['VARIANCE'].data[:]=0
        if change=='processed': hdus['IMAGE'].header['ZODISUB']=True
    proc,result=invoke(request)
    assert proc.returncode!=0
    assert result['error']['code']=='no_measurements'
    assert not (tmp_path/'result.json').exists()


def test_preview_spectrum_preserves_partial_results_and_counts_failures(tmp_path):
    source=spectral_fixture(tmp_path)
    request=batch(source,tmp_path/'result.json')
    request['observations'].append(dict(frame_id='missing',image_path=str(tmp_path/'missing.fits')))
    proc,result=invoke(request)
    assert proc.returncode==0, result
    data=json.loads((tmp_path/'result.json').read_text())
    assert data['total_channels']==1
    assert data['n_failed']==1
    assert data['failures'][0]['frame_id']=='missing'
    assert str(tmp_path) not in json.dumps(data)


@pytest.mark.parametrize('variance',[float('nan'),-1.])
def test_bad_variance_outside_aperture_does_not_discard_a_valid_measurement(tmp_path,variance):
    source=spectral_fixture(tmp_path)
    with fits.open(source,mode='update') as hdus:
        hdus['VARIANCE'].data[4,4]=variance
    proc,result=invoke(batch(source,tmp_path/'result.json'))
    assert proc.returncode==0,result
    data=json.loads((tmp_path/'result.json').read_text())
    assert data['spectrum'][0]['flux_mjy']==pytest.approx(2.232920901214299,rel=1e-10)
