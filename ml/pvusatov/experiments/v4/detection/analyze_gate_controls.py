"""DEV-only prelink gate control burden and fixed-object preservation."""
from pathlib import Path
import hashlib
import json
import numpy as np
from ml_inference.prepare import prepare
from ml_inference.model import load_ranker
from ml_inference.pipeline import _bloom_tracks
from ml.pvusatov.experiments.v4.detection.psf_gate import ProposalContext,SETTINGS

REPO=Path(__file__).resolve().parents[5];INF=REPO/'ml/pvusatov/backend/inference'


def run(output):
    ranker=load_ranker(REPO/'ml/pvusatov/releases/v3/model');inputs=[]
    for name in ['comet-d2','comet-d6','vesta-d3','vesta-d6']:
        p=INF/'fixtures'/f'{name}.npz';stack=prepare(dict(schema_version=1,analysis_id='v4gate-'+name,
            source=dict(kind='preset',preset_id=name,path=str(p))))
        inputs.append((name,stack,p))
    handoff=REPO/'ml/pvusatov/experiments/v4/data/development-handoff.json'
    for g in json.loads(handoff.read_text())['groups']:
        if g['split']!='train':continue
        rows=json.loads(Path(g['downloads_manifest']['path']).read_text())
        observations=[dict(path=r['path'],frame_id=Path(r['path']).stem,sha256=r['sha256'])for r in rows]
        if any('final'in r['path'].lower()or'quarant'in r['path'].lower()for r in rows):raise ValueError('development only')
        stack=prepare(dict(schema_version=1,analysis_id=g['group_id'],source=dict(kind='fits',observations=observations,
            region=dict(right_ascension_deg=g['center_deg'][0],declination_deg=g['center_deg'][1],width_arcmin=6,height_arcmin=6))))
        inputs.append((g['group_id'],stack,None))
    cases={}
    for name,stack,fixture in inputs:
        ctx=ProposalContext(stack.images,stack.times);results=[]
        for gate in [None,2.,3.,4.]:
            r=ctx.detect(gate);tracks=r.pop('tracks');x=np.asarray([t.features()for t in tracks],np.float32).reshape(-1,6)
            results.append((gate,r,tracks,ranker.score(x)))
        # Coordinates are consulted after every detector/model call for this case.
        expected=None
        if fixture is not None:
            with np.load(fixture,allow_pickle=False)as z:expected=np.asarray(z['expected_xy'])
        methods={}
        for gate,r,tracks,scores in results:
            order=np.argsort(-scores,kind='stable');ranks={int(i):j+1 for j,i in enumerate(order)}
            target=[]if expected is None else[ranks[i]for i,t in enumerate(tracks)if np.all(np.linalg.norm(np.asarray(t.positions_xy)-expected[list(t.epochs)],axis=1)<=1.5)]
            methods[str(gate)]={**r,'candidate_rows':len(tracks),'known_target_ranks':target}
        bloom,_=_bloom_tracks(stack.bloom,stack.times,SETTINGS)if stack.bloom is not None else([],False)
        cases[name]=dict(control_identity='UNKNOWN'if fixture is None else'selected DEV object; all unmatched tracks UNKNOWN',methods=methods,
            bloom_candidates=len(bloom),bloom_known_target_recovered=bool(expected is not None and any(np.all(np.linalg.norm(np.asarray(t.positions_xy)-expected[list(t.epochs)],axis=1)<=1.5)for t in bloom)),
            bloom_scores_null=True)
        print(json.dumps(dict(case=name,rows={k:v['candidate_rows']for k,v in methods.items()},target={k:v['known_target_ranks']for k,v in methods.items()})),flush=True)
    p=Path(output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(dict(schema_version=1,designation='DEV uniform-patch PSF gate; not selected',
        source_sha256={str(q):hashlib.sha256(q.read_bytes()).hexdigest()for q in [Path(__file__),Path(__file__).with_name('psf_gate.py'),Path(__file__).with_name('features.py')]},
        native_handoff_sha256=hashlib.sha256(handoff.read_bytes()).hexdigest(),cases=cases),indent=2,allow_nan=False)+'\n')


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();run(a.output)
