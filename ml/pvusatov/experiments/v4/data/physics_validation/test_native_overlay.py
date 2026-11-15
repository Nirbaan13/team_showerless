"""Physics guards use toy native arrays/FITS; no archive/final access."""
import importlib.util,tempfile,unittest
from pathlib import Path
import numpy as np
from astropy.io import fits
SPEC=importlib.util.spec_from_file_location('native_overlay',Path(__file__).with_name('native_overlay.py'));m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)
class NativeOverlayGuards(unittest.TestCase):
    def test_positive_native_x_y_axes_are_not_swapped(self):
        epsf=np.zeros((33,33));epsf[26,21]=1.
        image,meta=m.sample_native_epsf(epsf,10.,10.,(25,25),5,5)
        self.assertEqual(np.unravel_index(np.argmax(image),image.shape),(12,11));self.assertAlmostEqual(image.sum(),1.)
    def test_fractional_phase_preserves_unclipped_normalization(self):
        y,x=np.indices((33,33));epsf=np.exp(-((x-16)**2+(y-16)**2)/30.)
        for phase in [0.,.25,.5,.75]:
            image,meta=m.sample_native_epsf(epsf,10+phase,10.75,(25,25),5,5)
            self.assertAlmostEqual(image.sum(),1.,places=12)
        edge,meta=m.sample_native_epsf(epsf,.25,.25,(25,25),5,5)
        self.assertGreater(edge.sum(),0);self.assertLess(edge.sum(),1.)
    def test_derivative_float64_truthful_checksums_preserves_nonimage_arrays(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);source=root/'native.fits';target=root/'derived.fits'
            image=np.arange(100,dtype=np.float32).reshape(10,10);header=fits.Header({'OBSID':'toy1','DETECTOR':1,'BUNIT':'MJy / sr'})
            hdus=fits.HDUList([fits.PrimaryHDU(header=header),fits.ImageHDU(image,header=header,name='IMAGE'),fits.ImageHDU(np.full((10,10),3,dtype=np.uint32),name='FLAGS'),fits.ImageHDU(np.full((10,10),.2,dtype=np.float32),name='ZODI'),fits.ImageHDU(np.ones((10,10),dtype=np.float32),name='VARIANCE')]);hdus.writeto(source,checksum=True)
            result=m.write_derivative(source,target,np.ones((10,10)),2.,allowed_root=root)
            with fits.open(source,memmap=False)as a,fits.open(target,memmap=False)as b:
                self.assertEqual(b['IMAGE'].header['BITPIX'],-64);self.assertEqual(b[0].header['OBSID'],'toy1');self.assertTrue(b[0].header['V4DERIV'])
                np.testing.assert_array_equal(b['IMAGE'].data,image+2.)
                for name in ['FLAGS','ZODI','VARIANCE']:np.testing.assert_array_equal(a[name].data,b[name].data)
                for hdu in b:self.assertEqual(hdu.verify_checksum(),1);self.assertEqual(hdu.verify_datasum(),1)
            self.assertNotEqual(result['original_sha256'],result['derivative_sha256'])
    def test_quarantine_source_is_rejected_before_reader(self):
        with tempfile.TemporaryDirectory()as d:
            root=Path(d);source=root/'quarantine_final'/'missing.fits'
            with self.assertRaisesRegex(ValueError,'quarantine'):m.write_derivative(source,root/'derived.fits',np.ones((2,2)),1.,allowed_root=root)
if __name__=='__main__':unittest.main()
