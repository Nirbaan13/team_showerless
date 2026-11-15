"""Paired old-DEVELOPMENT uncertainty; explicitly not selection-adjusted evidence."""
from pathlib import Path
import gzip,json,hashlib
import numpy as np
import joblib


def main():
    scratch=Path('/tmp/spaceapps-v4-ranker/stage1-six');report=json.loads((scratch/'report.json').read_text());manifest=json.loads((scratch/'inputs.json').read_text());baseline=report['baseline'];parents=sorted(baseline['native']['by_parent']);rng=np.random.default_rng(20261115);sample=rng.integers(len(parents),size=(10000,len(parents)))
    with gzip.open(manifest['inputs']['synthetic_validation'][0],'rt')as f:fields=json.load(f)['fields']
    x=np.asarray([row for f in fields for row in f['features']],np.float32).reshape(-1,6)
    import sys
    base=Path(__file__).resolve().parents[3];sys.path.insert(0,str(base/'backend/inference'))
    from ml_inference.model import load_ranker
    c13=load_ranker(base/'releases/v3/model');scores=c13.score(x)
    cuts=np.cumsum([0]+[len(f['matches'])for f in fields]);truth=np.asarray([f['truth_count']for f in fields]);cadence=np.asarray([f['metadata']['cadence_family']for f in fields])
    def counts(values,k):
        return np.asarray([len({int(v)for v in np.asarray(f['matches'])[np.argsort(-values[cuts[i]:cuts[i+1]],kind='stable')[:k]]if v>=0}) for i,f in enumerate(fields)])
    base_counts={k:counts(scores,k)for k in [1,3]};draws={}
    for c in range(4):
        indices=np.flatnonzero(cadence==c);draws[c]=indices[rng.integers(len(indices),size=(10000,len(indices)))]
    results=[]
    for experiment in report['experiments']:
        entry=dict(config=experiment['config'],id=experiment['id'],native={},synthetic={})
        for k in [1,3]:
            delta=np.asarray([experiment['validation']['native']['by_parent'][parent]['recall'+str(k)]-baseline['native']['by_parent'][parent]['recall'+str(k)]for parent in parents]);boot=delta[sample].mean(axis=1)
            entry['native']['K'+str(k)]=dict(macro_parent_delta=float(delta.mean()),ci95=np.quantile(boot,[.025,.975]).tolist(),per_parent_delta=dict(zip(parents,delta.tolist())))
        if experiment['config']['kind']=='forest':
            estimator=joblib.load(experiment['estimator']['path']);indices=list(range(1,6))if experiment['config']['drop_epoch']else list(range(6));actual=estimator.predict_proba(x[:,indices])[:,1]
            for k in [1,3]:
                recovered=counts(actual,k);boot=np.mean([((recovered[draws[c]].sum(axis=1)-base_counts[k][draws[c]].sum(axis=1))/truth[draws[c]].sum(axis=1))for c in range(4)],axis=0)
                point=float(np.mean([(recovered[cadence==c].sum()-base_counts[k][cadence==c].sum())/truth[cadence==c].sum()for c in range(4)]))
                entry['synthetic']['K'+str(k)]=dict(macro_cadence_delta=point,whole_field_stratified_ci95=np.quantile(boot,[.025,.975]).tolist())
        results.append(entry)
    output=dict(scope='Old reused DEVELOPMENT only; model-selection reuse and multiple ablations invalidate fresh independent-performance interpretation of nominal intervals.',native_unit='11physicalparentfields, everybrightness/trajectory grouped',synthetic_unit='800independentwholefields stratifiedby4cadencefamilies; noiseonlyfieldsretained',bootstrap_samples=10000,seed=20261115,stage1_inputs_sha256=hashlib.sha256((scratch/'inputs.json').read_bytes()).hexdigest(),stage1_outcomes_sha256=hashlib.sha256((scratch/'report.json').read_bytes()).hexdigest(),experiments=results)
    path=Path('/tmp/spaceapps-v4-ranker/old-development-uncertainty.json');path.write_text(json.dumps(output,indent=2)+'\n')
    for e in results:
        if e['config']==dict(kind='forest',weight='group',mass=2,drop_epoch=False):print(json.dumps(e),flush=True)

if __name__=='__main__':main()
