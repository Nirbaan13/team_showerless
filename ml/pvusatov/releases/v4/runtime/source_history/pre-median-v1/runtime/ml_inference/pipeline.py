"""Prepare, detect, rerank and publish finite review results without training."""
from pathlib import Path
import numpy as np
from scipy.ndimage import center_of_mass, label
from .contracts import InferenceError, validate_request
from .prepare import prepare
from .detector import (difference_frames, filtered_evidence, _detect_peaks,
                       link_detections, find_candidates, baseline_score)
from .model import load_ranker
from .features import extract_features
from .render import stretch, write_png, track_images

ALGORITHM_VERSION='motion-v4-unconfigured'


def select_review_entries(entries,limit,preserve_bloom=False):
    """Protect three residual reviews and keep flagged evidence within one cap.

    BLOOM measurements never receive learned scores. Legacy installations keep
    their original truncation behavior; artifact-bound profiles opt into this
    versioned output policy independently of detector/forest calculations.
    """
    if not preserve_bloom or len(entries)<=limit:
        return entries[:limit]
    residual=[entry for entry in entries if not entry[3]]
    bloom=[entry for entry in entries if entry[3]]
    protected=min(3,len(residual),limit)
    bloom_count=min(len(bloom),limit-protected)
    residual_count=min(len(residual),limit-bloom_count)
    return residual[:residual_count]+bloom[:bloom_count]


def _bloom_tracks(masks,times,settings):
    peaks=[]; capped=False
    for mask in masks:
        components,count=label(mask,structure=np.ones((3,3)))
        areas=np.bincount(components.ravel(),minlength=count+1)
        ids=np.flatnonzero(areas[1:]>=6)+1
        ids=ids[np.argsort(-areas[ids],kind='stable')]
        if len(ids)>settings['max_peaks']: capped=True
        ids=ids[:settings['max_peaks']]
        positions=center_of_mass(mask,components,ids)
        peaks.append(np.asarray([(x,y,areas[i],0) for (y,x),i in zip(positions,ids)]).reshape(-1,4))
    return link_detections(peaks,times,settings['min_speed'],settings['max_speed'],1.4,settings['min_epochs'],subpixel=True),capped


def _record(track,index,baseline_rank,score,stack,*,bloom=False,score_kind=None):
    sky=np.asarray(stack.grid.pixel_to_world_values(*np.asarray(track.positions_xy).T)).T
    detections=[]; warnings=[]
    if bloom: warnings=['saturated_bloom_centroid','not_photometry','not_ml_ranked']
    for epoch,(x,y),(ra,dec),strength in zip(track.epochs,track.positions_xy,sky,track.snr):
        frame=stack.frames[epoch]
        point_warnings=list(warnings)
        if stack.outlier[epoch,int(round(y)),int(round(x))]: point_warnings.append('outlier_flag_at_detection')
        detection=dict(frame_index=epoch,frame_id=frame['frame_id'],observation_id=frame['observation_id'],
                       midpoint_utc=frame['midpoint_utc'],x=float(x),y=float(y),right_ascension_deg=float(ra)%360,
                       declination_deg=float(dec),residual_snr=None if bloom else float(strength),warnings=point_warnings)
        if bloom: detection['bloom_area_px']=int(strength)
        detections.append(detection)
    return dict(id=f'candidate-{index:03d}',rank=index+1,method='bloom_track' if bloom else 'residual_track',
                score=None if bloom else float(score),score_kind='flagged_bloom_evidence' if bloom else score_kind,
                baseline_score=None if bloom else float(baseline_score(track)),baseline_rank=baseline_rank,
                right_ascension_deg=detections[0]['right_ascension_deg'],declination_deg=detections[0]['declination_deg'],
                coordinate_epoch_utc=detections[0]['midpoint_utc'],speed_arcsec_per_hour=float(track.speed_px_per_time*stack.pixel_scale),
                fit_rms_px=float(track.fit_rms_px),detections=detections,warnings=warnings)


def run(request,output,progress=None):
    options=validate_request(request)
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    if progress: progress('preparing')
    # Verify the full artifact/feature/graph contract before any pixel reader.
    try:
        ranker=load_ranker(request.get('model_dir') or '/app/inference/models')
    except (ValueError,OSError,RuntimeError):
        raise InferenceError('model_unavailable','The installed frozen model could not be verified or loaded') from None
    stack=prepare(request)
    settings=dict(min_snr=options['min_snr'],max_peaks=options['max_peaks'],psf_sigma=1.2,
                  min_speed=options['min_speed_arcsec_per_hour']/stack.pixel_scale,
                  max_speed=options['max_speed_arcsec_per_hour']/stack.pixel_scale,match_radius=1.4,
                  min_epochs=options['min_epochs'],min_support=.8)
    if progress: progress('inferencing')
    sigma=ranker.detector_profile['psf_sigma']
    settings['psf_sigma']=sigma
    residuals=difference_frames(stack.images,leave_one_out=True)
    # Only significance is reused. Discard smoothed/support maps each epoch.
    significance=np.stack([filtered_evidence(diff,np.isfinite(diff),sigma,.8)[1] for diff in residuals])
    peaks=[_detect_peaks(diff,np.isfinite(diff),sigma,settings['min_snr'],settings['max_peaks'],.8) for diff in residuals]
    capped=any(len(p)>=settings['max_peaks'] for p in peaks)
    tracks=link_detections(peaks,stack.times,settings['min_speed'],settings['max_speed'],1.4,settings['min_epochs'])
    # Shared-median reference is retained as an explicit classical ablation.
    shared=find_candidates(stack.images,stack.times,**settings,leave_one_out=False)
    bloom_tracks,bloom_capped=_bloom_tracks(stack.bloom,stack.times,settings) if stack.bloom is not None else ([],False)
    try:
        measured=extract_features(stack.images,stack.times,tracks,psf_sigma=.8,
                                  outlier=stack.outlier,bloom=stack.bloom,residuals=residuals)
        features=np.asarray(measured['features_v4'],dtype=np.float32).reshape(-1,30)
        scores=ranker.score(features)
    except (ValueError,RuntimeError):
        raise InferenceError('model_inference_failed','The frozen model could not score the detected tracks') from None
    order=np.argsort(-scores,kind='stable')
    entries=[(tracks[i],int(i)+1,float(scores[i]),False) for i in order]
    entries.extend((track,i+1,None,True) for i,track in enumerate(bloom_tracks))
    warnings=list(stack.warnings)+['experimental_uncalibrated_ranking','short_linear_arc_model','uncalibrated_residual_snr',
                                  'passband_variation_not_corrected','psf_matching_not_applied']
    if capped or bloom_capped: warnings.append('peak_cap_reached_search_incomplete')
    if len(entries)>options['max_candidates']: warnings.append('candidate_cap_reached_search_incomplete')
    bound_profile='detector_profile' in ranker.metadata
    all_bloom=sum(entry[3] for entry in entries)
    entries=select_review_entries(entries,options['max_candidates'],preserve_bloom=bound_profile)
    if bound_profile and sum(entry[3] for entry in entries)<all_bloom:
        warnings.append('flagged_bloom_omitted_by_candidate_limit')
    if not entries: warnings.append('no_candidates_above_thresholds')
    if progress: progress('rendering')
    finite_raw=stack.images[np.isfinite(stack.images)]
    ceiling=max(.1,float(np.percentile(finite_raw,99.9))) if finite_raw.size else .1
    finite_significance=significance[np.isfinite(significance)]
    residual_ceiling=max(6,float(np.percentile(finite_significance,99.9))) if finite_significance.size else 6
    resources=[]; frames=[]; height,width=stack.images.shape[1:]
    for index,frame in enumerate(stack.frames):
        image_name=f'frame-{index:03d}.png'; diff_name=f'difference-{index:03d}.png'
        resources.append(write_png(output,image_name,stretch(stack.images[index],ceiling*.025,ceiling)))
        resources.append(write_png(output,diff_name,stretch(significance[index],2,residual_ceiling)))
        record={**frame,'width':width,'height':height,'image_url':image_name,'difference_url':diff_name,
                'coverage_fraction':float(np.isfinite(stack.images[index]).mean()),
                'outlier_fraction':float(stack.outlier[index].mean())}
        if stack.bloom is not None and stack.bloom[index].any():
            bloom_name=f'bloom-{index:03d}.png'
            resources.append(write_png(output,bloom_name,stretch(stack.bloom[index].astype(float),0,1)))
            record['bloom_url']=bloom_name
        frames.append(record)
    candidates=[]
    for index,(track,baseline_rank,score,is_bloom) in enumerate(entries):
        record=_record(track,index,baseline_rank,score,stack,bloom=is_bloom,score_kind=ranker.metadata['score_kind'])
        moving,stationary=track_images(track,stack.times,stack.bloom.astype(float) if is_bloom else significance,bloom=is_bloom)
        for kind,pixels in [('moving',moving),('stationary',stationary)]:
            name=f'candidate-{index:03d}-{kind}.png'
            resources.append(write_png(output,name,pixels)); record[f'{kind}_stack_url']=name
        candidates.append(record)
    manifest={key:ranker.metadata[key] for key in ('schema_version','model_id','sha256','feature_names','class_labels','positive_class','score_kind')}
    manifest.update({key:ranker.metadata[key] for key in (
        'model_family','detector_profile','algorithm_version_proposal','artifact_format','full_feature_count',
        'feature_version','feature_contract_sha256','feature_source_sha256','feature_options',
        'selected_feature_indices','selected_feature_names','score_description','score_numerics')})
    provenance={**stack.provenance,'grid':dict(projection='TAN',center_deg=stack.grid.wcs.crval.tolist(),
                crpix_fits=stack.grid.wcs.crpix.tolist(),cdelt_deg=stack.grid.wcs.cdelt.tolist(),
                width=width,height=height,coordinate_origin='zero_based_xy')}
    return dict(schema_version=1,analysis_id=request['analysis_id'],algorithm_version=ranker.metadata.get('algorithm_version_proposal',ALGORITHM_VERSION),
                model=manifest,settings={**options,'pixel_scale_arcsec':stack.pixel_scale,'leave_one_out':True,'min_support':.8,
                                         'psf_sigma_px':sigma,'match_radius_px':1.4,'feature_template_psf_sigma_px':.8,
                                         **({'review_policy':'protect_first3_residual_then_flagged_bloom'} if bound_profile else {})},frames=frames,candidates=candidates,
                comparison={'shared_median_count':len(shared),'leave_one_out_count':len(tracks),'bloom_track_count':len(bloom_tracks)},
                warnings=list(dict.fromkeys(warnings)),provenance=provenance,resources=resources)
