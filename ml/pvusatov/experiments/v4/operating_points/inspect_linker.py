"""Post-hoc DEV failure diagnosis; trace unchanged linker, no parameter selection."""
from pathlib import Path
import gzip
import inspect
import json
import sys
import numpy as np
from ml_inference import detector
from ml_inference.prepare import prepare
from training.evaluate_background import read_native,project_response,add_projected_injection
from .study import HERE,digest,image_hash,atomic,label_tracks


def main():
    protocol=json.loads((HERE/'protocol.json').read_text());report=json.loads((HERE/'results/summary.json').read_text())
    chosen=next(e for e in report['fields']if e['field']['kind']=='native' and e['field']['parent_id']=='v4-train01'
        and e['field']['speed_px_hour']==1. and e['field']['direction_id']==0 and e['field']['brightness']==3.)
    with gzip.open(chosen['path'],'rt')as stream:field=json.load(stream)
    info=protocol['native']['v4-train01']
    for row in info['input_sources']:
        if digest(row['path'])!=row['sha256']:raise ValueError('TRAIN bytes differ')
    ra,dec=info['center_deg'];stack=prepare(dict(schema_version=1,analysis_id='operating-link-diagnosis',
        source=dict(kind='fits',observations=info['input_sources'],region=dict(right_ascension_deg=ra,declination_deg=dec,width_arcmin=6.,height_arcmin=6.)),options=info['preparation_options']))
    lookup={r['frame_id']:r for r in info['input_sources']};natives=[read_native(lookup[f['frame_id']]['path'],stack.grid,stack.images.shape[1:])for f in stack.frames]
    truth=np.asarray(field['expected_xy'][0]);response=np.asarray([project_response(n,stack.grid,p)[0]for n,p in zip(natives,truth)])
    images=add_projected_injection(stack.images,response,field['injected_flux'])
    for image in images:image-=np.nanmedian(image)
    if image_hash(images)!=field['image_sha256']:raise ValueError('replayed latent images differ')
    residuals=detector.difference_frames(images,leave_one_out=True);outputs={};peak_sets={}
    filename=detector.link_detections.__code__.co_filename
    target_line=next(i for i,line in enumerate(Path(filename).read_text().splitlines(),1)if line.strip().startswith('ranked = sorted(tracks'))
    for threshold in (3.,4.):
        peaks=[detector._detect_peaks(d,np.isfinite(d),.8,threshold,100,.8)for d in residuals]
        peak_sets[threshold]=[{tuple(p[:2])for p in epoch}for epoch in peaks];captured={}
        def trace(frame,event,arg):
            if frame.f_code is detector.link_detections.__code__:
                if event=='line' and frame.f_lineno==target_line:
                    captured.update(frame.f_locals['tracks']);sys.settrace(None)
                return trace
            return None
        sys.settrace(trace)
        try:tracks=detector.link_detections(peaks,stack.times,.5,60.,1.4,3)
        finally:sys.settrace(None)
        before=list(captured.values());pre_labels=label_tracks(before,[truth],True);after_labels=label_tracks(tracks,[truth],True)
        ordered=sorted(captured,key=lambda k:detector.baseline_score(captured[k]),reverse=True)
        order_index={id(captured[k]):i for i,k in enumerate(ordered)};keys={id(v):k for k,v in captured.items()}
        pairset=lambda key:{(a,b)for i,a in enumerate(key)for b in key[i+1:]}
        lost=[]
        for candidate,label in zip(before,pre_labels):
            if label<0 or any(candidate is t for t in tracks):continue
            own=pairset(keys[id(candidate)])
            suppressors=[t for t in tracks if order_index[id(t)]<order_index[id(candidate)] and own & pairset(keys[id(t)])]
            lost.append(dict(epochs=list(candidate.epochs),positions_xy=candidate.positions_xy,
                previous_accepted_suppressors=len(suppressors),first_suppressor=None if not suppressors else dict(epochs=list(suppressors[0].epochs),positions_xy=suppressors[0].positions_xy,
                is_matching_injection=label_tracks([suppressors[0]],[truth],True)[0]>=0)))
        outputs[str(threshold)]=dict(peaks_per_epoch=[len(p)for p in peaks],pre_dedup_rows=len(before),pre_dedup_matching_rows=sum(x>=0 for x in pre_labels),
            post_dedup_rows=len(tracks),post_dedup_matching_rows=sum(x>=0 for x in after_labels),suppressed_matching_tracks=lost)
    superset=all(a.issubset(b)for a,b in zip(peak_sets[4.],peak_sets[3.]))
    proof=dict(designation='Post-hoc single DEV case, unchanged detector trace; no model/FINAL calls or parameter choice',
        source_field_cache=chosen['path'],source_field_cache_sha256=chosen['sha256'],image_sha256=field['image_sha256'],
        detector_source_sha256=digest(filename),diagnosis_source_sha256=digest(Path(__file__)),threshold3_peaks_include_every_threshold4_peak=superset,
        profiles=outputs,interpretation='Greedy pair-exclusive linking can suppress an injected match despite a larger uncapped peak set; diagnostics do not alter the detector/default/gates')
    path=HERE/'results/nonmonotonic-linker-case.json';atomic(path,proof);print(json.dumps(dict(path=str(path),sha256=digest(path),superset=superset,profiles=outputs)))


if __name__=='__main__':main()
