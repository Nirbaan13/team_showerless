"""All-model paired DEV uncertainty and physical/native strata; no selection."""
from pathlib import Path
import argparse,json,sys
import numpy as np
from datasets import BASE,sha,read_cache,native_moving_validation
from validate_frontier import atomic_json,field_split
from code_binding import verify_module


def recover(fields,values,k,masks=None):
    result=[]
    for i,(field,score)in enumerate(zip(fields,field_split(values,fields))):
        order=np.argsort(-score,kind='stable')[:k];matches=np.asarray(field['matches'],int)
        if masks is not None:result.append(int(np.any(masks[i][order])))
        else:result.append(len({int(v)for v in matches[order]if v>=0}))
    return np.asarray(result,int)


def native_geometry(fields):
    finite=[];capable=[];resolved=[]
    for field in fields:
        expected=np.asarray(field['expected_xy'],float);covered=np.asarray(field['center_usable_flags'],bool)&np.isfinite(expected).all(axis=1);path=expected[covered];span=float(np.max(np.linalg.norm(path[:,None]-path[None,:],axis=-1)))if len(path)else 0.
        finite.append(covered.sum()>=3);capable.append(covered.sum()>=3 and span>=3);mask=np.zeros(len(field['matches']),bool)
        for geometry in field['matched_geometry']:
            index=int(geometry['candidate_index'])
            if field['matches'][index]<0:continue
            epochs=np.asarray(geometry['epochs'],int);epochs=epochs[covered[epochs]];p=expected[epochs]
            if len(epochs)>=3 and np.max(np.linalg.norm(p[:,None]-p[None,:],axis=-1))>=3:mask[index]=True
        resolved.append(mask)
    return np.asarray(finite,bool),np.asarray(capable,bool),resolved


def main(args):
    source=Path(args.frontier);outcomes=json.loads((source/'all-outcomes.json').read_text());assert outcomes['complete']and len(outcomes['experiments'])==36
    checks=verify_module(sys.modules[__name__]);root=Path('/tmp/spaceapps-v4-native-cache/main-v2');native=[]
    for i in range(1,9):_,rows=read_cache(root/f'v4-validation{i:02d}-both.json.gz','validation');native.extend(rows)
    native=native_moving_validation(native);_,synthetic=read_cache('/tmp/spaceapps-v4-ranker/synthetic-validation-30-v1.json.gz','validation')
    for f in native+synthetic:
        for key in ['features_v4','features','candidate_ids','baseline','times_hours']:f.pop(key,None)
    base_native=np.concatenate([f['scores_c13']for f in native]);base_synthetic=np.concatenate([f['scores_c13']for f in synthetic]);parents=sorted({f['parent_id']for f in native});parent=np.asarray([f['parent_id']for f in native]);common=np.asarray([f['attribution_eligible']for f in native],bool);finite,capable,resolved=native_geometry(native)
    truth=np.asarray([f['truth_count']for f in synthetic]);truth_fields=truth>0;cadence=np.asarray([f['metadata']['cadence_family']for f in synthetic]);rng=np.random.default_rng(20261115);parent_draws=rng.integers(len(parents),size=(10000,len(parents)));field_draws=rng.integers(len(synthetic),size=(10000,len(synthetic)),dtype=np.int32);cadence_draws={}
    for c in range(4):indices=np.flatnonzero(cadence==c);cadence_draws[c]=indices[rng.integers(len(indices),size=(10000,len(indices)),dtype=np.int32)]
    base_counts_n={k:recover(native,base_native,k)for k in [1,3]};base_counts_s={k:recover(synthetic,base_synthetic,k)for k in [1,3]};base_resolved={k:recover(native,base_native,k,resolved)for k in [1,3]}
    assert [int(base_counts_n[k].sum())for k in [1,3]]==[309,347]
    assert [int(base_counts_s[k].sum())for k in [1,3]]==[249,451]
    results=[]
    for record in outcomes['experiments']:
        if record.get('error'):results.append(dict(id=record['id'],error=record['error']));continue
        npath=Path(record['scores']['native_onnx']['path']);spath=Path(record['scores']['synthetic_onnx']['path']);assert sha(npath)==record['scores']['native_onnx']['sha256']and sha(spath)==record['scores']['synthetic_onnx']['sha256'];nscore=np.load(npath,allow_pickle=False);sscore=np.load(spath,allow_pickle=False)
        item=dict(id=record['id'],config=record['config'],native={},synthetic={},strata={})
        for k in [1,3]:
            counts=recover(native,nscore,k);scounts=recover(synthetic,sscore,k);rcounts=recover(native,nscore,k,resolved)
            assert counts.sum()==record['onnx_development']['native']['all_planned']['top'+str(k)]and scounts.sum()==record['onnx_development']['synthetic']['all_planned']['top'+str(k)]
            for cohort,mask,cand,base in [('all_planned',np.ones(len(native),bool),counts,base_counts_n[k]),('common_attributable',common,counts,base_counts_n[k]),('finite_center_ge3',common&finite,counts,base_counts_n[k]),('geometrically_capable_resolved_detection',common&capable,rcounts,base_resolved[k])]:
                delta=[];by_parent={}
                for p in parents:
                    selected=(parent==p)&mask;den=int(selected.sum());a=int(cand[selected].sum());b=int(base[selected].sum());d=(a-b)/den if den else 0.;delta.append(d);by_parent[p]=dict(denominator=den,baseline=b,candidate=a,delta=d)
                delta=np.asarray(delta);boot=delta[parent_draws].mean(axis=1);item['native'].setdefault(cohort,{})['K'+str(k)]=dict(macro_parent_delta=float(delta.mean()),ci95=np.quantile(boot,[.025,.975]).tolist(),per_parent=by_parent)
            delta=scounts-base_counts_s[k];field_delta=np.divide(delta,truth,out=np.zeros(len(truth),float),where=truth_fields);field_boot=field_delta[field_draws].sum(axis=1)/truth_fields[field_draws].sum(axis=1);cadence_boot=np.mean([delta[draw].sum(axis=1)/truth[draw].sum(axis=1)for draw in cadence_draws.values()],axis=0)
            item['synthetic']['K'+str(k)]=dict(macro_field_delta=float(field_delta[truth_fields].mean()),macro_field_ci95=np.quantile(field_boot,[.025,.975]).tolist(),macro_cadence_delta=float(np.mean([delta[cadence==c].sum()/truth[cadence==c].sum()for c in range(4)])),macro_cadence_ci95=np.quantile(cadence_boot,[.025,.975]).tolist())
            for label,key in [('speed_px_hour','speed_px_hour'),('brightness','brightness')]:
                strata={}
                for value in sorted({f[key]for f in native}):
                    chosen=np.asarray([f[key]==value for f in native])&common;strata[str(value)]=dict(denominator=int(chosen.sum()),baseline=int(base_counts_n[k][chosen].sum()),candidate=int(counts[chosen].sum()))
                item['strata'].setdefault(label,{})['K'+str(k)]=strata
        results.append(item)
    payload=dict(schema_version=4,scope=__doc__,outcomes_sha256=sha(source/'all-outcomes.json'),source_check=checks,native_parents=8,native_planned=2160,native_common=int(common.sum()),finite_center_ge3=int((common&finite).sum()),geometrically_capable=int((common&capable).sum()),synthetic_fields=1000,synthetic_truth=int(truth.sum()),bootstrap_samples=10000,bootstrap_seed=20261115,confidence=.95,interpretation='Nominal pairedDEVELOPMENT uncertainty conditionalonreusedselectiondata; notmultiplicityadjusted, notnewFINAL performance. Nativephysicalparents andsyntheticwholefields areunits; derivedinjectionsnotindependent.',resolved_interpretation='Sameindependentgeometricallycapablecohort forbothsystems; recoveryrequires>=3coveredactualmatchedcenters and>=3pxtrue span, primarylabels/denominatorsunchanged',experiments=results,selection_performed=False)
    atomic_json(args.output,payload);print(json.dumps(dict(complete=True,models=len(results),native_parents=8,native_planned=2160,geometry_capable=payload['geometrically_capable'])),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--frontier',default='/tmp/spaceapps-v4-ranker/frontier-onnx-v1');p.add_argument('--output',default='/tmp/spaceapps-v4-ranker/paired-development-v1.json');main(p.parse_args())
