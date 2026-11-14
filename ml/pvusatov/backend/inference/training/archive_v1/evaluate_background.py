"""Held-out registered-real-background injection with native local SPHEREx ePSFs.

No fitting; all derivatives of these four exposures remain one held-out field.
Unknown real tracks remain unlabeled. Native inputs are opened read-only.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates

from ml_inference.prepare import prepare, SOURCE_BIT, OUTLIER_BIT
from ml_inference.detector import find_candidates, difference_frames, _detect_peaks
from ml_inference.model import load_ranker

SETTINGS = dict(min_snr=4., max_peaks=100, psf_sigma=1.2, min_speed=.5,
                max_speed=60., match_radius=1.4, min_epochs=3, min_support=.8,
                leave_one_out=True)


def trajectory(origin, velocity, times):
    return np.asarray(origin) + np.asarray(times)[:, None] * np.asarray(velocity)


def native_psf_patch(epsf, oversampling_x, oversampling_y, x, y):
    """Sample the supplied pixel-convolved ePSF at native pixel centers."""
    rx = int(np.ceil((epsf.shape[1]-1)/(2*oversampling_x)))+1
    ry = int(np.ceil((epsf.shape[0]-1)/(2*oversampling_y)))+1
    x0, y0 = int(np.floor(x))-rx, int(np.floor(y))-ry
    yy, xx = np.indices((2*ry+1, 2*rx+1))
    samples = map_coordinates(epsf, [(yy+y0-y)*oversampling_y+(epsf.shape[0]-1)/2,
                                    (xx+x0-x)*oversampling_x+(epsf.shape[1]-1)/2],
                              order=1, mode='constant', cval=0)
    if not np.isfinite(samples).all() or samples.sum() <= 0:
        raise ValueError('invalid local empirical PSF')
    return samples/samples.sum(), x0, y0


def add_projected_injection(images, responses, flux):
    return np.where(np.isfinite(images), images + flux*responses, np.nan)


def injection_recovery(tracks, scores, expected, top_k=3, tolerance=1.5):
    order = np.argsort(-scores, kind='stable')
    ranks = {int(index):rank for rank,index in enumerate(order,1)}
    matches = []
    for index, track in enumerate(tracks):
        offsets = np.linalg.norm(np.asarray(track.positions_xy)-expected[list(track.epochs)],axis=1)
        if np.all(offsets <= tolerance):
            matches.append(dict(baseline_rank=index+1, model_rank=ranks[index],
                                epochs=list(track.epochs), max_offset_px=float(offsets.max()),
                                model_score=float(scores[index]), features=list(map(float,track.features()))))
    return dict(candidates=len(tracks), recovered_before_ranking=bool(matches),
                baseline_recovered_at_k=any(m['baseline_rank']<=top_k for m in matches),
                model_recovered_at_k=any(m['model_rank']<=top_k for m in matches),
                matches=matches, other_candidates_unlabeled=len(tracks)-len(matches))


def read_native(path, grid, shape):
    with fits.open(path, memmap=False) as hdus:
        header = hdus[0].header.copy(); header.update(hdus['IMAGE'].header)
        wcs = WCS(header).celestial
        signal = np.asarray(hdus['IMAGE'].data,float)-hdus['ZODI'].data
        flags = hdus['FLAGS'].data.astype(np.int64)
        good = ((flags & ~(SOURCE_BIT|OUTLIER_BIT))==0)&np.isfinite(signal)&np.isfinite(hdus['VARIANCE'].data)&(hdus['VARIANCE'].data>0)
        yy,xx = np.indices(shape)
        native_x,native_y = wcs.world_to_pixel_values(*grid.pixel_to_world_values(xx,yy))
        support = map_coordinates(good.astype(float), [native_y,native_x], order=1, cval=0)
        table = hdus['EPSF'].data.copy()
        epsf_header = hdus['EPSF'].header.copy()
    if int(header.get('DETECTOR',2)) != 2 or epsf_header.get('DETCOORD') != 'sky':
        raise ValueError('evaluation is scoped to SWIR detector 2 sky-coordinate ePSFs')
    return dict(header=header,wcs=wcs,good=good,native_x=native_x,native_y=native_y,
                support=support,table=table,epsf_header=epsf_header)


def project_response(native, grid, position):
    sky = grid.pixel_to_world_values(*position)
    x,y = map(float,native['wcs'].world_to_pixel_values(*sky))
    # IRSA's documented cutout-to-parent transformation; no SIP on the linear A WCS.
    parent_x = 1+x-native['header'].get('CRPIX1A',1.)
    parent_y = 1+y-native['header'].get('CRPIX2A',1.)
    table = native['table']
    zone = int(np.argmin((table['XCENTER']-parent_x)**2+(table['YCENTER']-parent_y)**2))
    row = table[zone]
    patch,x0,y0 = native_psf_patch(np.asarray(row['EPSF'],float),native['epsf_header']['OVSMPX'],
                                  native['epsf_header']['OVSMPY'],x,y)
    yy,xx = np.indices(patch.shape); ix=xx+x0; iy=yy+y0
    inside=(ix>=0)&(iy>=0)&(ix<native['good'].shape[1])&(iy<native['good'].shape[0])
    masked=np.zeros_like(patch)
    masked[inside]=patch[inside]*native['good'][iy[inside],ix[inside]]
    projected=map_coordinates(masked,[native['native_y']-y0,native['native_x']-x0],order=1,cval=0)
    projected=np.divide(projected,native['support'],where=native['support']>=.995,out=np.zeros_like(projected))
    return projected,dict(zone=zone,bin_x=int(row['BINX']),bin_y=int(row['BINY']),
                          source_parent_xy=[parent_x,parent_y],wavelength_um=float(row['CWAVE']),
                          oversampling=[int(native['epsf_header']['OVSMPX']),int(native['epsf_header']['OVSMPY'])])


def detect(images,times,ranker):
    tracks=find_candidates(images,times,**SETTINGS)
    x=np.asarray([t.features() for t in tracks],np.float32).reshape(-1,6)
    scores=ranker.score(x)
    residuals=difference_frames(images,True)
    peaks=[len(_detect_peaks(d,np.isfinite(d),1.2,4,100,.8))for d in residuals]
    return tracks,scores,dict(peaks_per_epoch=peaks,peak_cap_reached=any(n>=100 for n in peaks),feature_rows=x.tolist())


def summarize(trials, top_k):
    return dict(injections=len(trials),eligible_center_coverage_at_least_3=sum(t['usable_center_epochs']>=3 for t in trials),
                recovered_before_ranking=sum(t['recovery']['recovered_before_ranking'] for t in trials),
                baseline_recovered_at_k=sum(t['recovery']['baseline_recovered_at_k'] for t in trials),
                model_recovered_at_k=sum(t['recovery']['model_recovered_at_k'] for t in trials),
                baseline_recovered_at_1=sum(any(m['baseline_rank']==1 for m in t['recovery']['matches']) for t in trials),
                model_recovered_at_1=sum(any(m['model_rank']==1 for m in t['recovery']['matches']) for t in trials),
                preexisting_control_match_trials=sum(t['control_match_before_injection'] for t in trials),
                top_k=top_k,total_candidate_rows=sum(t['recovery']['candidates'] for t in trials),
                trials_with_peak_cap=sum(t['detection']['peak_cap_reached']for t in trials))


def run(input_dir,output,top_k=3):
    started=time.monotonic();input_dir=Path(input_dir)
    downloads=json.loads((input_dir/'downloads.json').read_text())
    paths=[input_dir/Path(row['path']).name for row in downloads]
    source_rows=[]
    for row,path in zip(downloads,paths):
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=row['sha256']:raise ValueError('real input source checksum mismatch')
        source_rows.append(dict(filename=path.name,sha256=digest,bytes=path.stat().st_size,url=row['url']))
    request=dict(schema_version=1,analysis_id='heldout-m101-background',
                 source=dict(kind='fits',observations=[dict(path=str(p),frame_id=p.stem,observation_id=p.stem)for p in paths],
                             region=dict(right_ascension_deg=210.80227,declination_deg=54.34895,width_arcmin=6,height_arcmin=6)))
    stack=prepare(request);ranker=load_ranker();original_hash=ranker.metadata['sha256']
    lookup={p.stem:p for p in paths};paths=[lookup[f['frame_id']]for f in stack.frames]
    native=[read_native(p,stack.grid,stack.images.shape[1:])for p in paths]
    tracks,scores,detection=detect(stack.images,stack.times,ranker)
    control_tracks,control_scores=tracks,scores
    control=dict(candidates=len(tracks),detection=detection,candidate_scores=scores.tolist(),
                 labels='all unmodified real candidates remain unlabeled')
    sigma=[]
    for image in stack.images:
        values=image[np.isfinite(image)];sigma.append(float(1.4826*np.median(abs(values-np.median(values)))))
    rng=np.random.default_rng(932711);trials=[]
    for speed in [1.,4.,10.,25.,50.]:
        for direction_index in range(6):
            origin=rng.uniform(8,51,2); angle=rng.uniform(0,2*np.pi)
            velocity=speed*np.array([np.cos(angle),np.sin(angle)])
            positions=trajectory(origin,velocity,stack.times)
            responses=[];epsf=[];center_usable=0
            for n,position,image in zip(native,positions,stack.images):
                response,meta=project_response(n,stack.grid,position);responses.append(response);epsf.append(meta)
                x,y=np.rint(position).astype(int)
                center_usable+=int(0<=x<image.shape[1] and 0<=y<image.shape[0] and np.isfinite(image[y,x]))
            responses=np.asarray(responses)
            typical_peak=float(np.median(np.max(responses,axis=(1,2))))
            if typical_peak<=0:raise ValueError('planned injection has no usable ePSF support')
            for peak_multiplier in [3.,6.,12.,24.,48.]:
                flux=peak_multiplier*float(np.median(sigma))/typical_peak
                injected=add_projected_injection(stack.images,responses,flux)
                # Preparation recenters each projected epoch; reproduce that after addition.
                for image in injected:image-=np.nanmedian(image)
                tracks,scores,detection=detect(injected,stack.times,ranker)
                sky=stack.grid.pixel_to_world_values(positions[:,0],positions[:,1])
                trials.append(dict(trajectory_id=f'speed{speed:g}-direction{direction_index}',
                                   speed_px_per_hour=speed,speed_arcsec_per_hour=speed*stack.pixel_scale,
                                   origin_xy=origin.tolist(),velocity_xy_per_hour=velocity.tolist(),
                                   expected_xy=positions.tolist(),expected_icrs_deg=np.column_stack(sky).tolist(),
                                   peak_multiplier_of_registered_background_mad=peak_multiplier,
                                   constant_injected_flux_in_image_pixel_sum_units=flux,
                                   actual_peak_to_background_mad=(flux*np.max(responses,axis=(1,2))/sigma).tolist(),
                                   usable_center_epochs=center_usable,epsf=epsf,detection=detection,
                                   control_match_before_injection=injection_recovery(control_tracks,control_scores,positions,top_k)['recovered_before_ranking'],
                                   recovery=injection_recovery(tracks,scores,positions,top_k)))
            print(f'speed {speed:g}, direction {direction_index}: {len(trials)} injections, {time.monotonic()-started:.1f}s',flush=True)
    assert load_ranker().metadata['sha256']==original_hash
    report=dict(schema_version=1,model_sha256=original_hash,model_fitted_or_changed=False,
                independent_parent_fields=1,parent_exposures=4,derivative_trials_are_correlated=True,
                input_sources=source_rows,registered_shape=list(stack.images.shape),frames=stack.frames,
                times_hours=stack.times.tolist(),pixel_scale_arcsec=stack.pixel_scale,
                finite_fraction_per_epoch=np.isfinite(stack.images).mean(axis=(1,2)).tolist(),
                source_region=request['source']['region'],detector_settings=SETTINGS,mask_policy='motion',
                seed=932711,source_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                method='registered-real-background injection of local native EPSF pixel samples projected with native WCS, bilinear interpolation and production masks',
                limitations=['one real field, not 150 independent fields','fixed flux density across variable local passbands',
                             'no added photon noise or variance update','source added after real registration; no raw detector forward simulation',
                             'native EPSF is pixel-convolved; no additional pixel convolution applied',
                             'clustered early cadence and long gap cause blending/self-subtraction or source leaving field',
                             'unmatched real tracks remain unlabeled; no precision or false-positive metrics'],
                warnings=stack.warnings,background_robust_sigma=sigma,unmodified_control=control,
                summary=summarize(trials,top_k),by_peak_multiplier={},by_speed={},trials=trials,
                elapsed_seconds=time.monotonic()-started,
                references=['https://caltech-ipac.github.io/irsa-tutorials/spherex-psf/',
                            'https://docs.astropy.org/en/stable/wcs/'])
    for peak in [3.,6.,12.,24.,48.]:
        report['by_peak_multiplier'][str(peak)]=summarize([t for t in trials if t['peak_multiplier_of_registered_background_mad']==peak],top_k)
    for speed in [1.,4.,10.,25.,50.]:
        report['by_speed'][str(speed)]=summarize([t for t in trials if t['speed_px_per_hour']==speed],top_k)
    Path(output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(report['summary'],indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir',required=True)
    parser.add_argument('--output',default=str(Path(__file__).resolve().parents[1]/'models'/'real-background-evaluation.json'))
    args=parser.parse_args();run(args.input_dir,args.output)


if __name__=='__main__':main()
