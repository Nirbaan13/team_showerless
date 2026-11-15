"""Separate DEV Fisher-information support ablation; frozen features unchanged.

Amplitude+constant-background information is sum((p-mean(p))**2) on finite
pixels under independent equal noise. Finite coverage of faint PSF wings does
not have the same information loss as masking its bright core. This remains
an uncalibrated Gaussian/global-MAD proxy, not native detector photometry.
"""
from __future__ import annotations
import time
import numpy as np
from ml.pvusatov.experiments.v4.detection.psf_gate import ProposalContext as OriginalContext


def local_evidence(patch,kernel,noise,minimum_information=.8):
    patch=np.asarray(patch,float);kernel=np.asarray(kernel,float)
    if patch.shape!=kernel.shape or not np.isfinite(kernel).all()or not np.isfinite(noise)or noise<=0:
        raise ValueError('aligned kernel and positive finite noise required')
    valid=np.isfinite(patch);count=int(valid.sum());full=float(np.sum((kernel-kernel.mean())**2))
    if count<6 or full<=0:return 0.,0.
    p=kernel[valid];p=p-p.mean();information=float(p@p);fraction=information/full
    if fraction<minimum_information or not valid[patch.shape[0]//2,patch.shape[1]//2]or information<=1e-15:return 0.,fraction
    values=patch[valid];covariance=float(p@(values-values.mean()))
    return covariance/(noise*np.sqrt(information)),fraction


class ProposalContext(OriginalContext):
    def _evidence(self):
        if self.local_snr is not None:return
        wall=time.perf_counter();cpu=time.process_time();sigma=self.settings['psf_sigma'];radius=int(np.ceil(3*sigma))
        y,x=np.mgrid[-radius:radius+1,-radius:radius+1];kernel=np.exp(-(x*x+y*y)/(2*sigma*sigma));kernel/=kernel.sum()
        values=[];fractions=[]
        for image,peaks in zip(self.residuals,self.peaks):
            finite=image[np.isfinite(image)];noise=1.4826*np.median(abs(finite-np.median(finite)))if len(finite) else 0.
            padded=np.pad(image,radius,constant_values=np.nan);snrs=[];support=[]
            for x,y in peaks[:,:2].astype(int):
                if noise>0 and np.isfinite(noise):s,f=local_evidence(padded[y:y+2*radius+1,x:x+2*radius+1],kernel,noise)
                else:s,f=0.,0.
                snrs.append(s);support.append(f)
            values.append(np.asarray(snrs));fractions.append(support)
        self.local_snr=values;self.information_fractions=fractions
        self.gate_wall=time.perf_counter()-wall;self.gate_cpu=time.process_time()-cpu

    def detect(self,gate_snr=None):
        result=super().detect(gate_snr)
        result['support_policy']='amplitude+constant Fisher information >=.8 of full patch; >=6finitepixels;finitecenter'
        return result
