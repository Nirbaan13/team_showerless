"""Analytic interpolation/covariance/nuisance tests; no observations used."""
import importlib.util,unittest
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates
SPEC=importlib.util.spec_from_file_location('variance_operators',Path(__file__).with_name('operators.py'));m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)
class PropagationMath(unittest.TestCase):
    def test_variance_uses_squared_weights_and_shared_covariance(self):
        good=np.ones((2,2),bool);variance=np.array([[1.,4.],[9.,16.]])
        result=m.bilinear_operator(np.array([[.5,.25]]),np.array([[.5,.5]]),good,variance)
        np.testing.assert_allclose(result['variance_diagonal'],[[1.875,1.71875]],rtol=0,atol=1e-14)
        covariance=m.covariance_for_rows(result['operator'],result['native_variance'],[0,1])
        self.assertAlmostEqual(covariance[0,1],1.5625)
        self.assertNotAlmostEqual(result['linear_interpolated_variance'][0,0],1.875)
    def test_mask_support_and_constant_mode_match_registered_signal(self):
        signal=np.arange(12,dtype=float).reshape(3,4);good=np.ones((3,4),bool);good[1,1]=False;variance=np.ones((3,4))
        x=np.array([[0.,.1,.999,2.2,-.1,3.]]);y=np.array([[0.,.1,.001,1.3,.5,2.]])
        result=m.bilinear_operator(x,y,good,variance)
        support=map_coordinates(good.astype(float),[y,x],order=1,mode='constant',cval=0.)
        projected=map_coordinates(np.where(good,signal,0),[y,x],order=1,mode='constant',cval=0.)
        usable=support>=.995
        expected=np.divide(projected,support,where=usable,out=np.zeros_like(projected))
        np.testing.assert_allclose(result['support'],support,rtol=0,atol=1e-14)
        np.testing.assert_array_equal(result['usable'],usable)
        np.testing.assert_allclose((result['operator']@signal.ravel()).reshape(x.shape),expected,rtol=0,atol=1e-14)
    def test_affine_amplitude_nuisance_eliminates_global_median_constant(self):
        template=np.array([.0,.1,.6,.2,.1]);covariance=np.eye(5)+.2*(np.ones((5,5))-np.eye(5))
        fit=m.affine_amplitude_weights(template,covariance)
        weights=fit['amplitude_weights'];image=2*template+3.4
        self.assertAlmostEqual(weights.sum(),0.,places=12)
        self.assertAlmostEqual(weights@image,2.,places=12)
        self.assertAlmostEqual(weights@(image-np.median(image)),2.,places=12)
        self.assertAlmostEqual(fit['variance_exact'],weights@covariance@weights,places=12)
    def test_invalid_native_variance_is_not_silently_used(self):
        with self.assertRaises(ValueError):m.bilinear_operator(np.array([[.5]]),np.array([[.5]]),np.ones((2,2),bool),np.array([[1.,1.],[1.,-1.]]))
if __name__=='__main__':unittest.main()
