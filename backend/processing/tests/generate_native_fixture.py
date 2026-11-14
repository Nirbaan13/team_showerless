"""Regenerate the tiny committed FITS fixture with the shared UtilsAI interpreter."""
from pathlib import Path
import numpy as np
from astropy.io import fits


def generate(path):
    image=np.full((8,8),10.,dtype=np.float32)
    image[4,4]=20.
    header=fits.Header({'BUNIT':'MJy / sr','CTYPE1':'RA---TAN',
        'CTYPE2':'DEC--TAN','RADESYS':'ICRS','CRPIX1':4.5,'CRPIX2':4.5,
        'CRVAL1':1.,'CRVAL2':2.,'CDELT1':-1/3600,'CDELT2':1/3600,
        'DETECTOR':1,'MJD-OBS':60000.,'DATE-OBS':'2023-02-25T00:00:00'})
    fits.HDUList([fits.PrimaryHDU(),fits.ImageHDU(image,header,name='IMAGE'),
        fits.ImageHDU(np.zeros((8,8),dtype=np.int32),name='FLAGS'),
        fits.ImageHDU(np.ones((8,8),dtype=np.float32),
            fits.Header({'BUNIT':'MJy2 / sr2'}),name='VARIANCE'),
        fits.ImageHDU(np.full((8,8),2.,dtype=np.float32),
            fits.Header({'BUNIT':'MJy / sr'}),name='ZODI')]).writeto(path,overwrite=True)


if __name__ == '__main__':
    target=Path(__file__).resolve().parents[2]/'src/test/resources/processing/native_fixture.fits'
    target.parent.mkdir(parents=True,exist_ok=True)
    generate(target)
    print(target)
