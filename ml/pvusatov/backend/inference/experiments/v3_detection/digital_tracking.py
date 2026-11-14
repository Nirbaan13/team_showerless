"""Experimental mean-nuisance projected linear Gaussian template search.

Positions are fitted template hypotheses, not independently measured epoch peaks.
The template score is an uncalibrated search statistic; never a flux/probability.
"""
import ctypes,hashlib,subprocess
from pathlib import Path
from dataclasses import dataclass
import numpy as np
from ml_inference.detector import filtered_evidence,DetectionLimitError

@dataclass(frozen=True)
class JointCandidate:
    epochs:tuple
    positions_xy:tuple
    statistic:float
    velocity_xy_per_hour:tuple
    per_epoch_filtered_residual:tuple

_lib=None

def library():
    global _lib
    if _lib is None:
        source=Path(__file__).with_suffix('.cpp');digest=hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        path=Path('/tmp/spaceapps-v3-detection')/f'digital-{digest}.so'
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():subprocess.run(['g++','-O3','-shared','-fPIC','-o',str(path),str(source)],check=True)
        _lib=ctypes.CDLL(str(path));_lib.search.restype=ctypes.c_int
        ptr=np.ctypeslib.ndpointer
        _lib.search.argtypes=[ptr(np.float32,flags='C_CONTIGUOUS'),ptr(np.float64,flags='C_CONTIGUOUS'),ctypes.c_int,ctypes.c_int,ctypes.c_int,
            ctypes.c_double,ctypes.c_double,ctypes.c_double,ctypes.c_int,ctypes.c_double,ctypes.c_double,ctypes.c_int64,ctypes.c_int,
            ptr(np.float32,flags='C_CONTIGUOUS'),ptr(np.int16,flags='C_CONTIGUOUS'),ptr(np.int16,flags='C_CONTIGUOUS'),ctypes.POINTER(ctypes.c_int64)]
    return _lib

def find_joint_candidates(images,times,*,min_speed=.5,max_speed=60.,psf_sigma=1.2,min_support=.8,step_px=1.,max_displacement_px=64.,threshold=6.,max_candidates=100,max_work=600_000_000,statistic="trimmed"):
    images=np.asarray(images,float);times=np.ascontiguousarray(times,dtype=np.float64)
    if images.ndim!=3 or not 3<=len(images)<=32 or not 1<=min(images.shape[1:])<=max(images.shape[1:])<=512:raise ValueError('requires 3..32 frames, at most 512 grid')
    if times.shape!=(len(images),)or not np.isfinite(times).all()or np.any(np.diff(times)<=0):raise ValueError('strictly increasing physical-hour times required')
    settings=[min_speed,max_speed,psf_sigma,min_support,step_px,max_displacement_px,threshold,max_work,max_candidates]
    if not np.isfinite(settings).all()or not 0<min_speed<=max_speed or min(settings)<=0 or min_support>1:raise ValueError('positive finite bounded search settings required')
    if not isinstance(max_candidates,int)or not isinstance(max_work,int):raise ValueError('integer candidate and work caps required')
    if np.isinf(images).any():raise ValueError('infinite images unsupported')
    displacement=int(np.ceil(min(max_displacement_px,max_speed*(times[-1]-times[0]))/step_px))
    if (2*displacement+1)**2>65536:raise ValueError('velocity grid exceeds 65536 bounded hypotheses')
    if statistic not in ("sum", "trimmed"):raise ValueError("unknown joint statistic")
    n,h,w=images.shape;valid=np.isfinite(images);count=valid.sum(axis=0)
    # Constant spatial nuisance is eliminated before motion template fitting.
    mean=np.divide(np.where(valid,images,0).sum(axis=0),count,out=np.zeros((h,w)),where=count>0)
    residual=np.where(valid & (count>=3),images-mean,np.nan)
    maps=[];noise=[]
    for image in residual:
        filtered,_,support,sigma=filtered_evidence(image,np.isfinite(image),psf_sigma,min_support)
        if sigma<=0:maps.append(np.full((h,w),np.nan));noise.append(0);continue
        # Approximation: normalize per-epoch residual MAD back to raw-epoch noise.
        usable=(support>=min_support)&np.isfinite(image)
        centered=filtered-np.median(filtered[usable]);scale=sigma/np.sqrt(1-1/n)
        maps.append(np.where(usable,centered/scale,np.nan));noise.append(float(scale))
    maps=np.ascontiguousarray(maps,dtype=np.float32);best=np.empty((h,w),np.float32);bx=np.zeros((h,w),np.int16);by=bx.copy();work=ctypes.c_int64()
    code=library().search(maps,times,n,h,w,min_speed,max_speed,step_px,displacement,psf_sigma,threshold,max_work,int(statistic=="trimmed"),best,bx,by,ctypes.byref(work))
    if code:raise DetectionLimitError(f'joint search exceeds work cap {max_work}; partial results withheld')
    finite=np.flatnonzero(np.isfinite(best));order=finite[np.argsort(-best.ravel()[finite],kind='stable')]
    candidates=[];paths=[];cap=False
    for index in order:
        y,x=divmod(int(index),w);velocity=np.array([bx[y,x],by[y,x]])*step_px/(times[-1]-times[0]);positions=np.array([x,y])+np.rint((times-times[0])[:,None]*velocity)
        if any(np.median(np.linalg.norm(positions-path,axis=1))<2 for path in paths):continue
        if len(candidates)>=max_candidates:cap=True;break
        sample=maps[np.arange(n),positions[:,1].astype(int),positions[:,0].astype(int)]
        candidates.append(JointCandidate(tuple(range(n)),tuple(map(tuple,positions.tolist())),float(best[y,x]),tuple(velocity.tolist()),tuple(map(float,sample))))
        paths.append(positions)
    return candidates,dict(work_pixels_epochs=work.value,velocity_endpoint_step_px=step_px,max_displacement_px=max_displacement_px,
       statistic=statistic,fitted_hypotheses_above_threshold=len(finite),candidate_cap_reached=cap,noise_scale=noise,
       warnings=['experimental_mean_template_projection','uncalibrated_joint_statistic','fitted_template_positions_not_epoch_peaks','equal_epoch_noise_approximation','spatially_correlated_noise_approximation','all_epoch_support_required'])
