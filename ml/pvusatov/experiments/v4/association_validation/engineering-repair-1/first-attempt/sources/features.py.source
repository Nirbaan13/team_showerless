"""Candidate-derived physical proxies; no labels, ephemerides, or target positions.

Gaussian amplitude/background fits assume independent per-epoch MAD noise. These
are ranking proxies under correlated interpolation/residual noise, not calibrated
photometry, chi-square tests, posterior probabilities, or motion significances.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.ndimage import convolve, map_coordinates

FEATURE_VERSION = 'v4-physical-features-v1'
FEATURE_NAMES = (
    'epoch_count', 'fit_rms_px', 'median_snr', 'min_snr',
    'snr_coefficient_of_variation', 'median_peak_ratio',
    'linked_epoch_fraction', 'matched_timespan_hours', 'motion_span_over_psf',
    'motion_delta_chi2_proxy', 'velocity_snr_proxy', 'motion_fit_valid',
    'residual_psf_snr_median', 'residual_psf_snr_min', 'residual_psf_snr_coherent',
    'residual_psf_reduced_chi2_median', 'residual_psf_correlation_median',
    'residual_negative_fraction_median', 'residual_amplitude_cv',
    'residual_positive_epoch_fraction', 'moving_minus_static_coadd_snr2',
    'residual_to_raw_amplitude_ratio', 'raw_psf_reduced_chi2_median',
    'patch_valid_fraction_min', 'photometry_epoch_fraction',
    'photometry_summary_valid', 'static_photometry_epoch_fraction',
    'outlier_patch_fraction_mean', 'bloom_patch_fraction_mean', 'quality_masks_available',
)
FEATURE_GROUPS = dict(legacy=list(range(6)), kinematics=list(range(6,12)),
                     photometry=list(range(12,23)), support=list(range(23,30)))
CONTRACT = dict(version=FEATURE_VERSION, feature_names=FEATURE_NAMES,
                patch_radius='ceil(3*psf_sigma)', minimum_patch_support=.8,
                centroid_floor_px=.2, centroid_error='max(.2,psf_sigma/max(abs(template_snr),1))',
                covariance='weighted linear fit; reduced-chi2 inflation >=1',
                noise='per-epoch 1.4826*MAD; independent-pixel proxy',
                template='unit-sum Gaussian; local affine amplitude+constant background',
                fractional_coordinates='bilinear interpolation of fit maps',
                masks_available='fraction of outlier/bloom channels supplied',
                undefined='zero plus explicit support/validity columns and missing_statistics',
                static='mean measured candidate position, common valid matched epochs')
FEATURE_CONTRACT_SHA256 = hashlib.sha256(json.dumps(CONTRACT,sort_keys=True).encode()).hexdigest()


def _difference(images):
    residuals = np.full_like(images, np.nan)
    valid = np.isfinite(images)
    for epoch, image in enumerate(images):
        others = np.delete(images, epoch, axis=0)
        covered = valid[epoch] & np.isfinite(others).any(axis=0)
        residuals[epoch, covered] = image[covered] - np.nanmedian(others[:, covered],axis=0)
    return residuals


def _maps(images, kernel):
    """Bounded sufficient-statistic maps for y=a*PSF+b on finite patch pixels."""
    names = ('amplitude','error','snr','chi2','correlation','negative','support','valid')
    result = {name:np.zeros(images.shape,dtype=np.float64) for name in names}
    ones = np.ones(kernel.shape); area = float(kernel.size)
    for epoch, image in enumerate(images):
        valid = np.isfinite(image); values = image[valid]
        if not len(values): continue
        noise = 1.4826*np.median(abs(values-np.median(values)))
        count = convolve(valid.astype(float),ones,mode='constant',cval=0.)
        result['support'][epoch] = count/area
        if not np.isfinite(noise) or noise<=0: continue
        pixels = np.where(valid,image,0.)
        p = convolve(valid.astype(float),kernel,mode='constant',cval=0.)
        p2 = convolve(valid.astype(float),kernel*kernel,mode='constant',cval=0.)
        y = convolve(pixels,ones,mode='constant',cval=0.)
        y2 = convolve(pixels*pixels,ones,mode='constant',cval=0.)
        py = convolve(pixels,kernel,mode='constant',cval=0.)
        safe = np.maximum(count,1.)
        norm = np.maximum(p2-p*p/safe,0.)
        covariance = py-p*y/safe; variance = np.maximum(y2-y*y/safe,0.)
        good = valid & (count>=6) & (count/area>=.8) & (norm>1e-15)
        amplitude = np.divide(covariance,norm,out=np.zeros_like(norm),where=good)
        error = np.divide(noise,np.sqrt(norm),out=np.zeros_like(norm),where=good)
        snr = np.divide(amplitude,error,out=np.zeros_like(norm),where=good)
        fit_power = np.divide(covariance*covariance,norm,out=np.zeros_like(norm),where=good)
        chi2 = np.maximum(variance-fit_power,0.)/(noise*noise*np.maximum(count-2,1.))
        correlation = np.divide(covariance,np.sqrt(norm*variance),out=np.zeros_like(norm),where=good&(variance>0))
        negative = convolve(np.maximum(-pixels,0.),kernel,mode='constant',cval=0.)
        total = convolve(abs(pixels),kernel,mode='constant',cval=0.)
        negative = np.divide(negative,total,out=np.zeros_like(norm),where=good&(total>0))
        for name,value in dict(amplitude=amplitude,error=error,snr=snr,chi2=chi2,
                               correlation=np.clip(correlation,-1,1),negative=negative).items():
            result[name][epoch] = np.where(good,value,0.)
        result['valid'][epoch] = good
    return result


def _sample(maps, epochs, xy):
    coords = np.asarray([epochs,xy[:,1],xy[:,0]])
    return {key:map_coordinates(value,coords,order=1,mode='constant',cval=0.,prefilter=False)
            for key,value in maps.items()}


def _coherent(amplitudes, errors):
    weights = 1./np.square(errors)
    return float(np.dot(amplitudes,weights)/np.sqrt(weights.sum()))


class FeatureContext:
    """Retain only input/residual stacks; stream and discard 2D epoch fit maps."""
    def __init__(self, images, times, *, psf_sigma=.8, outlier=None, bloom=None, residuals=None):
        images=np.asarray(images,dtype=float);times=np.asarray(times,dtype=float)
        if (images.ndim!=3 or not 3<=len(images)<=32 or not 1<=min(images.shape[1:])
                or max(images.shape[1:])>512 or np.isinf(images).any()
                or times.shape!=(len(images),) or not np.isfinite(times).all() or np.any(np.diff(times)<=0)
                or not np.isfinite(psf_sigma) or not .3<=psf_sigma<=3.):
            raise ValueError('bounded finite images, increasing physical times and valid PSF width required')
        self.times=times-times[0];self.psf_sigma=float(psf_sigma);self.shape=images.shape
        radius=int(np.ceil(3*psf_sigma)); yy,xx=np.mgrid[-radius:radius+1,-radius:radius+1]
        kernel=np.exp(-(xx*xx+yy*yy)/(2*psf_sigma*psf_sigma));kernel/=kernel.sum()
        residuals=_difference(images)if residuals is None else np.asarray(residuals,dtype=float)
        if residuals.shape!=images.shape or np.isinf(residuals).any():raise ValueError('residual dimensions/values differ')
        self.images=images;self.residuals=residuals;self.kernel=kernel
        self.masks={};self.mask_availability={}
        for name,value in [('outlier',outlier),('bloom',bloom)]:
            self.mask_availability[name]=value is not None
            if value is not None and(np.asarray(value).shape!=images.shape or np.asarray(value).dtype.kind!='b'):
                raise ValueError('quality masks must be aligned boolean arrays')
            self.masks[name]=None if value is None else np.asarray(value)

    def _samples(self,epochs,positions,static):
        """O(N matched positions) storage; no full-frame statistic cubes."""
        n=len(epochs);keys=('amplitude','error','snr','chi2','correlation','negative','support','valid')
        residual={k:np.empty(n)for k in keys}
        raw={k:np.empty(n)for k in ('amplitude','error','chi2','valid')}
        stationary={k:np.empty(n)for k in ('amplitude','error','valid')}
        masks={k:np.zeros(n)for k in self.masks}
        for epoch in np.unique(epochs):
            ids=np.flatnonzero(epochs==epoch);local_epochs=np.zeros(len(ids),dtype=int)
            maps=_maps(self.residuals[epoch:epoch+1],self.kernel)
            for key,value in _sample(maps,local_epochs,positions[ids]).items():residual[key][ids]=value
            for key,value in _sample({k:maps[k]for k in stationary},local_epochs,static[ids]).items():stationary[key][ids]=value
            del maps
            maps=_maps(self.images[epoch:epoch+1],self.kernel)
            for key,value in _sample({k:maps[k]for k in raw},local_epochs,positions[ids]).items():raw[key][ids]=value
            del maps
            for key,mask in self.masks.items():
                if mask is not None:
                    fraction=np.clip(convolve(mask[epoch].astype(float),np.ones(self.kernel.shape)/self.kernel.size,
                                             mode='constant',cval=0.),0.,1.)
                    masks[key][ids]=map_coordinates(fraction,np.asarray([positions[ids,1],positions[ids,0]]),
                                                   order=1,mode='constant',cval=0.,prefilter=False)
        return residual,raw,stationary,masks

    def extract(self, tracks):
        tracks=list(tracks)
        if len(tracks)>50000:raise ValueError('candidate feature workload exceeds 50000 rows')
        rows=[];diagnostics=[];ids=[];boundaries=[0]
        total=sum(len(t.epochs)for t in tracks)
        positions=np.empty((total,2));static=np.empty((total,2));epochs=np.empty(total,dtype=np.int16)
        for track in tracks:
            e=np.asarray(track.epochs);xy=np.asarray(track.positions_xy,dtype=float)
            base=np.asarray(track.features(),dtype=float)
            if (e.ndim!=1 or len(e)<3 or e.dtype.kind not in 'iu' or e.tolist()!=sorted(set(e.tolist()))
                    or np.any(e<0)or np.any(e>=len(self.times))or xy.shape!=(len(e),2)or not np.isfinite(xy).all()
                    or base.shape!=(6,)or not np.isfinite(base).all()):raise ValueError('measured candidate geometry/features invalid')
            start=boundaries[-1];end=start+len(e)
            positions[start:end]=xy;epochs[start:end]=e;static[start:end]=xy.mean(axis=0);boundaries.append(end)
            ids.append(hashlib.sha256(json.dumps(dict(epochs=e.tolist(),positions_xy=xy.tolist()),sort_keys=True).encode()).hexdigest())
        if not tracks:return self._result(np.empty((0,30)),ids,diagnostics)
        r,raw,stationary,masks=self._samples(epochs,positions,static)
        for index,track in enumerate(tracks):
            start,end=boundaries[index:index+2];cut=slice(start,end);e=epochs[cut];xy=positions[cut];n=len(e)
            good=(r['valid'][cut]>=1.-1e-10)&(r['error'][cut]>0);rgood=(raw['valid'][cut]>=1.-1e-10)&(raw['error'][cut]>0)
            sgood=(stationary['valid'][cut]>=1.-1e-10)&(stationary['error'][cut]>0)
            missing=[];base=list(map(float,track.features())); f={name:0. for name in FEATURE_NAMES[6:]}
            f.update(linked_epoch_fraction=n/len(self.times),matched_timespan_hours=float(np.ptp(self.times[e])),
                     motion_span_over_psf=float(np.max(np.linalg.norm(xy[:,None]-xy[None,:],axis=-1)))/self.psf_sigma,
                     patch_valid_fraction_min=float(np.min(r['support'][cut])),photometry_epoch_fraction=float(np.mean(good)),
                     photometry_summary_valid=float(good.sum()>=3),static_photometry_epoch_fraction=float(np.mean(sgood)),
                     outlier_patch_fraction_mean=float(np.mean(masks['outlier'][cut])),
                     bloom_patch_fraction_mean=float(np.mean(masks['bloom'][cut])),
                     quality_masks_available=sum(self.mask_availability.values())/2.)
            if good.sum()>=3:
                t=self.times[e][good];p=xy[good]
                sigma=np.maximum(.2,self.psf_sigma/np.maximum(abs(r['snr'][cut][good]),1.));w=1./sigma**2
                tc=t-np.average(t,weights=w);pc=p-np.average(p,weights=w,axis=0);den=float(np.dot(w,tc*tc))
                velocity=np.sum(w[:,None]*tc[:,None]*pc,axis=0)/den
                residual=pc-tc[:,None]*velocity;chi0=float(np.sum(w[:,None]*pc*pc));chi1=float(np.sum(w[:,None]*residual*residual))
                inflation=max(1.,chi1/max(2*len(t)-4,1));variance=inflation/den
                f.update(motion_delta_chi2_proxy=max(0.,chi0-chi1),velocity_snr_proxy=float(np.linalg.norm(velocity)/np.sqrt(variance)),motion_fit_valid=1.)
            else:missing.extend(['motion_delta_chi2_proxy','velocity_snr_proxy'])
            if good.any():
                amp=r['amplitude'][cut][good];err=r['error'][cut][good];snr=r['snr'][cut][good]
                f.update(residual_psf_snr_median=float(np.median(snr)),residual_psf_snr_min=float(np.min(snr)),
                         residual_psf_snr_coherent=_coherent(amp,err),residual_psf_reduced_chi2_median=float(np.median(r['chi2'][cut][good])),
                         residual_psf_correlation_median=float(np.median(r['correlation'][cut][good])),
                         residual_negative_fraction_median=float(np.median(r['negative'][cut][good])),
                         residual_amplitude_cv=float(np.std(amp)/(abs(np.mean(amp))+np.median(err))),
                         residual_positive_epoch_fraction=float(np.mean(amp>0)))
            else:missing.extend(FEATURE_NAMES[12:20])
            common=good&sgood
            if common.any():
                moving=_coherent(r['amplitude'][cut][common],r['error'][cut][common]);still=_coherent(stationary['amplitude'][cut][common],stationary['error'][cut][common])
                f['moving_minus_static_coadd_snr2']=float(moving*abs(moving)-still*abs(still))
            else:missing.append('moving_minus_static_coadd_snr2')
            common=good&rgood
            if common.any():
                f['residual_to_raw_amplitude_ratio']=float(np.median(r['amplitude'][cut][common]/(abs(raw['amplitude'][cut][common])+raw['error'][cut][common])))
                f['raw_psf_reduced_chi2_median']=float(np.median(raw['chi2'][cut][common]))
            else:missing.extend(['residual_to_raw_amplitude_ratio','raw_psf_reduced_chi2_median'])
            row=base+[f[name]for name in FEATURE_NAMES[6:]]
            if not np.isfinite(row).all():raise ValueError('physical feature proxy is nonfinite')
            rows.append(row);diagnostics.append(dict(candidate_id=ids[index],missing_statistics=missing,
                photometry_valid_epochs=e[good].tolist(),static_valid_epochs=e[sgood].tolist(),
                raw_valid_epochs=e[rgood].tolist(),quality_masks_available=dict(self.mask_availability)))
        return self._result(np.asarray(rows),ids,diagnostics)

    def _result(self,features,ids,diagnostics):
        return dict(features_v4=features,feature_names=list(FEATURE_NAMES),feature_version=FEATURE_VERSION,
                    feature_contract_sha256=FEATURE_CONTRACT_SHA256,feature_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    candidate_ids=ids,diagnostics=diagnostics,template_psf_sigma=self.psf_sigma)


def extract_features(images,times,tracks,*,psf_sigma=.8,outlier=None,bloom=None,residuals=None):
    return FeatureContext(images,times,psf_sigma=psf_sigma,outlier=outlier,bloom=bloom,residuals=residuals).extract(tracks)
