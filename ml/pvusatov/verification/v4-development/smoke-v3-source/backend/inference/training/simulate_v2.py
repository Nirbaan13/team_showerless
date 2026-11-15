"""Domain-balanced physical field simulation for the six-feature v2 ranker.

Source brightness, PSF family and variability are drawn independently of
injected-vs-transient identity. Instrument ePSFs are pixel-convolved responses,
so rendering samples native pixels once and then performs bilinear registration.
"""
from pathlib import Path
import json
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from training.evaluate_background import native_psf_patch


def draw_flux(rng, noise):
    """A common integrated-amplitude law for real sources and transient artifacts."""
    return float(noise*np.exp(rng.uniform(np.log(6.),np.log(600.))))


def draw_cadence(rng,n):
    family=int(rng.integers(4))
    if family==0:
        gaps=rng.uniform(.3,1.5,n-1)
    elif family==1:
        gaps=rng.uniform(.015,.065,n-1)
    elif family==2:
        gaps=rng.uniform(.02,.07,n-1);gaps[-1]=rng.uniform(2,7)
    else:
        gaps=rng.uniform(.02,.10,n-1);gaps[max(0,(n-1)//2)]=rng.uniform(1,6)
    return np.r_[0,np.cumsum(gaps)],family


def procedural_bank():
    """Analytic core/wing responses supplement native calibration, never replace it."""
    yy,xx=np.indices((33,33),dtype=float);x=(xx-16)/5;y=(yy-16)/5
    stamps=[]
    for sigma in [.5,.65,.8,1.,1.3,1.65]:
        for ratio in [.75,1.,1.3]:
            core=np.exp(-.5*((x/sigma)**2+(y/(sigma*ratio))**2))
            wing=np.exp(-.5*(x*x+y*y)/(2*sigma)**2)
            stamp=.9*core+.1*wing;stamps.append(stamp/stamp.sum())
    return dict(stamps=np.asarray(stamps),oversampling=5,
                detectors=np.zeros(len(stamps),dtype=int),provenance=dict(kind='analytic_core_wing'))


def load_bank(path):
    with np.load(path,allow_pickle=False)as data:
        stamps=np.asarray(data['stamps'],dtype=float)
        detectors=np.asarray(data['detectors'],dtype=int)
        oversampling=int(data['oversampling'])
        provenance=json.loads(str(data['provenance_json']))
    if stamps.ndim!=3 or stamps.shape[1:]!=(33,33)or len(detectors)!=len(stamps)or oversampling!=5:
        raise ValueError('expected local 33x33 five-times-sampled calibration responses')
    if not np.isfinite(stamps).all()or np.any(stamps.sum(axis=(1,2))<=0):
        raise ValueError('calibration bank contains invalid PSFs')
    return dict(stamps=stamps,detectors=detectors,oversampling=oversampling,provenance=provenance)


def render_source(image,position,flux,stamp,oversampling,angle,phase):
    x,y=map(float,position);radius=6
    left=max(0,int(np.floor(x))-radius);right=min(image.shape[1],int(np.floor(x))+radius+2)
    top=max(0,int(np.floor(y))-radius);bottom=min(image.shape[0],int(np.floor(y))+radius+2)
    if left>=right or top>=bottom:return
    rotation=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]])
    native_xy=rotation@np.asarray([x,y])+phase
    patch,x0,y0=native_psf_patch(stamp,oversampling,oversampling,*native_xy)
    yy,xx=np.indices((bottom-top,right-left));points=np.stack([xx+left,yy+top]).reshape(2,-1)
    native=rotation@points+np.asarray(phase)[:,None]
    registered=map_coordinates(patch,[native[1]-y0,native[0]-x0],order=1,mode='constant',cval=0)
    image[top:bottom,left:right]+=flux*registered.reshape(bottom-top,right-left)


def simulate(seed,bank,*,extended=False,varying_psf=False):
    rng=np.random.default_rng(seed)
    psf_rng=np.random.default_rng(seed+424242)
    profile_rng=np.random.default_rng(seed+242424)
    mode='noise_only'if seed%10==0 else'artifacts_only'if seed%10==1 else'injected'
    n=int(rng.choice([3,4,5,6,7,8],p=[.30,.25,.15,.15,.075,.075]));times,cadence=draw_cadence(rng,n)
    size=80;noise=float(rng.uniform(.6,1.8));images=rng.normal(0,noise,(n,size,size))
    # Registration produces correlated background noise; the same law covers all classes.
    if rng.random()<.65:
        for image in images:image[:]=gaussian_filter(image,rng.uniform(.2,.65))
    details=dict(epoch_count=n,cadence_family=cadence,positive_fluxes=[],artifact_fluxes=[],
                 label_nuisance_policy='shared flux law, field PSF and overlapping variability for source/artifact identities')
    if mode=='noise_only':return images,times,[],mode,details
    detector=int(rng.choice(np.unique(bank['detectors'])))
    options=np.flatnonzero(bank['detectors']==detector)
    use_analytic=rng.random()<.2
    chosen=procedural_bank()if use_analytic else bank
    options=np.arange(len(chosen['stamps']))if use_analytic else options
    stamp_id=int(rng.choice(options));stamp=chosen['stamps'][stamp_id]
    angle=float(rng.uniform(0,2*np.pi));angles=angle+rng.normal(0,.015,n)
    phases=rng.uniform(-.5,.5,(n,2));jitter=rng.normal(0,rng.uniform(.03,.25),(n,2))
    gain=rng.lognormal(0,rng.uniform(.02,.25),n)
    details.update(detector=detector,psf_family='analytic_core_wing'if use_analytic else'calibration',
                   psf_bank_row=stamp_id,registration_jitter_xy=jitter.tolist(),
                   extended_stationary_sources=0,epoch_psf_rows=[stamp_id]*n)
    epoch_ids=np.full(n,stamp_id,dtype=int)
    if varying_psf:
        anchor=int(np.where(options==stamp_id)[0][0])
        offsets=psf_rng.integers(-9,10,n)if not use_analytic else psf_rng.integers(-3,4,n)
        epoch_ids=options[np.clip(anchor+offsets,0,len(options)-1)]
    epoch_stamps=[chosen['stamps'][i]for i in epoch_ids]
    details['epoch_psf_rows']=epoch_ids.tolist()
    def profiles(blur):
        if not blur:return epoch_stamps
        return [gaussian_filter(v,blur*chosen['oversampling'])for v in epoch_stamps]
    def render(epoch,xy,flux,source_profiles=None):
        response=epoch_stamps[epoch]if source_profiles is None else source_profiles[epoch]
        render_source(images[epoch],np.asarray(xy)+jitter[epoch],flux*gain[epoch],response,
                      chosen['oversampling'],angles[epoch],phases[epoch])
    for _ in range(int(rng.integers(18,40))):
        position=rng.uniform(4,size-4,2);flux=draw_flux(rng,noise)
        variation=rng.uniform(.05,.7);factors=rng.lognormal(-variation*variation/2,variation,n)
        for epoch in range(n):render(epoch,position,flux*factors[epoch])
    if extended:
        count=int(profile_rng.integers(3,9));details['extended_stationary_sources']=count
        for _ in range(count):
            center=profile_rng.uniform(6,size-6,2);flux=draw_flux(profile_rng,noise)
            broad=profiles(profile_rng.uniform(.8,2.5));offset=profile_rng.normal(0,.9,2)
            factors=profile_rng.lognormal(-.2,.6,(n,2))
            for epoch in range(n):
                render(epoch,center,.65*flux*factors[epoch,0],broad)
                render(epoch,center+offset,.35*flux*factors[epoch,1],broad)
    truth=[]
    if mode=='injected':
        for _ in range(int(rng.integers(1,5))):
            for attempt in range(30):
                origin=rng.uniform(12,size-12,2)
                span=times[-1]if rng.random()<.5 else times[2]
                lo=max(.5,1.5/span);hi=min(60.,45/span)
                if lo>=hi:lo,hi=.5,60.
                speed=float(np.exp(rng.uniform(np.log(lo),np.log(hi))))
                direction=rng.uniform(0,2*np.pi);velocity=speed*np.array([np.cos(direction),np.sin(direction)])
                positions=origin+times[:,None]*velocity
                covered=np.all((positions>=5)&(positions<size-5),axis=1)
                if covered.sum()>=3:break
            flux=draw_flux(rng,noise);details['positive_fluxes'].append(flux/noise)
            variation=rng.uniform(.05,.7);factors=rng.lognormal(-variation*variation/2,variation,n)
            source_profiles=profiles(profile_rng.uniform(.8,2.5))if extended and profile_rng.random()<.2 else epoch_stamps
            drop=int(rng.integers(n))if n>3 and rng.random()<.25 else-1
            for epoch in range(n):
                if epoch!=drop:render(epoch,positions[epoch],flux*factors[epoch],source_profiles)
            truth.append(positions+jitter)
    for epoch in range(n):
        for _ in range(int(rng.integers(8,22))):
            xy=rng.uniform(3,size-3,2);flux=draw_flux(rng,noise)
            details['artifact_fluxes'].append(flux/noise)
            source_profiles=profiles(profile_rng.uniform(.8,2.5))if extended and profile_rng.random()<.2 else epoch_stamps
            render(epoch,xy,flux,source_profiles)
        for _ in range(int(rng.integers(3,10))):
            x,y=rng.integers(2,size-2,2);images[epoch,y,x]+=draw_flux(rng,noise)
    # Fixed-offset strip and isolated bad patches represent changing real coverage.
    if rng.random()<.8:
        for epoch in range(n):
            if rng.random()<.5:
                gap=int(rng.integers(2,size-8));images[epoch,:,gap:gap+int(rng.integers(1,7))]=np.nan
            if rng.random()<.35:
                x,y=rng.integers(0,size-12,2);images[epoch,y:y+12,x:x+12]=np.nan
    return images,times,truth,mode,details
