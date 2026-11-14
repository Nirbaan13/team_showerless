"""Build unsigned final-run metadata; never evaluate or read FITS headers/pixels.

Only the standard library and the runner's metadata-only constants/versions are
loaded. Native files and calibration/model artifacts are streamed as opaque bytes.
No function can authorize a run: every emitted payload has status=draft.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re

V2_SHA='dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9'
CANDIDATE_SHA='c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204'
CANDIDATE_METADATA_SHA='983c49f568a2a18f57bfedc5ecda3e11233bb37a3cd52a7277ec8c5095b8ee04'
BANK_SHA='793e05135438c95b8eaeace21948b34fe2eb49cd581be9e81dfff2b493e08d6d'

def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb')as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()

def load_runner(package_root):
    spec=importlib.util.spec_from_file_location('freeze_schema',Path(package_root)/'experiments/v3_evaluation/run_native.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def document(path):return json.loads(Path(path).read_text())

def reference(path):return dict(path=str(Path(path).resolve()),sha256=digest(path))

def write_new(path,payload):
    """Never silently replace an earlier draft or its evidence."""
    with Path(path).open('x')as stream:json.dump(payload,stream,indent=2,allow_nan=False);stream.write('\n')

def audit_groups(groups):
    """Audit physical IDs across all versions, detectors, variants and splits."""
    physical={};checked={}
    for group in groups:
        parent=group['parent_group_id'];split=group['split']
        for row in group['downloads']:
            path=Path(row['path']).resolve();expected=row['sha256']
            if path not in checked:checked[path]=(digest(path),path.stat().st_size)
            if checked[path]!=(expected,row['bytes']):raise ValueError('observation byte hash/size mismatch: '+str(path))
            obs=str(row['obs_id']);entry=physical.get(obs)
            if entry and(entry['parent_id']!=parent or entry['split']!=split):
                raise ValueError('cross-parent physical OBSID overlap: '+obs)
            if entry and(entry['sha256']!=expected or entry['detector']!=row['detector']):
                raise ValueError('same-parent physical OBSID bytes/detector inconsistent: '+obs)
            if entry is None:
                entry=dict(physical_obsid=obs,parent_id=parent,split=split,detector=row['detector'],sha256=expected,
                           bytes=row['bytes'],t_min_mjd=row['t_min_mjd'],t_max_mjd=row['t_max_mjd'],paths=[])
                physical[obs]=entry
            if str(path)not in entry['paths']:entry['paths'].append(str(path))
    for entry in physical.values():entry['paths'].sort()
    return [physical[key]for key in sorted(physical)]

def build(namespace,output,source_commit):
    namespace=Path(namespace).resolve();output=Path(output).resolve()
    if not re.fullmatch('[0-9a-f]{40}',source_commit)or not source_commit.startswith('331c6b1'):
        raise ValueError('exact full331c6b1 source commit is required')
    if not output.is_relative_to(namespace):raise ValueError('all generated paths must be under ml/pvusatov')
    if output.exists():raise ValueError('output already exists; preserve the previous draft')
    output.mkdir(parents=True)
    package=namespace/'backend/inference';evidence=package/'experiments/v3_data/evidence';acquisition=evidence/'acquisition'
    runner=load_runner(package)
    publication=document(evidence/'publication-manifest.json')
    repo=namespace.parents[1]
    for row in publication['files']:
        path=repo/row['published_path']
        if digest(path)!=row['sha256']:raise ValueError('published acquisition bytes changed: '+str(path))
    original=document(acquisition/'audit.json');expanded=document(acquisition/'expansion-v2/audit-expanded-v2.json')
    finals=document(acquisition/'expansion-v2/final-byte-audit-v2.json')
    if any(x['final_pixels_opened']is not False for x in [original,expanded,finals]):raise ValueError('acquisition final closure missing')
    groups=original['groups']+expanded['new_groups']
    primary=sorted(finals['groups'],key=lambda row:row['parent_group_id'])
    if [g['parent_group_id']for g in primary]!=[f'final{i:02d}'for i in range(1,11)]:raise ValueError('exact final10 parents required')
    manifest_directory=output/'native-manifests';manifest_directory.mkdir()
    parents=[];all_groups=list(groups)
    for index,group in enumerate(primary,2200001):
        source=Path(group['directory'])/'downloads.json';rows=document(source)
        if rows!=group['downloads']or len(rows)!=8 or len({r['obs_id']for r in rows})!=8:
            raise ValueError('audited augmented8 manifest differs: '+group['parent_group_id'])
        destination=manifest_directory/(group['parent_group_id']+'-augmented8-downloads.json')
        with destination.open('xb')as stream:stream.write(source.read_bytes())
        if digest(destination)!=digest(source):raise ValueError('manifest copy mismatch')
        all_groups.append(group)
        parents.append(dict(parent_id=group['parent_group_id'],seed=index,center_deg=group['center'],
                            downloads_manifest=reference(destination),variant='augmented8',detector=group['detector'],
                            stratum=group['stratum'],physical_midpoint_span_hours=group['physical_midpoint_span_hours'],
                            physical_obsids=[row['obs_id']for row in rows],original_downloads_manifest=reference(source)))
    mapping=audit_groups(all_groups)
    counts=Counter(row['split']for row in mapping)
    if dict(counts)!=dict(train=43,validation=77,final=80):raise ValueError('physical exposure counts differ: '+str(counts))
    parent_counts=Counter(split for _,split in {(r['parent_id'],r['split'])for r in mapping})
    if dict(parent_counts)!=dict(train=8,validation=11,final=10):raise ValueError('parent split counts differ')
    audit=dict(schema_version=1,method='JSON metadata and opaque byte hash/size only; no FITS reader/header/pixel access',
               source_commit=source_commit,physical_observations=len(mapping),exposure_counts=dict(counts),
               parent_counts=dict(parent_counts),cross_parent_physical_obsid_overlap=0,final_pixels_opened=False,
               observations=mapping)
    audit_path=output/'physical-observation-audit.json';write_new(audit_path,audit)
    baseline=namespace/'releases/v2/backend/inference/models';candidate=namespace/'artifacts/v3-development-candidate'
    models={}
    for role,root,sigma,expected in [('baseline',baseline,1.2,V2_SHA),('candidate',candidate,.8,CANDIDATE_SHA)]:
        artifact=reference(root/'ranker.onnx');metadata=reference(root/'metadata.json')
        if artifact['sha256']!=expected or document(metadata['path'])['sha256']!=expected:raise ValueError('frozen model binding differs')
        if role=='candidate'and metadata['sha256']!=CANDIDATE_METADATA_SHA:raise ValueError('candidate metadata differs')
        models[role]=dict(artifact=artifact,metadata=metadata,psf_sigma=sigma)
    bank=reference(package/'training/calibration/instrument-epsf-bank.npz')
    if bank['sha256']!=BANK_SHA:raise ValueError('calibration bank differs')
    acquisition_files=[evidence/'publication-manifest.json',evidence/'query-provenance.json',
        acquisition/'partition-plan.json',acquisition/'cadence-supplement-plan.json',
        acquisition/'crowded-development/partition-plan.json',acquisition/'expansion-v2/partition-plan.json',
        acquisition/'audit.json',acquisition/'data-handoff.json',acquisition/'expansion-v2/audit-expanded-v2.json',
        acquisition/'expansion-v2/final-byte-audit-v2.json',acquisition/'expansion-v2/data-handoff-v2.json',audit_path]
    provenance=[namespace/'artifacts/v3-selected-input-provenance.json',namespace/'artifacts/v3-profile-bound-artifact-review.json',namespace/'artifacts/v3-selection-source/snapshot-manifest.json',
        namespace/'artifacts/v3-selection-source/invocation-source.json',namespace/'artifacts/v3-selected-output-policy-parity.json',
        candidate/'freeze.json',candidate/'export-validation.json',candidate/'system-validation-evaluation.json',
        candidate/'selection-invocation-source.json',candidate/'training-manifest.json',candidate/'runtime-probe.json',
        namespace/'verification/legacy-runtime-parity-proof.json',
        package/'experiments/v3_evaluation/results/preset-compatibility.json',
        package/'experiments/v3_evaluation/results/preset-compatibility-post-policy.json',
        package/'experiments/v3_evaluation/results/preset-compatibility-post-policy-manifest.json',
        namespace/'docs/ai/ML-V3-COORDINATION.AI.md',Path(__file__).resolve()]
    snapshot=namespace/'artifacts/v3-selection-source'
    for row in document(snapshot/'snapshot-manifest.json')['files']:
        path=snapshot/row['path']
        if digest(path)!=row['sha256']:raise ValueError('historical selection source snapshot differs')
    payload=dict(schema_version=1,status='draft',scope='final',authorized_final=False,unsigned=True,
        source_commit=source_commit,package_root=str(package),
        sources={name:reference(package/relative)for name,relative in runner.SOURCES.items()},
        versions=runner.versions(),runtime=dict(workers=6,math_threads=1,max_frames=32,max_grid=512),models=models,
        options={name:{**runner.OPTIONS,'min_speed':speed}for name,speed in [('primary',.5),('secondary',.005)]},
        native=dict(matrix=runner.MATRIX,region=dict(width_arcmin=6.,height_arcmin=6.,pixel_scale_arcsec=6.15,mask_policy='motion'),
                    parents=parents,acquisition_manifests=[reference(path)for path in acquisition_files],
                    primary_epoch_variant='augmented8',short_variants='secondary correlated derivatives; never extra parents'),
        synthetic=dict(seeds=list(range(2000000,2002000)),calibration_bank=bank,
                       generator=dict(extended_every_nth_field=3,varying_psf=True)),
        provenance_files=[reference(path)for path in provenance],
        authorization_note='UNSIGNED DRAFT. Coordinator must independently verify CI, source bytes, provenance and authorization, then create a separate trusted frozen JSON and record its SHA256 externally. This file cannot execute.')
    draft=output/'final-freeze.draft.json';write_new(draft,payload)
    try:runner.validate_freeze(draft,digest(draft))
    except ValueError as exc:
        if 'status frozen'not in str(exc):raise
    else:raise AssertionError('draft was unexpectedly executable')
    write_new(output/'draft-manifest.json',dict(schema_version=1,status='draft',authorized_final=False,source_commit=source_commit,
        files=[reference(path)for path in [draft,audit_path,*sorted(manifest_directory.glob('*.json'))]],
        final_pixels_opened=False,runner_executed=False,simulation_executed=False))
    return draft

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--namespace',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-commit',required=True)
    args=parser.parse_args();path=build(args.namespace,args.output,args.source_commit)
    print(json.dumps(dict(path=str(path),sha256=digest(path),status='draft',authorized_final=False)))

if __name__=='__main__':main()
