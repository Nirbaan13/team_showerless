"""Post-hoc resolution audit; does not change predeclared spatial recovery endpoint."""
import gzip,json,hashlib,argparse
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from ml_inference.prepare import prepare
from ml_inference.detector import find_candidates
from training.evaluate_background import read_native,project_response,add_projected_injection

def one(path):
    with gzip.open(path,'rt')as s:p=json.load(s)
    group=p['parent_id'];folder=Path('/tmp/spaceapps-v3-native-data/development/variants')/(group+'-augmented');paths=[folder/Path(r['path']).name for r in p['input_sources']]
    ra,dec={'validation01':(30.,45.),'validation02':(165.,5.),'validation03':(300.,-20.)}[group]
    for r,q in zip(p['input_sources'],paths):
        if hashlib.sha256(q.read_bytes()).hexdigest()!=r['sha256']:raise ValueError('source mismatch')
    request=dict(schema_version=1,analysis_id='v3-slow-resolution-'+group,source=dict(kind='fits',observations=[dict(path=str(q),frame_id=q.stem,observation_id=q.stem)for q in paths],region=dict(right_ascension_deg=ra,declination_deg=dec,width_arcmin=6,height_arcmin=6)))
    stack=prepare(request);lookup={q.stem:q for q in paths};native=[read_native(lookup[f['frame_id']],stack.grid,stack.images.shape[1:])for f in stack.frames]
    noise=np.array([1.4826*np.median(abs(v-np.median(v)))for image in stack.images for v in [image[np.isfinite(image)]]]);audits=[]
    for index,field in enumerate(p['fields']):
        if not any(m.get('detected',False)for m in field['methods'].values()):continue
        positions=np.asarray(field['expected_xy']);response=np.asarray([project_response(n,stack.grid,xy)[0]for n,xy in zip(native,positions)]);peak=float(np.median(np.max(response,axis=(1,2))));flux=field['brightness']*float(np.median(noise))/peak if peak>0 else 0
        images=add_projected_injection(stack.images,response,flux)
        for image in images:image-=np.nanmedian(image)
        methods={}
        for key,m in field['methods'].items():
            if not m.get('detected',False):continue
            tracks=find_candidates(images,stack.times,**{**p['settings'],'psf_sigma':float(key)});hits=[]
            if len(tracks)!=len(m['scores']):raise ValueError('candidate ordering/count changed')
            ranks={int(i):rank for rank,i in enumerate(np.argsort(-np.asarray(m['scores']),kind='stable'),1)}
            for candidate_index,track in enumerate(tracks):
                expected=positions[list(track.epochs)];xy=np.asarray(track.positions_xy);distance=np.linalg.norm(xy-expected,axis=1)
                if not np.all(distance<=1.5):continue
                es=float(np.max(np.linalg.norm(expected[:,None,:]-expected[None,:,:],axis=-1)));ms=float(np.max(np.linalg.norm(xy[:,None,:]-xy[None,:,:],axis=-1)))
                hits.append(dict(candidate_index=candidate_index,model_rank=ranks[candidate_index],baseline_rank=candidate_index+1,epochs=list(track.epochs),time_span_hours=float(stack.times[track.epochs[-1]]-stack.times[track.epochs[0]]),expected_support_span_px=es,measured_peak_span_px=ms,max_offset_px=float(distance.max()),fitted_speed_px_hour=track.speed_px_per_time,fit_rms_px=track.fit_rms_px,resolution_diagnostic_ge3px=es>=3 and ms>=1.5))
            if not hits:raise ValueError('rerun differs from primary spatial match')
            methods[key]=dict(matches=hits,has_resolution_diagnostic_ge3px=any(h['resolution_diagnostic_ge3px']for h in hits))
        audits.append(dict(primary_field_index=index,speed_px_hour=field['speed_px_hour'],direction_id=field['direction_id'],brightness=field['brightness'],methods=methods))
    result=dict(designation='post-hoc resolution audit, primary spatial endpoints unchanged',parent_id=group,primary_report=str(path),primary_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),resolution_diagnostic='Expected positions span at least3px over matched epochs; measured peaks span at least1.5px; this is an evaluation-only resolution diagnostic, not an independently validated motion declaration',audits=audits)
    output=Path(path).with_name(Path(path).name.replace('.json.gz','-resolution.json.gz'))
    with gzip.open(output,'wt')as s:json.dump(result,s,allow_nan=False)
    return str(output)

def main():
    a=argparse.ArgumentParser();a.add_argument('--report',required=True,action='append');a.add_argument('--workers',type=int,default=2);p=a.parse_args()
    with ProcessPoolExecutor(max_workers=p.workers)as pool:
        for path in pool.map(one,p.report):print(path,flush=True)
if __name__=='__main__':main()
