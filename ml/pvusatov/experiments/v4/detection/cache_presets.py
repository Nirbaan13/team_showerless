"""Full fixed-DEV preset pools for prospective eligibility, NEVER fitting labels."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import numpy as np
from ml_inference.prepare import prepare
from ml_inference.detector import find_candidates
from ml_inference.model import load_ranker
from ml_inference.pipeline import _bloom_tracks,select_review_entries
from ml.pvusatov.experiments.v4.detection.features import extract_features,FEATURE_NAMES,FEATURE_VERSION,FEATURE_CONTRACT_SHA256
from ml.pvusatov.experiments.v4.detection.psf_gate import SETTINGS

REPO=Path(__file__).resolve().parents[5];INF=REPO/'ml/pvusatov/backend/inference'


def matches(tracks,expected):
    return [bool(np.all(np.linalg.norm(np.asarray(t.positions_xy)-expected[list(t.epochs)],axis=1)<=1.5))for t in tracks]


def run(output):
    ranker=load_ranker(REPO/'ml/pvusatov/releases/v3/model');pending=[]
    # Complete EVERY candidate pool, feature extraction and C13 prediction first.
    for name in ['comet-d2','comet-d6','vesta-d3','vesta-d6']:
        path=INF/'fixtures'/f'{name}.npz'
        stack=prepare(dict(schema_version=1,analysis_id='v4eligibility-'+name,source=dict(kind='preset',preset_id=name,path=str(path))))
        tracks=find_candidates(stack.images,stack.times,**SETTINGS)
        rich=extract_features(stack.images,stack.times,tracks,psf_sigma=.8,outlier=stack.outlier,bloom=stack.bloom)
        legacy=np.asarray([t.features()for t in tracks],np.float32).reshape(-1,6);scores=ranker.score(legacy)
        bloom,capped=_bloom_tracks(stack.bloom,stack.times,SETTINGS)if stack.bloom is not None else([],False)
        pending.append((name,path,stack,tracks,rich,scores,bloom,capped))
    cases={}
    # Expected coordinates are now evaluation-only; never passed into extraction.
    for name,path,stack,tracks,rich,scores,bloom,capped in pending:
        with np.load(path,allow_pickle=False)as z:expected=np.asarray(z['expected_xy'])
        hit=matches(tracks,expected);bhit=matches(bloom,expected);order=np.argsort(-scores,kind='stable')
        ranks={int(index):i+1 for i,index in enumerate(order)}
        entries=[(tracks[i],int(i)+1,float(scores[i]),False)for i in order]
        entries.extend((track,i+1,None,True)for i,track in enumerate(bloom))
        published=select_review_entries(entries,100,preserve_bloom=True)
        known_bloom_ids={id(t)for t,flag in zip(bloom,bhit)if flag}
        cases[name]=dict(designation='selected DEVELOPMENT eligibility only; never train on these labels',
            object_parent='3I/ATLAS'if name.startswith('comet')else'Vesta',fixture_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            times_hours=stack.times.tolist(),registered_shape=list(stack.images.shape),frames=stack.frames,
            feature_names=rich['feature_names'],feature_version=rich['feature_version'],feature_contract_sha256=rich['feature_contract_sha256'],
            feature_source_sha256=rich['feature_source_sha256'],feature_options={'template_psf_sigma':.8},
            detector_settings=dict(SETTINGS),candidate_ids=rich['candidate_ids'],
            candidate_epochs=[list(t.epochs)for t in tracks],candidate_positions_xy=[list(t.positions_xy)for t in tracks],
            features=[list(map(float,t.features()))for t in tracks],features_v4=rich['features_v4'].tolist(),diagnostics=rich['diagnostics'],
            scores_c13=scores.tolist(),scores=scores.tolist(),matches=[0 if flag else-2 for flag in hit],
            known_target_matches=hit,c13_known_target_ranks=[ranks[i]for i,flag in enumerate(hit)if flag],
            unmatched_identity='UNKNOWN, never negative labels',truth_count=1,
            bloom_tracks=[dict(epochs=list(t.epochs),positions_xy=t.positions_xy,score=None,score_kind='flagged_bloom_evidence',
                method='bloom_track',known_target_match=flag,photometry=False,ml_ranked=False)for t,flag in zip(bloom,bhit)],
            bloom_peak_cap_reached=capped,c13_published_count=len(published),c13_published_bloom_retained=sum(e[3]for e in published),
            c13_known_bloom_target_published=any(e[3]and id(e[0])in known_bloom_ids for e in published),
            existing_output_policy='first3 residual protected; reserve BLOOM slots; at most100 published entries')
    sources=[Path(__file__),Path(__file__).with_name('features.py'),Path(__file__).with_name('psf_gate.py'),
             *[INF/'ml_inference'/f'{name}.py'for name in ['detector','prepare','model','pipeline','contracts']]]
    payload=dict(schema_version=1,scope='development-presets-eligibility-only',fitting_forbidden=True,
        feature_names=list(FEATURE_NAMES),feature_version=FEATURE_VERSION,feature_contract_sha256=FEATURE_CONTRACT_SHA256,
        source_sha256={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest()for p in sources},
        baseline_model=dict(ranker.metadata),model_artifact_sha256=ranker.metadata['sha256'],
        independent_known_objects=2,eligibility=dict(comet_d2_rank_max=1,comet_d6_rank_max=4,comet_d6_preferred_rank_max=3,
                                                   vesta_bloom_retained=True,unscored_bloom_required=True),cases=cases)
    output=Path(output)
    if output.exists():raise ValueError('refusing to overwrite fixed preset cache')
    output.parent.mkdir(parents=True,exist_ok=True);tmp=output.with_suffix('.tmp');tmp.write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n');tmp.replace(output)
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        cases={n:dict(rows=len(c['features_v4']),target_ranks=c['c13_known_target_ranks'],bloom_target=c['c13_known_bloom_target_published'])for n,c in cases.items()})),flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();run(a.output)
