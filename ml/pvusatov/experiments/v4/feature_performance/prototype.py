"""RESEARCH batch photometry; original source843/runtime/model remain immutable.

Producer hash is this module, explicitly distinct from its reference hash.
Uses reference map sampling unchanged. Only compact epoch-aligned reductions
are grouped; weighted astrometry/coherent dot products retain reference math.
"""
import hashlib,json
from pathlib import Path
import numpy as np
from ml.pvusatov.experiments.v4.detection import features as ref
FEATURE_NAMES=ref.FEATURE_NAMES
_coherent=ref._coherent
REFERENCE_SHA='8433495da9d0eda745903a9d63f430e3fc8b7c283b2ad7aded96511059b91282'
if hashlib.sha256(Path(ref.__file__).read_bytes()).hexdigest()!=REFERENCE_SHA:
    raise ValueError('research reference source changed')


def _batch_photometry(r,boundaries):
    good=(r['valid']>=1.-1e-10)&(r['error']>0)
    indices=[np.flatnonzero(good[start:end])+start for start,end in zip(boundaries[:-1],boundaries[1:])]
    counts=np.asarray([len(i)for i in indices]);results=[None]*len(indices);groups={}
    for count in np.unique(counts[counts>0]):
        ids=np.flatnonzero(counts==count);groups[str(int(count))]=len(ids)
        for offset in range(0,len(ids),4096):
            rows=ids[offset:offset+4096];ix=np.asarray([indices[int(i)]for i in rows])
            amp=r['amplitude'][ix];err=r['error'][ix];snr=r['snr'][ix]
            stats=dict(residual_psf_snr_median=np.median(snr,axis=1),residual_psf_snr_min=np.min(snr,axis=1),
                residual_psf_reduced_chi2_median=np.median(r['chi2'][ix],axis=1),
                residual_psf_correlation_median=np.median(r['correlation'][ix],axis=1),
                residual_negative_fraction_median=np.median(r['negative'][ix],axis=1),
                residual_amplitude_cv=np.std(amp,axis=1)/(abs(np.mean(amp,axis=1))+np.median(err,axis=1)),
                residual_positive_epoch_fraction=np.mean(amp>0,axis=1))
            for k,i in enumerate(rows):results[int(i)]={name:float(v[k])for name,v in stats.items()}
    return results,dict(groups_by_valid_epoch_count=groups,block_rows=4096,valid_rows=int(np.sum(counts>0)))


class BatchContext(ref.FeatureContext):
    def extract(self, tracks):
        tracks=list(tracks)
        if len(tracks)>50000:raise ValueError('candidate feature workload exceeds 50000 rows')
        rows=[];diagnostics=[];ids=[];boundaries=[0];base_cache=[]
        total=sum(len(t.epochs)for t in tracks)
        positions=np.empty((total,2));static=np.empty((total,2));epochs=np.empty(total,dtype=np.int16)
        for track in tracks:
            e=np.asarray(track.epochs);xy=np.asarray(track.positions_xy,dtype=float)
            base=np.asarray(track.features(),dtype=float)
            if (e.ndim!=1 or len(e)<3 or e.dtype.kind not in 'iu' or e.tolist()!=sorted(set(e.tolist()))
                    or np.any(e<0)or np.any(e>=len(self.times))or xy.shape!=(len(e),2)or not np.isfinite(xy).all()
                    or base.shape!=(6,)or not np.isfinite(base).all()):raise ValueError('measured candidate geometry/features invalid')
            base_cache.append(base.tolist())
            start=boundaries[-1];end=start+len(e)
            positions[start:end]=xy;epochs[start:end]=e;static[start:end]=xy.mean(axis=0);boundaries.append(end)
            ids.append(hashlib.sha256(json.dumps(dict(epochs=e.tolist(),positions_xy=xy.tolist()),sort_keys=True).encode()).hexdigest())
        if not tracks:return self._result(np.empty((0,30)),ids,diagnostics)
        r,raw,stationary,masks=self._samples(epochs,positions,static)
        batch_stats,self.batch_diagnostics=_batch_photometry(r,boundaries)
        for index,track in enumerate(tracks):
            start,end=boundaries[index:index+2];cut=slice(start,end);e=epochs[cut];xy=positions[cut];n=len(e)
            good=(r['valid'][cut]>=1.-1e-10)&(r['error'][cut]>0);rgood=(raw['valid'][cut]>=1.-1e-10)&(raw['error'][cut]>0)
            sgood=(stationary['valid'][cut]>=1.-1e-10)&(stationary['error'][cut]>0)
            missing=[];base=base_cache[index]; f={name:0. for name in FEATURE_NAMES[6:]}
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
                f.update(batch_stats[index]);f['residual_psf_snr_coherent']=_coherent(amp,err)
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
        output=super()._result(features,ids,diagnostics)
        output['reference_feature_source_sha256']=REFERENCE_SHA
        output['feature_source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        output['producer']='experimental-grouped-photometry-v1; not released or model-source-bound'
        output['batch_performance']=getattr(self,'batch_diagnostics',dict(valid_rows=0,block_rows=4096))
        return output


def extract_features(images,times,tracks,*,psf_sigma=.8,outlier=None,bloom=None,residuals=None):
    return BatchContext(images,times,psf_sigma=psf_sigma,outlier=outlier,bloom=bloom,residuals=residuals).extract(tracks)
