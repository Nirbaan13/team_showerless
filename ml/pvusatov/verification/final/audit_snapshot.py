"""Portable read-only hash/aggregate audit; no FITS, inference or original paths.

Needs Python and NumPy. Run from any checkout or working directory. Translation
is restricted to the published ml/pvusatov namespace; historical JSON is never
rewritten. This audits existing predictions, not the original execution context.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform

FREEZE_SHA='2bb68024e0101164f7628074b23e82f07f91480fd5161208e2031c05942dfb75'
SUMMARY_SHA='3c0be474cc46488b159e72ebf56fd7a0862fea614a5d1de77c45925143386b9b'
CANDIDATE_SHA='c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204'
METADATA_SHA='983c49f568a2a18f57bfedc5ecda3e11233bb37a3cd52a7277ec8c5095b8ee04'
BASELINE_SHA='dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9'
PROFILES=('primary','secondary');ROLES=('baseline','candidate')
SLIM=('parent_id','seed','trajectory_id','brightness','truth_count','expected_xy','injected_flux','speed_px_hour',
      'origin_xy','velocity_xy_hour','usable_center_epochs','attribution_eligible','matches','scores')

def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb')as stream:
        for block in iter(lambda:stream.read(1048576),b''):value.update(block)
    return value.hexdigest()

def read_json(path):
    def invalid(value):raise ValueError('nonfinite JSON '+value)
    with(gzip.open(path,'rt')if str(path).endswith('.gz')else Path(path).open())as stream:
        return json.load(stream,parse_constant=invalid)

def snapshot_location(root,relative):
    root=Path(root).resolve();path=(root/relative).resolve()
    if Path(relative).is_absolute()or not path.is_relative_to(root):raise ValueError('snapshot path escape')
    return path

def verify_file(path,expected,size=None):
    path=Path(path)
    if path.suffix.lower()in ['.fits','.fit','.fts']:raise ValueError('raw FITS inspection forbidden')
    if digest(path)!=expected:raise ValueError('file hash mismatch: '+str(path))
    if size is not None and path.stat().st_size!=size:raise ValueError('file size mismatch: '+str(path))
    return path

def translate(original,namespace):
    namespace=Path(namespace).resolve();marker='/ml/pvusatov/'
    if marker in original:relative=original.split(marker,1)[1]
    elif original.startswith('ml/pvusatov/'):relative=original[len('ml/pvusatov/'):]
    else:raise ValueError('external original path cannot be translated: '+original)
    return snapshot_location(namespace,relative)

def compare(actual,expected,label='metric'):
    if isinstance(expected,dict):
        if not isinstance(actual,dict)or actual.keys()!=expected.keys():raise ValueError(label+' mapping differs')
        for key,value in expected.items():compare(actual[key],value,label+'.'+key)
    elif isinstance(expected,list):
        if not isinstance(actual,list)or len(actual)!=len(expected):raise ValueError(label+' array differs')
        for index,(a,b)in enumerate(zip(actual,expected)):compare(a,b,label+'['+str(index)+']')
    elif type(expected)is float:
        if type(actual)not in(int,float)or not math.isfinite(actual)or not math.isclose(actual,expected,abs_tol=1e-12,rel_tol=1e-12):raise ValueError(label+' float differs')
    elif type(actual)is not type(expected)or actual!=expected:raise ValueError(label+' value differs')

def references(value,prefix='$'):
    if isinstance(value,dict):
        if set(value)=={'path','sha256'}:yield prefix,value
        else:
            for key,item in value.items():yield from references(item,prefix+'.'+key)
    elif isinstance(value,list):
        for index,item in enumerate(value):yield from references(item,prefix+'['+str(index)+']')

def load_paired(path):
    spec=importlib.util.spec_from_file_location('frozen_paired_replay',path)
    paired=importlib.util.module_from_spec(spec);spec.loader.exec_module(paired);return paired

def archived_manifest(snapshot,files,summary,freeze,kind):
    ref=summary['manifests'][kind];row=files[ref['path']]
    if row['sha256']!=ref['sha256']:raise ValueError('published run manifest anchor differs')
    path=snapshot_location(snapshot,row['snapshot_path']);run=read_json(path)
    for key,value in [('schema_version',1),('kind',kind),('scope','final'),('freeze_sha256',FREEZE_SHA),('versions',freeze['versions']),('options',freeze['options']),('evaluation_complete',True)]:
        if run.get(key)!=value:raise ValueError('run manifest metadata differs: '+key)
    expected={(p['parent_id'],profile,role)for p in freeze['native']['parents']for profile in PROFILES for role in ROLES}if kind=='native'else{('synthetic',profile,role)for profile in PROFILES for role in ROLES}
    found={};originals={ref['path']}
    for output in run['outputs']:
        row=files[output['path']]
        if row['sha256']!=output['sha256']:raise ValueError('cache hash disagrees with frozen run manifest')
        location=snapshot_location(snapshot,row['snapshot_path']);key=tuple(location.name.removesuffix('.json.gz').rsplit('-',2))
        if key not in expected or key in found:raise ValueError('duplicate/undeclared archived cache')
        found[key]=(location,output['summary']);originals.add(output['path'])
    if set(found)!=expected:raise ValueError('incomplete archived run manifest')
    return found,originals

def load_cache(location,declared,freeze,kind,parent,profile,role,metadata):
    cache=read_json(location)
    for key,value in [('schema_version',1),('freeze_sha256',FREEZE_SHA),('partition','final'),('kind',kind),('profile',profile),('system',role),
                      ('model',freeze['models'][role]),('model_metadata',metadata[role]),('versions',freeze['versions']),
                      ('source_sha256',{key:ref['sha256']for key,ref in freeze['sources'].items()}),
                      ('detector_settings',{**freeze['options'][profile],'psf_sigma':freeze['models'][role]['psf_sigma']})]:
        if cache.get(key)!=value:raise ValueError('archived cache metadata differs: '+key)
    if cache['summary']!=declared or declared['evaluation_complete']is not True or declared['error_trials']!=0 or declared['truth_count_unknown_trials']!=0:
        raise ValueError('archived cache evaluation incomplete')
    if any(field.get('error')is not None or field.get('truth_count_known')is False for field in cache['fields']):raise ValueError('archived trial failure')
    if kind=='native':
        matrix=freeze['native']['matrix'];expected={(parent['seed'],f'{speed:g}-{direction}',brightness)for speed in matrix['speeds_px_hour']for direction in range(matrix['directions_per_speed'])for brightness in matrix['brightness']}
        actual=[(field['seed'],field['trajectory_id'],field['brightness'])for field in cache['fields']]
        if any(field['parent_id']!=parent['parent_id']for field in cache['fields']):raise ValueError('archived parent differs')
    else:expected=set(freeze['synthetic']['seeds']);actual=[field['seed']for field in cache['fields']]
    if len(actual)!=len(expected)or set(actual)!=expected or declared['planned']!=len(expected):raise ValueError('archived trial plan incomplete')
    slim=[{key:field[key]for key in SLIM if key in field}for field in cache['fields']]
    header={key:value for key,value in cache.items()if key not in ['fields','control']}
    return slim,header

def audit(namespace):
    namespace=Path(namespace).resolve();snapshot=namespace/'artifacts/v3-final-331c6b1'
    freeze_path=verify_file(namespace/'verification/final/frozen-331c6b1/final-freeze.json',FREEZE_SHA)
    summary_path=verify_file(snapshot/'summary.json',SUMMARY_SHA)
    freeze=read_json(freeze_path);summary=read_json(summary_path)
    if freeze['status']!='frozen'or freeze['authorized_final']is not True or summary['all_outputs_complete_and_integrity_verified']is not True:raise ValueError('published final authorization/completion differs')
    snapshot_manifest=read_json(snapshot/'snapshot-manifest.json')
    if snapshot_manifest['root_final_freeze_sha256']!=FREEZE_SHA or len(snapshot_manifest['files'])!=46:raise ValueError('snapshot count/freeze differs')
    files={};destinations=set();total_bytes=0
    for row in snapshot_manifest['files']:
        destination=snapshot_location(snapshot,row['snapshot_path'])
        if row['original_path']in files or destination in destinations:raise ValueError('duplicate snapshot mapping')
        verify_file(destination,row['sha256'],row['size_bytes']);files[row['original_path']]=row;destinations.add(destination);total_bytes+=row['size_bytes']
    checked_refs=[];external_refs=[]
    for label,ref in references(freeze):
        try:path=translate(ref['path'],namespace)
        except ValueError:external_refs.append(dict(reference=label,original_path=ref['path']));continue
        verify_file(path,ref['sha256']);checked_refs.append(label)
    if len(freeze['sources'])!=15:raise ValueError('scientific source inventory differs')
    for ref in freeze['sources'].values():verify_file(translate(ref['path'],namespace),ref['sha256'])
    metadata={}
    for role,expected in [('baseline',BASELINE_SHA),('candidate',CANDIDATE_SHA)]:
        model=freeze['models'][role]
        if model['artifact']['sha256']!=expected:raise ValueError('published model anchor differs')
        verify_file(translate(model['artifact']['path'],namespace),expected)
        if role=='candidate'and model['metadata']['sha256']!=METADATA_SHA:raise ValueError('original candidate metadata anchor differs')
        meta=verify_file(translate(model['metadata']['path'],namespace),model['metadata']['sha256']);metadata[role]=read_json(meta)
        if metadata[role]['sha256']!=expected:raise ValueError('model metadata linkage differs')
    invocation=read_json(namespace/'verification/final/frozen-331c6b1/summary-invocation-source.json')
    if invocation['root_freeze_sha256']!=FREEZE_SHA:raise ValueError('summary source invocation freeze differs')
    for ref in invocation['sources'].values():verify_file(translate(ref['path'],namespace),ref['sha256'])
    paired=load_paired(translate(freeze['sources']['paired']['path'],namespace))
    runs={};all_originals=set()
    for kind in ['native','synthetic']:
        runs[kind],originals=archived_manifest(snapshot,files,summary,freeze,kind);all_originals.update(originals)
    if all_originals!=set(files):raise ValueError('snapshot contains missing/extra run outputs')
    recomputed={};key_counts={}
    for kind in ['native','synthetic']:
        recomputed[kind]={}
        for profile in PROFILES:
            combined={role:[]for role in ROLES}
            for parent in freeze['native']['parents']if kind=='native'else[None]:
                headers={}
                for role in ROLES:
                    key=(parent['parent_id']if parent else'synthetic',profile,role);location,declared=runs[kind][key]
                    fields,headers[role]=load_cache(location,declared,freeze,kind,parent,profile,role,metadata);combined[role].extend(fields)
                paired.validate_cache_pair(headers['baseline'],headers['candidate'])
            published=summary['reports'][kind][profile]['model']
            report=paired.paired_report(combined['baseline'],combined['candidate'],[field['scores']for field in combined['baseline']],
                [field['scores']for field in combined['candidate']],bootstrap_samples=published['bootstrap_samples'],bootstrap_seed=published['bootstrap_seed'])
            compare(report,published,'metric.'+kind+'.'+profile)
            recomputed[kind][profile]=report
            key_counts[kind+'_'+profile]=dict(trials=report['all_planned']['trials'],independent_groups=report['all_planned']['independent_groups'],
                truth_count=report['all_planned']['truth_count'],common_attributable_trials=report['common_attributable']['trials'])
            del combined
    gate=paired.promotion_gate(recomputed['synthetic']['primary'],recomputed['native']['primary']);compare(gate,summary['primary_recovery_gate'],'metric.primary_gate')
    return dict(schema_version=1,passes=True,audit_source_sha256=digest(__file__),freeze_sha256=FREEZE_SHA,summary_sha256=SUMMARY_SHA,
        snapshot_manifest_sha256=digest(snapshot/'snapshot-manifest.json'),snapshot_files_verified=len(files),snapshot_bytes_verified=total_bytes,
        scientific_sources_verified=len(freeze['sources']),translated_freeze_references_verified=len(checked_refs),
        external_freeze_references_not_verified=external_refs,model_artifacts_and_original_metadata_verified=True,
        summary_invocation_sources_verified=len(invocation['sources']),paired_model_reports_recomputed=4,all_model_report_metrics_match=True,
        primary_gate_matches_published=gate,key_counts=key_counts,replay_python=platform.python_version(),
        floating_comparison=dict(absolute_tolerance=1e-12,relative_tolerance=1e-12,integer_counts_exact=True),
        scope='Portable source/model/snapshot/cache/paired-aggregate audit only; no original FITS, execution-environment recreation, rendering or inference.',
        original_absolute_paths_opened=False,predictions_changed=False,promotion_authorized=False)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--namespace',type=Path,default=Path(__file__).resolve().parents[2]);args=parser.parse_args()
    print(json.dumps(audit(args.namespace),indent=2,allow_nan=False))

if __name__=='__main__':main()
