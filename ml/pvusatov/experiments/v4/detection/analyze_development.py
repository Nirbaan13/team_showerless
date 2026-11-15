"""Selected-DEV failure diagnostics; expected coordinates enter evaluation only."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time
import numpy as np
from ml_inference.detector import find_candidates, baseline_score
from ml_inference.model import load_ranker
from ml_inference.prepare import prepare
from ml_inference.pipeline import _bloom_tracks
from ml.pvusatov.experiments.v4.detection.features import FeatureContext, FEATURE_NAMES, FEATURE_CONTRACT_SHA256

REPO=Path(__file__).resolve().parents[5]
INFERENCE=REPO/'ml/pvusatov/backend/inference'
SETTINGS=dict(min_snr=4.,max_peaks=100,min_speed=.5,max_speed=60.,match_radius=1.4,
              min_epochs=3,min_support=.8,leave_one_out=True)


def duplicates(tracks):
    """Diagnostic only: geometry overlap is not a source identity or rejection."""
    counts=np.zeros(len(tracks),int);pairs=[]
    for i,a in enumerate(tracks):
        left=dict(zip(a.epochs,a.positions_xy))
        for j in range(i+1,len(tracks)):
            right=dict(zip(tracks[j].epochs,tracks[j].positions_xy));common=sorted(left.keys()&right.keys())
            if len(common)>=3 and max(np.linalg.norm(np.asarray(left[e])-right[e])for e in common)<=1.:
                counts[i]+=1;counts[j]+=1;pairs.append([i,j])
    return dict(pairs_with_geometric_overlap=len(pairs),candidates_with_overlap=int(np.sum(counts>0)),
                definition='>=3 common epochs, all measured positions within1px; diagnostic, no candidates removed')


def analyze(name,stack,expected=None):
    c13=load_ranker(REPO/'ml/pvusatov/releases/v3/model');baseline=load_ranker(REPO/'ml/pvusatov/releases/v2/backend/inference/models')
    report=dict(designation='selected development known-object case'if expected is not None else'UNKNOWN real control',
                times_hours=stack.times.tolist(),registered_shape=list(stack.images.shape),profiles={})
    for sigma,ranker in [(1.2,baseline),(.8,c13)]:
        wall=time.perf_counter();cpu=time.process_time();tracks=find_candidates(stack.images,stack.times,psf_sigma=sigma,**SETTINGS)
        detector_wall=time.perf_counter()-wall;detector_cpu=time.process_time()-cpu
        legacy=np.asarray([t.features()for t in tracks]).reshape(-1,6);scores=ranker.score(legacy)
        wall=time.perf_counter();ctx=FeatureContext(stack.images,stack.times,psf_sigma=.8,outlier=stack.outlier,bloom=stack.bloom)
        map_wall=time.perf_counter()-wall;wall=time.perf_counter();rich=ctx.extract(tracks);feature_wall=time.perf_counter()-wall
        order=np.argsort(-scores,kind='stable');ranks={int(i):r+1 for r,i in enumerate(order)}
        target=[]
        if expected is not None:
            for i,t in enumerate(tracks):
                distance=np.linalg.norm(np.asarray(t.positions_xy)-expected[list(t.epochs)],axis=1)
                if np.all(distance<=1.5):target.append(i)
        rows=[]
        for i in sorted(set(order[:10].tolist()+target),key=lambda i:ranks[i]):
            rows.append(dict(candidate_id=rich['candidate_ids'][i],heuristic_rank=i+1,model_rank=ranks[i],
                model_score=float(scores[i]),known_target_match=i in target if expected is not None else None,
                epochs=list(tracks[i].epochs),positions_xy=tracks[i].positions_xy,
                features_v4=rich['features_v4'][i].tolist(),diagnostics=rich['diagnostics'][i]))
        bench_wall=None
        if tracks:
            repeats=(1000+len(tracks)-1)//len(tracks);bench=(tracks*repeats)[:1000]
            wall=time.perf_counter();ctx.extract(bench);bench_wall=time.perf_counter()-wall
        bloom=[]
        if stack.bloom is not None:bloom,_=_bloom_tracks(stack.bloom,stack.times,{**SETTINGS,'psf_sigma':sigma})
        bloom_matches=[]
        if expected is not None:
            bloom_matches=[i for i,t in enumerate(bloom)if np.all(np.linalg.norm(np.asarray(t.positions_xy)-expected[list(t.epochs)],axis=1)<=1.5)]
        report['profiles'][str(sigma)]=dict(candidates=len(tracks),target_ranks=[ranks[i]for i in target],
            bloom_candidates=len(bloom),known_bloom_target_recovered=bool(bloom_matches),bloom_ml_scored=False,
            model_sha256=ranker.metadata['sha256'],detector_wall_seconds=detector_wall,detector_cpu_seconds=detector_cpu,
            feature_map_wall_seconds=map_wall,feature_extract_wall_seconds=feature_wall,feature_extract_1000_wall_seconds=bench_wall,
            rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,geometric_overlap=duplicates(tracks),rows=rows)
        print(json.dumps(dict(case=name,sigma=sigma,candidates=len(tracks),target_ranks=[ranks[i]for i in target],
            detector_wall=detector_wall,feature_map_wall=map_wall,feature_extract_1000_wall=bench_wall)),flush=True)
    return report


def run(output,native_handoff=None):
    result=dict(schema_version=1,feature_names=list(FEATURE_NAMES),feature_contract_sha256=FEATURE_CONTRACT_SHA256,
                feature_source_sha256=hashlib.sha256(Path(__file__).with_name('features.py').read_bytes()).hexdigest(),
                controls_unknown=True,old_final_not_read=True,cases={})
    for name in ['comet-d2','comet-d6','vesta-d3','vesta-d6']:
        path=INFERENCE/'fixtures'/f'{name}.npz'
        stack=prepare(dict(schema_version=1,analysis_id='v4dev-'+name,source=dict(kind='preset',preset_id=name,path=str(path))))
        # Extraction input never receives this separate, evaluation-only truth.
        with np.load(path,allow_pickle=False)as z:expected=np.asarray(z['expected_xy'])
        result['cases'][name]=analyze(name,stack,expected)
    if native_handoff:
        handoff=json.loads(Path(native_handoff).read_text())
        for g in handoff['groups'][:4]:
            if g['split']not in ('train','validation')or any(v in g['directory'].lower()for v in ('quarant','final')):raise ValueError('development inputs only')
            rows=json.loads(Path(g['downloads_manifest']['path']).read_text())
            if hashlib.sha256(Path(g['downloads_manifest']['path']).read_bytes()).hexdigest()!=g['downloads_manifest']['sha256']:raise ValueError('manifest changed')
            observations=[dict(path=r['path'],frame_id=Path(r['path']).stem,sha256=r['sha256'])for r in rows]
            region=dict(right_ascension_deg=g['center_deg'][0],declination_deg=g['center_deg'][1],width_arcmin=6.,height_arcmin=6.)
            stack=prepare(dict(schema_version=1,analysis_id=g['group_id'],source=dict(kind='fits',observations=observations,region=region)))
            result['cases'][g['group_id']]=analyze(g['group_id'],stack)
    p=Path(output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('OUTPUT '+str(p),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--native-handoff');a=p.parse_args();run(a.output,a.native_handoff)
