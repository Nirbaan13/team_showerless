"""Offline v2 training with physical ePSF/cadence/amplitude coverage and grouped fields."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

import numpy as np
import onnx
import onnxruntime
import scipy
import sklearn
import skl2onnx
from sklearn.ensemble import RandomForestClassifier
from skl2onnx import to_onnx

from ml_inference.detector import baseline_score,find_candidates,difference_frames,_detect_peaks
from ml_inference.model import FEATURE_NAMES,SCORE_KIND,load_ranker
from training.simulate_v2 import simulate,load_bank
from training.train import evaluate,feature_matrix,write_json,sha
from training.evaluate_background import SETTINGS
from training.weights import epoch_stratum_weights,weight_metadata


def split_seeds(train,validation,test,test_start=500000):
    if min(train,validation,test)<1 or max(train,validation,test)>100000:
        raise ValueError('partition counts must be in [1,100000]')
    partitions=dict(train=list(range(10000,10000+train)),
                    validation=list(range(300000,300000+validation)),test=list(range(test_start,test_start+test)))
    combined=[seed for rows in partitions.values()for seed in rows]
    if len(set(combined))!=len(combined):raise ValueError('field-group partitions overlap')
    return partitions


def field(seed,bank,*,extended=False,varying_psf=False):
    images,times,truth,mode,details=simulate(seed,bank,extended=extended,varying_psf=varying_psf)
    tracks=find_candidates(images,times,**SETTINGS)
    matches=[]
    for track in tracks:
        positions=np.asarray(track.positions_xy)
        distances=[np.linalg.norm(positions-path[list(track.epochs)],axis=1)for path in truth]
        ids=[i for i,d in enumerate(distances)if np.all(d<=1.5)]
        matches.append(min(ids,key=lambda i:distances[i].mean())if ids else-1)
    peaks=[len(_detect_peaks(d,np.isfinite(d),1.2,4,100,.8))for d in difference_frames(images,True)]
    return dict(seed=seed,mode=mode,features=[list(map(float,t.features()))for t in tracks],matches=matches,
                truth_count=len(truth),baseline=[float(baseline_score(t))for t in tracks],
                times_hours=times.tolist(),metadata=details,peaks_per_epoch=peaks,peak_cap_reached=any(p>=100 for p in peaks))


def ranking_report(fields,score):
    return dict(top1=evaluate(fields,score,1),top3=evaluate(fields,score,3))


def selection_key(fields,score):
    keys=[]
    for k in [1,3]:
        recall=[]
        for family in range(4):
            subset=[f for f in fields if f['metadata']['cadence_family']==family]
            metrics=evaluate(subset,score,k)
            if metrics['top_k_recall']is not None:recall.append(metrics['top_k_recall'])
        keys.append(float(np.mean(recall)))
    keys.append(evaluate(fields,score,3)['track_average_precision']or 0)
    return tuple(keys)


def fit_selected(train,validation,epoch_balanced=False):
    x,y=feature_matrix(train)
    if len(set(y))!=2:raise ValueError('both simulated classes required')
    weights=epoch_stratum_weights(x,y)if epoch_balanced else None
    experiments=[];best=None
    for features in [1.,'sqrt']:
        for leaf,depth in [(4,12),(12,16),(24,None)]:
            params=dict(n_estimators=150,min_samples_leaf=leaf,max_depth=depth,max_features=features,
                        class_weight='balanced',random_state=42,n_jobs=1)
            started=time.monotonic();forest=RandomForestClassifier(**params).fit(x,y,sample_weight=weights)
            score=lambda f:forest.predict_proba(np.asarray(f['features'],np.float32))[:,1]
            key=selection_key(validation,score)
            record=dict(parameters=params,selection_key=list(key),validation=ranking_report(validation,score))
            experiments.append(record)
            print(f'forest {params}: key {key}, fit/eval {time.monotonic()-started:.1f}s',flush=True)
            if best is None or key>best[0]:best=key,forest
    return best[1],experiments


def nuisance_summary(fields):
    true_flux=[v for f in fields for v in f['metadata']['positive_fluxes']]
    artifact_flux=[v for f in fields for v in f['metadata']['artifact_fluxes']]
    x,y=feature_matrix(fields)
    return dict(physical_flux_distribution_policy='common log-uniform integrated flux 6..600 times epoch noise scale; independent of source/artifact truth label',
                positive_flux_quantiles=np.quantile(true_flux,[0,.1,.5,.9,1]).tolist()if true_flux else[],
                artifact_flux_quantiles=np.quantile(artifact_flux,[0,.1,.5,.9,1]).tolist()if artifact_flux else[],
                positive_feature_quantiles=np.quantile(x[y==1],[0,.1,.5,.9,1],axis=0).tolist()if np.any(y==1)else[],
                negative_feature_quantiles=np.quantile(x[y==0],[0,.1,.5,.9,1],axis=0).tolist()if np.any(y==0)else[],
                field_epoch_counts={str(n):sum(len(f['times_hours'])==n for f in fields)for n in range(3,9)},
                cadence_family_counts={str(n):sum(f['metadata']['cadence_family']==n for f in fields)for n in range(4)},
                peak_cap_fields=sum(f['peak_cap_reached']for f in fields))


def run(args):
    started=time.monotonic();output=Path(args.output_dir);output.mkdir(parents=True,exist_ok=True)
    bank=load_bank(args.calibration_bank)
    seeds=split_seeds(args.train_fields,args.validation_fields,args.test_fields,args.test_start)
    fields={}
    for partition,values in seeds.items():
        fields[partition]=[]
        for i,seed in enumerate(values):
            fields[partition].append(field(seed,bank,extended=args.extended_backgrounds and seed%3==0,varying_psf=args.varying_psf))
            if i%50==0:print(f'{partition} {i+1}/{len(values)} elapsed {time.monotonic()-started:.1f}s',flush=True)
    forest,experiments=fit_selected(fields['train'],fields['validation'],args.epoch_balanced)
    x,y=feature_matrix(fields['train'])
    graph=to_onnx(forest,x[:1],options={id(forest):{'zipmap':False}},target_opset=17)
    onnx.helper.set_model_props(graph,dict(schema_version='1',feature_names=json.dumps(list(FEATURE_NAMES)),
                                         class_labels='[0, 1]',score_kind=SCORE_KIND))
    onnx.checker.check_model(graph);(output/'ranker.onnx').write_bytes(graph.SerializeToString())
    base=Path(__file__).resolve().parent
    sources=[base/'train_v2.py',base/'simulate_v2.py',base/'prepare_calibration.py',base/'train.py',
             base/'evaluate_background.py',base/'weights.py',base/'evaluate_synthetic.py',base.parent/'ml_inference'/'detector.py']
    manifest=dict(schema_version=1,model_generation=2,partitions=seeds,
                  partition_group='whole independent synthetic field, never candidate rows',
                  actual_observation_pixels_used_in_fit=False,
                  design_development_evidence='M101 v1 failure informed generator design; M101 is development only for v2',
                  final_real_field_opened=False,base_source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                  source_sha256={str(p.relative_to(base.parent)):sha(p)for p in sources},
                  calibration_bank_sha256=sha(Path(args.calibration_bank)),calibration_provenance=bank['provenance'],
                  detector_settings=SETTINGS,feature_names=list(FEATURE_NAMES),match_tolerance_px=1.5,
                  training_candidates=len(x),training_positive_candidates=int(y.sum()),
                  versions=dict(python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,
                                sklearn=sklearn.__version__,skl2onnx=skl2onnx.__version__,onnx=onnx.__version__,onnxruntime=onnxruntime.__version__),
                  selection_rule='validation macro cadence-family top1 recall, then macro top3 recall, then candidate AP',
                  validation_experiments=experiments,selected_parameters=forest.get_params(),refit_validation=False,
                  nuisance_summaries={name:nuisance_summary(rows)for name,rows in fields.items()},
                  evaluation_designation=args.designation,
                  generator_configuration=dict(extended_backgrounds=args.extended_backgrounds,extended_every_nth_field=3,
                                               varying_psf=args.varying_psf),
                  sample_weighting=weight_metadata(x,y,epoch_stratum_weights(x,y))if args.epoch_balanced else dict(method='balanced classes only'),
                  used_features=[FEATURE_NAMES[i]for i,v in enumerate(forest.feature_importances_)if v>0],
                  impurity_feature_importances=dict(zip(FEATURE_NAMES,map(float,forest.feature_importances_))))
    write_json(output/'training-manifest.json',manifest)
    metadata=dict(schema_version=1,model_id='spherex-track-rf-v2',sha256=sha(output/'ranker.onnx'),
                  feature_names=list(FEATURE_NAMES),class_labels=[0,1],positive_class=1,score_kind=SCORE_KIND,
                  status='experimental',score_description='Mean class-1 weighted leaf fraction across trees; not calibrated planet probability',
                  training_manifest_sha256=sha(output/'training-manifest.json'))
    write_json(output/'metadata.json',metadata);ranker=load_ranker(output)
    test_x,_=feature_matrix(fields['test']);rng=np.random.default_rng(8127)
    probes=np.vstack([x[:64],test_x[:1024],rng.uniform(0,300,(256,6))]).astype(np.float32)
    reference=forest.predict_proba(probes)[:,1];actual=ranker.score(probes)
    np.testing.assert_allclose(actual,reference,rtol=2e-6,atol=2e-6)
    write_json(output/'parity-reference.json',dict(features=probes.tolist(),scores=reference.tolist(),
                                                 max_abs_error=float(np.max(abs(reference-actual)))))
    report=dict(schema_version=1,model_sha256=metadata['sha256'],designation=args.designation,
                training_manifest_sha256=metadata['training_manifest_sha256'],partitions={},
                elapsed_seconds=time.monotonic()-started,parity_max_abs_error=float(np.max(abs(reference-actual))))
    for name in ['validation','test']:
        report['partitions'][name]={}
        groups={'all':fields[name]}
        groups.update({mode:[f for f in fields[name]if f['mode']==mode]for mode in ['noise_only','artifacts_only','injected']})
        groups.update({f'cadence{family}':[f for f in fields[name]if f['metadata']['cadence_family']==family]for family in range(4)})
        groups.update({f'epochs{n}':[f for f in fields[name]if len(f['times_hours'])==n]for n in range(3,9)})
        groups.update({f'detector{n}':[f for f in fields[name]if f['metadata'].get('detector')==n]for n in range(1,7)})
        for group,rows in groups.items():
            if not rows:continue
            report['partitions'][name][group]=dict(
                baseline=ranking_report(rows,lambda f:np.asarray(f['baseline'])),
                random_forest=ranking_report(rows,lambda f:ranker.score(np.asarray(f['features'],np.float32))))
    write_json(output/'evaluation.json',report);write_json(output/'field-candidates.json',fields)
    print(json.dumps(report['partitions']['test']['all'],indent=2),flush=True)
    print(f'OUTPUT {output} SHA256 {metadata["sha256"]}',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--calibration-bank',default=str(Path(__file__).resolve().parent/'calibration'/'instrument-epsf-bank.npz'))
    parser.add_argument('--train-fields',type=int,default=1500)
    parser.add_argument('--validation-fields',type=int,default=400)
    parser.add_argument('--test-fields',type=int,default=400)
    parser.add_argument('--test-start',type=int,default=500000)
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--designation',default='independent synthetic field test')
    parser.add_argument('--extended-backgrounds',action='store_true')
    parser.add_argument('--varying-psf',action='store_true')
    parser.add_argument('--epoch-balanced',action='store_true')
    args=parser.parse_args();run(args)


if __name__=='__main__':main()
