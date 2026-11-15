"""Experimental local PSF+background evidence gate BEFORE legacy peak linking.

The original Gaussian-filter peaks/values are retained. A gate is a physical
template-SNR proxy, never an output-count cutoff or a truth-conditioned search.
"""
from __future__ import annotations
import time
import numpy as np
from ml_inference.detector import difference_frames, _detect_peaks, link_detections, DetectionLimitError
from ml.pvusatov.experiments.v4.detection.features import _maps

SETTINGS=dict(min_snr=4.,max_peaks=100,psf_sigma=.8,min_speed=.5,max_speed=60.,
              match_radius=1.4,min_epochs=3,min_support=.8,leave_one_out=True)


class ProposalContext:
    def __init__(self,images,times,settings=None):
        self.settings={**SETTINGS,**(settings or {})};s=self.settings
        images=np.asarray(images,float);times=np.asarray(times,float)
        if(images.ndim!=3 or not s['min_epochs']<=len(images)<=32 or min(images.shape[1:])<1
           or max(images.shape[1:])>512 or times.shape!=(len(images),)or not np.isfinite(times).all()
           or np.any(np.diff(times)<=0)or np.isinf(images).any()):raise ValueError('bounded images and increasing physical times required')
        self.times=times-times[0];wall=time.perf_counter();cpu=time.process_time()
        self.residuals=difference_frames(images,s['leave_one_out'])
        self.peaks=[_detect_peaks(d,np.isfinite(d),s['psf_sigma'],s['min_snr'],s['max_peaks'],s['min_support'])for d in self.residuals]
        self.prepare_wall=time.perf_counter()-wall;self.prepare_cpu=time.process_time()-cpu
        self.local_snr=None;self.gate_wall=0.;self.gate_cpu=0.

    def _evidence(self):
        if self.local_snr is not None:return
        wall=time.perf_counter();cpu=time.process_time();sigma=self.settings['psf_sigma'];radius=int(np.ceil(3*sigma))
        y,x=np.mgrid[-radius:radius+1,-radius:radius+1];kernel=np.exp(-(x*x+y*y)/(2*sigma*sigma));kernel/=kernel.sum()
        values=[]
        for image,peaks in zip(self.residuals,self.peaks):
            fit=_maps(image[None],kernel);xy=peaks[:,:2].astype(int)
            values.append(fit['snr'][0,xy[:,1],xy[:,0]]if len(xy)else np.empty(0))
        self.local_snr=values;self.gate_wall=time.perf_counter()-wall;self.gate_cpu=time.process_time()-cpu

    def detect(self,gate_snr=None):
        if gate_snr is not None and(not np.isfinite(gate_snr)or gate_snr<=0):raise ValueError('gate SNR must be positive or None')
        s=self.settings
        if gate_snr is not None:
            self._evidence();peaks=[p[snr>=gate_snr]for p,snr in zip(self.peaks,self.local_snr)]
        else:peaks=self.peaks
        wall=time.perf_counter();cpu=time.process_time();error=None
        try:tracks=link_detections(peaks,self.times,s['min_speed'],s['max_speed'],s['match_radius'],s['min_epochs'])
        except DetectionLimitError as exc:tracks=[];error=dict(phase='linking',type=type(exc).__name__,message=str(exc))
        link_wall=time.perf_counter()-wall;link_cpu=time.process_time()-cpu
        gate_wall=self.gate_wall if gate_snr is not None else 0.;gate_cpu=self.gate_cpu if gate_snr is not None else 0.
        before=[len(p)for p in self.peaks];after=[len(p)for p in peaks];capped=any(v>=s['max_peaks']for v in before)
        return dict(tracks=tracks,error=error,gate_snr=gate_snr,peaks_before=before,peaks_after=after,
            peak_cap_reached=capped,search_complete=not capped and error is None,
            prepare_wall_seconds=self.prepare_wall,prepare_cpu_seconds=self.prepare_cpu,
            gate_wall_seconds=gate_wall,gate_cpu_seconds=gate_cpu,link_wall_seconds=link_wall,link_cpu_seconds=link_cpu,
            total_wall_seconds=self.prepare_wall+gate_wall+link_wall,total_cpu_seconds=self.prepare_cpu+gate_cpu+link_cpu,
            limitation='local Gaussian/MAD SNR is an approximate finite-support point-template statistic')


def detect(images,times,*,gate_snr=None,settings=None):
    return ProposalContext(images,times,settings).detect(gate_snr)
