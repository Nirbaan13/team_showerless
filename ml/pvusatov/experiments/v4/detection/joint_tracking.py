"""Separately typed, bounded track-before-detect DEVELOPMENT hypotheses.

No independent epoch peaks, learned probabilities, flux estimates, or six-feature
rows are manufactured. Statistics remain conditional, uncalibrated search proxies.
"""
from __future__ import annotations
import ctypes
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import numpy as np
from ml_inference.detector import filtered_evidence,DetectionLimitError

_LIBRARIES={}
DEFAULTS=dict(min_speed=.5,max_speed=60.,step_px=1.,max_endpoint_component_px=64.,psf_sigma=.8)


@dataclass(frozen=True)
class JointHypothesis:
    epochs:tuple
    positions_xy:tuple
    velocity_xy_px_hour:tuple
    search_statistic:float
    per_epoch_proxy:tuple
    statistic_kind:str
    kind:str='joint_template_hypothesis'
    positions_measured:bool=False
    learned_score:None=None


def library(scratch=None):
    source=Path(__file__).with_suffix('.cpp');digest=hashlib.sha256(source.read_bytes()).hexdigest()
    scratch=Path(scratch or'/tmp/spaceapps-v4-detection');key=(str(scratch),digest)
    if key not in _LIBRARIES:
        scratch.mkdir(parents=True,exist_ok=True);target=scratch/f'joint-{digest[:20]}.so'
        if not target.exists():
            handle=tempfile.NamedTemporaryFile(dir=scratch,suffix='.so',delete=False);temporary=Path(handle.name);handle.close()
            try:
                subprocess.run(['g++','-std=c++17','-O3','-shared','-fPIC',str(source),'-o',str(temporary)],check=True,capture_output=True)
                os.replace(temporary,target)
            finally:temporary.unlink(missing_ok=True)
        lib=ctypes.CDLL(str(target));ptr=np.ctypeslib.ndpointer;i=ctypes.c_int;d=ctypes.c_double;counter=ctypes.POINTER(ctypes.c_int64)
        common=[ptr(np.float64,flags='C_CONTIGUOUS'),i,i,i,i,d,d,d,i,d]
        lib.plan.restype=ctypes.c_int64;lib.plan.argtypes=common+[counter,counter]
        lib.search.restype=i;lib.search.argtypes=[ptr(np.float32,flags='C_CONTIGUOUS')]+common+[d,ctypes.c_int64,i,
            ptr(np.float32,flags='C_CONTIGUOUS'),ptr(np.int16,flags='C_CONTIGUOUS'),ptr(np.int16,flags='C_CONTIGUOUS'),counter,counter,counter]
        _LIBRARIES[key]=lib
    return _LIBRARIES[key]


def round_offsets(values):
    values=np.asarray(values,float)
    return np.copysign(np.floor(abs(values)+.5),values).astype(int)


def automatic_groups(times):
    times=np.asarray(times,float)
    if times.ndim!=1 or not 3<=len(times)<=32 or not np.isfinite(times).all()or np.any(np.diff(times)<=0):raise ValueError('3..32 increasing physical times required')
    groups=[tuple(range(len(times)))];start=0
    for end in [*np.flatnonzero(np.diff(times)>1.5)+1,len(times)]:
        group=tuple(range(start,int(end)))
        if len(group)>=3 and group not in groups:groups.append(group)
        start=int(end)
    return groups


def _parameters(times,shape,reference_epoch_count,settings):
    times=np.ascontiguousarray(times,dtype=np.float64);s={**DEFAULTS,**settings}
    if times.ndim!=1 or not 3<=len(times)<=32 or not np.isfinite(times).all()or np.any(np.diff(times)<=0):raise ValueError('3..32 increasing physical times required')
    if len(shape)!=2 or any(type(v)not in (int,np.int64,np.int32)or not 1<=v<=512 for v in shape):raise ValueError('bounded2D grid required')
    n=len(times);reference=n if reference_epoch_count is None else reference_epoch_count
    if type(reference)is not int or not n<=reference<=32:raise ValueError('reference count must include every selected epoch')
    if not all(np.isfinite(v)and v>0 for v in s.values())or s['min_speed']>s['max_speed']:raise ValueError('finite positive search settings required')
    span=times[-1]-times[0];displacement=int(np.floor(min(s['max_endpoint_component_px'],s['max_speed']*span)/s['step_px']))
    if (2*displacement+1)**2>65536:raise ValueError('bounded velocity grid exceeds65536 hypotheses')
    args=(times,n,reference,int(shape[0]),int(shape[1]),s['min_speed'],s['max_speed'],s['step_px'],displacement,s['psf_sigma'])
    return args,s


def plan_search(times,shape,*,reference_epoch_count=None,**settings):
    args,s=_parameters(times,shape,reference_epoch_count,settings);anchors=ctypes.c_int64();velocities=ctypes.c_int64()
    work=int(library().plan(*args,ctypes.byref(anchors),ctypes.byref(velocities)))
    return dict(planned_pixel_epoch_tests=work,anchor_velocity_tests=anchors.value,velocity_hypotheses=velocities.value,
                reference_epoch_count=args[2],selected_epochs=args[1],settings=s,minimum_template_span_px=1.5)


def search_maps(maps,times,*,reference_epoch_count=None,real_epochs=None,threshold=6.,max_candidates=100,
                max_work=600000000,statistic='nuisance_sum',**settings):
    maps=np.asarray(maps,dtype=np.float32)
    if maps.ndim!=3:raise ValueError('epoch,y,x maps required')
    args,s=_parameters(times,maps.shape[1:],reference_epoch_count,settings)
    if maps.shape[0]!=args[1]:raise ValueError('map/time count differs')
    if type(max_work)is not int or max_work<1 or type(max_candidates)is not int or not 1<=max_candidates<=100:raise ValueError('bounded integer work/proposal caps required')
    if not np.isfinite(threshold)or threshold<=0 or statistic not in ('nuisance_sum','robust_positive'):raise ValueError('unsupported search statistic/threshold')
    plan=plan_search(times,maps.shape[1:],reference_epoch_count=reference_epoch_count,**settings)
    if plan['planned_pixel_epoch_tests']>max_work:raise DetectionLimitError('preflight joint work cap exceeded; no pixel search or partial results')
    # Work preflight intentionally precedes any pixel-value validation/search.
    if np.isinf(maps).any():raise ValueError('infinite filtered proxy values unsupported')
    n,h,w=maps.shape;epochs=tuple(range(n))if real_epochs is None else tuple(real_epochs)
    if len(epochs)!=n or any(type(e)is not int or not 0<=e<32 for e in epochs)or list(epochs)!=sorted(set(epochs)):raise ValueError('actual selected epoch identities invalid')
    maps=np.ascontiguousarray(maps);best=np.empty((h,w),np.float32);dx=np.zeros((h,w),np.int16);dy=dx.copy()
    work=ctypes.c_int64();valid=ctypes.c_int64();qualified=ctypes.c_int64()
    code=library().search(maps,*args,threshold,max_work,int(statistic=='robust_positive'),best,dx,dy,
        ctypes.byref(work),ctypes.byref(valid),ctypes.byref(qualified))
    if code or work.value!=plan['planned_pixel_epoch_tests']:raise DetectionLimitError('joint work counter failed; partial results withheld')
    finite=np.isfinite(best);maximum=float(np.max(best[finite]))if finite.any()else None
    indices=np.flatnonzero(finite&(best>=threshold));order=indices[np.argsort(-best.ravel()[indices],kind='stable')]
    result=[];paths=[];capped=False;next_unpublished=None;t=np.asarray(times)-times[0];span=t[-1]
    for index in order:
        y,x=divmod(int(index),w);velocity=np.asarray([dx[y,x],dy[y,x]])*s['step_px']/span
        positions=np.asarray([x,y])+round_offsets(t[:,None]*velocity)
        if any(np.median(np.linalg.norm(positions-p,axis=1))<2. for p in paths):continue
        if len(result)>=max_candidates:capped=True;next_unpublished=float(best[y,x]);break
        sample=maps[np.arange(n),positions[:,1],positions[:,0]]
        result.append(JointHypothesis(epochs,tuple(map(tuple,positions.tolist())),tuple(velocity.tolist()),
            float(best[y,x]),tuple(map(float,sample)),statistic));paths.append(positions)
    return result,dict(plan,threshold=threshold,statistic=statistic,work_counter=work.value,
        valid_hypothesis_tests=valid.value,qualified_hypothesis_tests=qualified.value,
        maximum_search_statistic=maximum,anchor_positions_with_valid_hypothesis=int(finite.sum()),
        fitted_anchor_positions_above_threshold=len(indices),candidate_cap_reached=capped,
        first_unpublished_statistic=next_unpublished,
        hypothesis_search_complete=True,proposal_publication_complete=not capped,
        nms='median fitted path distance<2px; proposal suppression, not proven source identity',
        positions_are_fitted=True,learned_score=None,
        cpp_source_sha256=hashlib.sha256(Path(__file__).with_suffix('.cpp').read_bytes()).hexdigest(),
        warnings=['uncalibrated_search_statistic','look_elsewhere_multiple_hypotheses',
                  'fitted_positions_not_epoch_peaks','equal_noise_Gaussian_response_approximation',
                  'spatial_temporal_noise_correlations_not_calibrated','all_selected_epoch_support_required'])


def nuisance_maps(images,*,psf_sigma=.8,min_support=.8):
    images=np.asarray(images,float)
    if images.ndim!=3 or not 3<=len(images)<=32 or min(images.shape[1:])<1 or max(images.shape[1:])>512 or np.isinf(images).any():raise ValueError('bounded finite-or-masked images required')
    n=len(images);valid=np.isfinite(images);count=valid.sum(axis=0)
    mean=np.divide(np.where(valid,images,0.).sum(axis=0),count,out=np.zeros(images.shape[1:]),where=count>0)
    maps=[];scales=[]
    for image,mask in zip(images,valid):
        residual=np.where(mask&(count>=3),image-mean,np.nan)
        filtered,_,support,sigma=filtered_evidence(residual,np.isfinite(residual),psf_sigma,min_support)
        usable=(support>=min_support)&np.isfinite(residual)
        if sigma<=0 or not usable.any():maps.append(np.full(image.shape,np.nan));scales.append(None);continue
        scale=sigma/np.sqrt(1.-1./n);scales.append(float(scale))
        maps.append(np.where(usable,(filtered-np.median(filtered[usable]))/scale,np.nan))
    return np.ascontiguousarray(maps,dtype=np.float32),dict(noise_proxy_scales=scales,reference_epoch_count=n,
        static_nuisance='full-stack finite-pixel temporal mean; min3reference samples',
        normalization='per-epoch filtered MAD corrected by sqrt(1-1/N), equal-noise approximation')
