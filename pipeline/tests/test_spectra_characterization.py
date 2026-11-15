"""Runtime evidence for the team function; not authorization for a science API.

WCS-WAVE is visualization calibration only. The worker deliberately gates spectra.
"""
from pathlib import Path
import sys

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.spectra import extract_spectrum, measure_cutout_point
from test_worker import fixture_fits


def spectral_fixture(tmp_path):
    p=fixture_fits(tmp_path)
    with fits.open(p,mode='update') as h:
        header=h['IMAGE'].header
        for key,value in {'WCSAXESW':2,'CRPIX1W':1,'CRPIX2W':1,
            'CDELT1W':1,'CDELT2W':1,'CUNIT1W':'um','CUNIT2W':'um',
            'CTYPE1W':'WAVE-TAB','CTYPE2W':'WAVE-TAB','CRVAL1W':1,
            'CRVAL2W':1,'PV1_3W':1,'PV2_3W':2,'PS1_0W':'WCS-WAVE',
            'PS2_0W':'WCS-WAVE','PS1_1W':'VALUES','PS2_1W':'VALUES',
            'PS1_2W':'X','PS2_2W':'Y'}.items():
            header[key]=value
        values=np.empty((1,2,2,2),dtype=np.float64)
        values[:,:,:,0]=.9
        values[:,:,:,1]=.02
        h.append(fits.BinTableHDU.from_columns([
            fits.Column(name='X',format='2J',dim='(2)',array=[[0,6]]),
            fits.Column(name='Y',format='2J',dim='(2)',array=[[0,6]]),
            fits.Column(name='VALUES',format='8D',dim='(2,2,2)',array=values)
        ],name='WCS-WAVE'))
    return p


def test_team_spectrum_real_fits_conversion_and_wavelength(tmp_path):
    p=spectral_fixture(tmp_path)
    # Radius 1.1 includes exactly 5 pixels. Their clean surface brightness
    # sums to 95 MJy/sr; one arcsec-square pixel is 2.3504430539097885e-11 sr.
    point=measure_cutout_point(p,120.,-20.,radius_pix=1.1)
    assert point['flux_mjy'] == pytest.approx(2.232920901214299,rel=1e-10)
    assert point['uncertainty_mjy'] == pytest.approx(.10511500891568655,rel=1e-10)
    assert point['wavelength_um'] == .9
    assert point['bandwidth_um'] == .02
    assert point['mjd'] == 60000.25
    table=extract_spectrum([p],120.,-20.,radius_pix=1.1)
    assert len(table) == 1  # One observed image produces one point, never 102 invented bands.
    assert table[0]['flux_mjy'] == point['flux_mjy']


def test_team_spectrum_skips_offimage_and_flagged_apertures(tmp_path):
    p=spectral_fixture(tmp_path)
    assert measure_cutout_point(p,121.,-20.) is None
    with fits.open(p,mode='update') as h:
        h['FLAGS'].data[2,2]=64
    assert measure_cutout_point(p,120.,-20.) is None


def test_team_spectrum_masks_negative_variance_before_measurement(tmp_path):
    p=spectral_fixture(tmp_path)
    with fits.open(p,mode='update') as h:
        h['VARIANCE'].data[:]=-1
    assert measure_cutout_point(p,120.,-20.,radius_pix=1.1) is None
