"""Compact derived-only retention audit; never loads an image or changes policy."""
from pathlib import Path
import gzip,json
import numpy as np
from ml.pvusatov.experiments.v4.operating_points.study import atomic,digest
HERE=Path(__file__).resolve().parent


def pack():
    run=json.loads((HERE/'results/run.json').read_text());records=[];resolved={};examples={}
    for entry in run['entries']:
        if digest(entry['path'])!=entry['sha256']:raise ValueError('raw derived field changed')
        with gzip.open(entry['path'],'rt')as stream:row=json.load(stream)
        if 'task_error'in row:records.append(dict(task_error=row['task_error'],identity=entry['field']));continue
        profiles={}
        for t,p in row['profiles'].items():
            union=set(i for name,q in p['policies'].items()if name!='near_duplicate'for i in q['indices'])
            for m,scores in p['scores'].items():
                ids=p['policies']['near_duplicate']['indices'];order=np.argsort(-np.asarray(scores)[ids],kind='stable')[:3];union.update(ids[int(j)]for j in order)
            union=sorted(union|{i for i,label in enumerate(p['matches'])if label>=0})
            profiles[t]=dict(hypotheses=p['hypotheses'],retained_union_or_evaluation_matched_indices=union,
                candidates=[dict(pool_index=i,candidate_id=p['candidate_ids'][i],epochs=p['candidate_epochs'][i],xy=p['candidate_positions_xy'][i],features_v4=p['features_v4'][i],scores={m:s[i]for m,s in p['scores'].items()},offline_match=p['matches'][i])for i in union],
                policies={name:dict(indices=q['indices'],error=q['error'],accounting=q['accounting'],models=q['models'],attribution_eligible=q['attribution_eligible'])for name,q in p['policies'].items()})
            for name,q in p['policies'].items():
                key=(row['kind'],t,name);resolved.setdefault(key,dict(resolved_C596_top3=0,unresolved_C596_top3=0))
                ids=q['indices'];order=np.argsort(-np.asarray(p['scores']['C596'])[ids],kind='stable')[:3];found={}
                for orderid in order:
                    i=ids[int(orderid)];label=p['matches'][i]
                    if label<0:continue
                    xy=np.asarray(row['expected_xy'][label])[p['candidate_epochs'][i]];span=float(np.max(np.linalg.norm(xy[:,None]-xy[None,:],axis=2)))
                    found[label]=max(found.get(label,0.),span)
                resolved[key]['resolved_C596_top3']+=sum(v>=3 for v in found.values());resolved[key]['unresolved_C596_top3']+=sum(v<3 for v in found.values())
                delta=q['models']['C596']['top3']-p['policies']['legacy']['models']['C596']['top3']
                ekey=f'{row["kind"]}/{t}/{name}/{"gain"if delta>0 else "loss"}'
                if name!='legacy'and delta and len(examples.setdefault(ekey,[]))<2:
                    positives=[i for i,x in enumerate(p['matches'])if x>=0];details=[]
                    for i in positives[:3]:
                        target=set(zip(p['candidate_epochs'][i],map(tuple,p['candidate_positions_xy'][i])));blockers=[]
                        for j in p['policies']['legacy']['indices']:
                            if j==i:continue
                            common=target&set(zip(p['candidate_epochs'][j],map(tuple,p['candidate_positions_xy'][j])))
                            if len(common)>=2:blockers.append(dict(pool_index=j,shared_measured_points=len(common),offline_match=p['matches'][j],C596_score=p['scores']['C596'][j]))
                        details.append(dict(pool_index=i,C596_score=p['scores']['C596'][i],epochs=p['candidate_epochs'][i],xy=p['candidate_positions_xy'][i],legacy_shared_pair_blockers=blockers[:4]))
                    examples[ekey].append(dict(case_id=row['case_id'],image_sha256=row['image_sha256'],full_raw_sha256=entry['sha256'],delta_top3=delta,legacy_top3=p['policies']['legacy']['models']['C596']['top3'],policy_top3=q['models']['C596']['top3'],matched_hypothesis_examples=details))
        records.append(dict(case_id=row['case_id'],kind=row['kind'],parent_id=row['parent_id'],seed=row['seed'],image_sha256=row['image_sha256'],finite_mask_sha256=row['finite_mask_sha256'],full_raw_sha256=entry['sha256'],profiles=profiles))
    path=HERE/'results/retained-features.json.gz';atomic(path,dict(protocol_sha256=run['protocol_sha256'],record_count=len(records),scope='Derived all legacy/learned retained rows + top3 C13/C596 diversity rows + offline matched hypotheses. Remaining diversity/unretained unmatched rows are omitted and remain in SHA-bound scratch full caches. No pixels/weights. Not a training dataset.',records=records))
    atomic(HERE/'results/retention-audit.json',dict(protocol_sha256=run['protocol_sha256'],archive_sha256=digest(path),archive_bytes=path.stat().st_size,source_sha256=digest(__file__),actual_matched_epoch_span_diagnostic=[dict(kind=k[0],min_snr=k[1],policy=k[2],**v)for k,v in resolved.items()],illustrative_cases=examples))
    print('ARCHIVE',path.stat().st_size,digest(path))
if __name__=='__main__':pack()
