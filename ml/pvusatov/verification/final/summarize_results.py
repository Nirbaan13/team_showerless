"""Fail-closed summary of completed frozen runs; never reads FITS or reruns science.

Only metadata, opaque source/model hashes and completed gzip caches are read.
Primary recovery uses the immutable paired_report/promotion_gate without changes.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path

ROOT_FREEZE_SHA='2bb68024e0101164f7628074b23e82f07f91480fd5161208e2031c05942dfb75'
PROFILES=('primary','secondary');ROLES=('baseline','candidate')
SPEEDS=(.01,.03,.1,.3,1.,4.,10.,25.,50.);BRIGHTNESS=(3.,6.,12.,24.,48.)
DEV_ROOT=Path('/tmp/spaceapps-v3-runners-post-policy-dev')
# SIA acquisition endpoints have six decimal MJD digits (0.0864 s per digit).
# The PRE-EXISTING DEV three-frame header/acquisition midpoint differences are
# -0.010999991,+0.011200528,-0.010799454 seconds. One endpoint precision unit
# (0.0864 s) covers rounding; fixed before any FINAL output is inspected.
ABS_TIME_TOLERANCE_DAYS=1e-6
UTC_TIME_TOLERANCE_DAYS=.0015/86400  # exported UTC timestamps have millisecond precision
NUISANCE_POLICY='shared flux law, field PSF and overlapping variability for source/artifact identities'

# Shared latent/source allow-list ONLY. Deliberately excludes controls,
# attribution, candidate matches/scores/geometry, caps and runtime measurements.
LATENT_FIELDS=dict(
    native=('parent_id','partition','seed','trajectory_id','speed_px_hour','direction_id','brightness',
            'origin_xy','velocity_xy_hour','expected_xy','injected_flux','epsf','truth_count',
            'usable_center_epochs','center_usable_flags','expected_covered_displacement_px',
            'coverage_known','independent_geometry'),
    synthetic=('seed','mode','metadata','expected_xy','times_hours','registered_shape','truth_count','truth_count_known'))
SOURCE_FIELDS=dict(
    native=('parent_id','seed','input_sources','center_deg','times_hours','registered_shape','frames',
            'acquisition_manifests','downloads_manifest','preparation_options','injection_matrix'),
    synthetic=('parent_id','input_sources','times_hours','registered_shape','center_deg','independent_group',
               'independent_parent_fields','parent_field_seeds','generator'))


def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb')as stream:
        for block in iter(lambda:stream.read(1048576),b''):value.update(block)
    return value.hexdigest()

def read_json(path):
    def invalid(value):raise ValueError('nonfinite JSON: '+value)
    opener=gzip.open if str(path).endswith('.gz')else open
    with opener(path,'rt')as stream:return json.load(stream,parse_constant=invalid)

def load_paired(package):
    spec=importlib.util.spec_from_file_location('immutable_paired',Path(package)/'experiments/v3_evaluation/paired.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def checked(ref,base):
    if set(ref)!= {'path','sha256'}:raise ValueError('invalid hashed reference')
    path=Path(ref['path']);path=path.resolve()if path.is_absolute()else(base/path).resolve()
    # Native pixel bytes were verified by the frozen acquisition/preflight. This
    # report checks their recorded metadata hashes, without reopening those files.
    if path.suffix.lower()in ('.fits','.fit','.fts'):raise ValueError('summary cannot open native FITS')
    if digest(path)!=ref['sha256']:raise ValueError('reference byte hash mismatch: '+str(path))
    return path

def verify_freeze(path,expected,development=False):
    path=Path(path).resolve()
    if not development and expected!=ROOT_FREEZE_SHA:raise ValueError('root freeze trust anchor differs')
    if development and not path.is_relative_to(DEV_ROOT):raise ValueError('development inspection restricted to declared DEV schemas')
    if digest(path)!=expected:raise ValueError('freeze byte hash mismatch')
    freeze=read_json(path)
    if freeze.get('status')!='frozen'or freeze.get('schema_version')!=1:raise ValueError('freeze not frozen')
    if freeze.get('scope')!=('development'if development else'final')or freeze.get('authorized_final')is not(not development):
        raise ValueError('freeze scope/authorization differs')
    package=Path(freeze['package_root']).resolve();base=path.parent
    for ref in list(freeze['sources'].values())+freeze.get('provenance_files',[])+freeze['native']['acquisition_manifests']:
        checked(ref,base)
    for role in ROLES:
        model=freeze['models'][role];checked(model['artifact'],base);meta=checked(model['metadata'],base)
        if read_json(meta)['sha256']!=model['artifact']['sha256']:raise ValueError('model metadata binding differs')
    checked(freeze['synthetic']['calibration_bank'],base)
    parents=freeze['native']['parents'];ids=[p['parent_id']for p in parents]
    if ids!=sorted(set(ids)):raise ValueError('parent identities are not canonical')
    if not development and(ids!=[f'final{i:02d}'for i in range(1,11)]or[p['seed']for p in parents]!=list(range(2200001,2200011))or freeze['synthetic']['seeds']!=list(range(2000000,2002000))):
        raise ValueError('final parent/seed plan differs')
    for parent in parents:
        manifest=checked(parent['downloads_manifest'],base);parent['_downloads']=read_json(manifest)
        if not development and len(parent['_downloads'])!=8:raise ValueError('final native epoch plan differs')
    freeze['_sha256']=expected;freeze['_path']=str(path)
    return freeze,load_paired(package)

def validate_run_header(run,freeze,kind):
    if run.get('freeze_sha256')!=freeze['_sha256']:raise ValueError('run freeze differs')
    if any(run.get(key)!=expected for key,expected in [('schema_version',1),('kind',kind),('scope',freeze['scope']),('versions',freeze['versions']),('options',freeze['options'])]):
        raise ValueError('run metadata differs')
    if run.get('evaluation_complete')is not True:raise ValueError('run is incomplete')

def validate_trial_plan(fields,kind,parent,freeze):
    if kind=='native':
        expected={(parent['parent_id'],parent['seed'],f'{speed:g}-{direction}',speed,direction,brightness)
                  for speed in SPEEDS for direction in range(6)for brightness in BRIGHTNESS}
        actual=[(f.get('parent_id'),f.get('seed'),f.get('trajectory_id'),f.get('speed_px_hour'),f.get('direction_id'),f.get('brightness'))for f in fields]
    else:expected=set(freeze['synthetic']['seeds']);actual=[f.get('seed')for f in fields]
    if len(actual)!=len(expected)or set(actual)!=expected:raise ValueError('missing, duplicate or undeclared trial identities')

def recompute_summary(fields,control_capped):
    result=dict(planned=0,candidate_rows=0,spatial_recovered=0,spatial_recovered_trials=0,resolved_truth_span_ge3px=0,
                truth_count_unknown_trials=0,error_trials=0,peak_cap_trials=0,errors_by_phase={})
    for f in fields:
        if f.get('error')is not None:raise ValueError('trial runtime failure')
        if f.get('truth_count_known')is False:raise ValueError('unknown truth trial')
        result['planned']+=1;result['candidate_rows']+=len(f['matches'])
        result['spatial_recovered']+=len({m for m in f['matches']if m>=0})
        result['spatial_recovered_trials']+=int(any(m>=0 for m in f['matches']))
        result['resolved_truth_span_ge3px']+=len({g['truth_index']for g in f['matched_geometry']if g['true_displacement_px']>=3})
        if type(f.get('peak_cap_reached'))is not bool:raise ValueError('missing cap diagnostic')
        result['peak_cap_trials']+=int(f['peak_cap_reached'])
    result['evaluation_complete']=True;result['search_coverage_complete']=not result['peak_cap_trials']and not control_capped
    return result

def finite_matrix(values,columns):
    return isinstance(values,list)and all(isinstance(row,list)and len(row)==columns and all(isinstance(v,(float,int))and math.isfinite(v)for v in row)for row in values)

def paths_for_truth(field,kind):return [field['expected_xy']]if kind=='native'else field['expected_xy']

def synthetic_metadata(field):
    times=field.get('times_hours');shape=field.get('registered_shape');metadata=field.get('metadata')
    if not isinstance(times,list)or not 3<=len(times)<=8 or any(type(t)not in (int,float)or not math.isfinite(t)for t in times)or times!=sorted(set(times))or times[0]!=0.:
        raise ValueError('synthetic times invalid')
    n=len(times)
    if shape!=[n,80,80]:raise ValueError('synthetic registered shape invalid')
    mode='noise_only'if field['seed']%10==0 else'artifacts_only'if field['seed']%10==1 else'injected'
    if field.get('mode')!=mode:raise ValueError('synthetic mode differs from generator')
    base={'epoch_count','cadence_family','positive_fluxes','artifact_fluxes','label_nuisance_policy'}
    extra={'detector','psf_family','psf_bank_row','registration_jitter_xy','extended_stationary_sources','epoch_psf_rows'}
    if not isinstance(metadata,dict)or set(metadata)!=(base if mode=='noise_only'else base|extra):raise ValueError('synthetic full generator metadata missing')
    if metadata['epoch_count']!=n or type(metadata['cadence_family'])is not int or metadata['cadence_family']not in range(4)or metadata['label_nuisance_policy']!=NUISANCE_POLICY:raise ValueError('synthetic generator metadata invalid')
    for key in ['positive_fluxes','artifact_fluxes']:
        if not isinstance(metadata[key],list)or any(type(v)not in (float,int)or not math.isfinite(v)or v<=0 for v in metadata[key]):raise ValueError('synthetic flux metadata invalid')
    if len(metadata['positive_fluxes'])!=field['truth_count']or(mode!='injected'and field['truth_count']!=0)or(mode=='injected'and not 1<=field['truth_count']<=4):raise ValueError('synthetic truth/generator metadata differs')
    if mode=='noise_only':
        if metadata['artifact_fluxes']:raise ValueError('noise-only artifact metadata invalid')
    else:
        if type(metadata['detector'])is not int or metadata['detector']not in range(1,7)or metadata['psf_family']not in ['calibration','analytic_core_wing']or type(metadata['psf_bank_row'])is not int or metadata['psf_bank_row']<0:raise ValueError('synthetic PSF metadata invalid')
        if not finite_matrix(metadata['registration_jitter_xy'],2)or len(metadata['registration_jitter_xy'])!=n:raise ValueError('synthetic jitter metadata invalid')
        rows=metadata['epoch_psf_rows']
        if not isinstance(rows,list)or len(rows)!=n or any(type(v)is not int or v<0 for v in rows):raise ValueError('synthetic epoch PSF metadata invalid')
        extended=metadata['extended_stationary_sources']
        if type(extended)is not int or(extended not in range(3,9)if field['seed']%3==0 else extended!=0):raise ValueError('synthetic extended generator metadata invalid')
        if not 8*n<=len(metadata['artifact_fluxes'])<=21*n:raise ValueError('synthetic artifact metadata invalid')
    if any(len(path)!=n for path in field['expected_xy']):raise ValueError('synthetic truth/time epoch length differs')


def validate_shared_latents(cache,kind,registry):
    key=(kind,cache['parent_id'])
    payload=dict(source={name:cache[name]for name in SOURCE_FIELDS[kind]},
                 fields=[{name:field[name]for name in LATENT_FIELDS[kind]}for field in cache['fields']])
    payload['fields'].sort(key=lambda field:json.dumps([field.get('parent_id'),field['seed'],field.get('trajectory_id'),field.get('brightness')]))
    fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True,allow_nan=False,separators=(',',':')).encode()).hexdigest()
    if key in registry and registry[key]!=fingerprint:raise ValueError('shared latent/source metadata differs across profiles/systems')
    registry[key]=fingerprint


_GEOMETRY=None
def geometry_validator():
    global _GEOMETRY
    if _GEOMETRY is None:
        spec=importlib.util.spec_from_file_location('summary_geometry',Path(__file__).with_name('summary_geometry.py'))
        _GEOMETRY=importlib.util.module_from_spec(spec);spec.loader.exec_module(_GEOMETRY)
    return _GEOMETRY


def validate_field(field,kind,times_hours=None):
    count=field.get('truth_count');n=len(field['matches'])
    if type(count)is not int or count<0 or(kind=='native'and count!=1):raise ValueError('invalid truth count')
    if field.get('error')is not None:raise ValueError('trial runtime failure')
    if(kind=='synthetic'and field.get('truth_count_known')is not True)or(kind=='native'and field.get('coverage_known')is not True):raise ValueError('unknown truth/coverage')
    if type(field.get('attribution_eligible'))is not bool:raise ValueError('unknown attribution')
    if kind=='native'and type(field.get('preexisting_control_match'))is not bool:raise ValueError('unknown control attribution')
    if any(type(m)is not int or m<(-2 if kind=='native'else-1)or m>=count for m in field['matches']):raise ValueError('invalid candidate truth index')
    for column in ['scores','baseline']:
        if len(field[column])!=n or any(not isinstance(v,(int,float))or not math.isfinite(v)for v in field[column]):raise ValueError('candidate score alignment/finite failure')
    if any(not 0<=v<=1 for v in field['scores']):raise ValueError('model score outside unit interval')
    if len(field['features'])!=n or not finite_matrix(field['features'],6):raise ValueError('measured feature alignment/finite failure')
    if len(field['candidate_epochs'])!=n or len(field['candidate_positions_xy'])!=n:raise ValueError('candidate geometry alignment failure')
    paths=paths_for_truth(field,kind)
    if len(paths)!=count or any(not finite_matrix(path,2)for path in paths):raise ValueError('expected geometry invalid')
    epochs=len(paths[0])if paths else len(field['times_hours'])
    if any(len(path)!=epochs for path in paths):raise ValueError('expected geometry epoch count differs')
    for observed,xy in zip(field['candidate_epochs'],field['candidate_positions_xy']):
        if not isinstance(observed,list)or observed!=sorted(set(observed))or any(type(e)is not int or not 0<=e<epochs for e in observed)or len(xy)!=len(observed)or not finite_matrix(xy,2):raise ValueError('candidate geometry invalid')
    if kind=='synthetic':synthetic_metadata(field)
    geometry_validator().validate_matched_geometry(field,times_hours if kind=='native'else field['times_hours'],native=kind=='native')
    if kind=='native':
        flags=field['center_usable_flags']
        if len(flags)!=epochs or any(type(v)is not bool for v in flags)or sum(flags)!=field['usable_center_epochs']:raise ValueError('finite-center geometry invalid')
        if field['attribution_eligible']==field['preexisting_control_match']:raise ValueError('control attribution inconsistent')

KEEP=('parent_id','seed','trajectory_id','brightness','truth_count','expected_xy','injected_flux','speed_px_hour','direction_id',
      'origin_xy','velocity_xy_hour','usable_center_epochs','attribution_eligible','preexisting_control_match','matches','scores','baseline',
      'center_usable_flags','independent_geometry','matched_geometry','mode','metadata','times_hours','registered_shape')
def slim(field):return {key:field[key]for key in KEEP if key in field}

def cache_metadata(cache,freeze,kind,parent,profile,role):
    expected=dict(schema_version=1,freeze_sha256=freeze['_sha256'],versions=freeze['versions'],profile=profile,system=role,
                  partition=freeze['scope'],kind=kind,model=freeze['models'][role],
                  detector_settings={**freeze['options'][profile],'psf_sigma':freeze['models'][role]['psf_sigma']},
                  source_sha256={key:ref['sha256']for key,ref in freeze['sources'].items()})
    for key,value in expected.items():
        if cache.get(key)!=value:raise ValueError('cache metadata differs: '+key)
    if cache['model_metadata']!=read_json(freeze['models'][role]['metadata']['path']):raise ValueError('cache model metadata differs')
    controls=None
    if kind=='native':
        for key,value in [('parent_id',parent['parent_id']),('seed',parent['seed']),('center_deg',parent['center_deg']),
                          ('downloads_manifest',parent['downloads_manifest']),('preparation_options',freeze['native']['region']),
                          ('injection_matrix',freeze['native']['matrix']),('acquisition_manifests',freeze['native']['acquisition_manifests'])]:
            if cache.get(key)!=value:raise ValueError('native cache metadata differs: '+key)
        if [r['sha256']for r in cache['input_sources']]!=[r['sha256']for r in parent['_downloads']]:raise ValueError('native data metadata byte hashes differ')
        frames=cache['frames'];inputs=cache['input_sources']
        if len(frames)!=len(inputs)or len(cache['times_hours'])!=len(inputs):raise ValueError('native prepared epoch count differs')
        if {f['sha256']for f in frames}!={r['sha256']for r in inputs}:raise ValueError('native frame hashes differ')
        if all('obs_id'in row for row in parent['_downloads'])and{f['physical_observation_id']for f in frames}!={r['obs_id']for r in parent['_downloads']}:raise ValueError('native prepared physical OBSIDs differ')
        if all('obs_id'in row for row in parent['_downloads']):
            expected_obsids={row['sha256']:row['obs_id']for row in parent['_downloads']}
            if any(expected_obsids[frame['sha256']]!=frame['physical_observation_id']for frame in frames):raise ValueError('native frame hash/physical OBSID association differs')
        times=cache['times_hours']
        if any(not isinstance(t,(int,float))or not math.isfinite(t)for t in times)or times!=sorted(set(times))or abs(times[0])>1e-9:raise ValueError('native epoch times invalid')
        if any(abs((frame['midpoint_mjd']-frames[0]['midpoint_mjd'])*24-t)>1e-6 for frame,t in zip(frames,times)):raise ValueError('native epoch/time association differs')
        acquisition={row['sha256']:row for row in parent['_downloads']}
        if freeze['scope']=='development'and any('t_min_mjd'not in row for row in acquisition.values()):
            # The pre-existing small DEV downloads schema lacks interval metadata;
            # use its matching immutable published acquisition rows, never FINAL.
            audit=read_json(Path(freeze['package_root'])/'experiments/v3_data/evidence/acquisition/audit.json')
            published={row['sha256']:row for group in audit['groups']for row in group['downloads']}
            acquisition={sha:published[sha]for sha in acquisition}
        epoch=datetime(1858,11,17,tzinfo=timezone.utc)
        for frame in frames:
            row=acquisition[frame['sha256']];lo=row['t_min_mjd'];hi=row['t_max_mjd'];mid=frame['midpoint_mjd']
            if not all(type(value)in (int,float)and math.isfinite(value)for value in [lo,hi,mid])or lo>hi or not lo-ABS_TIME_TOLERANCE_DAYS<=mid<=hi+ABS_TIME_TOLERANCE_DAYS or abs(mid-(lo+hi)/2)>ABS_TIME_TOLERANCE_DAYS:raise ValueError('native absolute acquisition midpoint differs')
            try:utc=datetime.fromisoformat(frame['midpoint_utc'].replace('Z','+00:00'))
            except (KeyError,TypeError,ValueError)as exc:raise ValueError('native UTC timestamp invalid')from exc
            if utc.tzinfo is None or abs((utc-epoch).total_seconds()/86400-mid)>UTC_TIME_TOLERANCE_DAYS:raise ValueError('native UTC/MJD midpoint differs')
        if cache.get('control_labels')!='unknown'or cache.get('control_error')is not None or cache['control_diagnostics'].get('error')is not None:raise ValueError('native controls unavailable or labelled')
        if any(m!=-2 for m in cache['control']['matches']):raise ValueError('native controls must remain UNKNOWN')
        controls=dict(parent_id=parent['parent_id'],profile=profile,system=role,identities='UNKNOWN',
                      candidate_rows=len(cache['control']['matches']),precision=None,precision_estimated=False,
                      peaks_per_epoch=cache['control_diagnostics']['peaks_per_epoch'],peak_cap_reached=cache['control_diagnostics']['peak_cap_reached'])
    else:
        for key,value in [('input_sources',[freeze['synthetic']['calibration_bank']]),('parent_field_seeds',freeze['synthetic']['seeds']),
                          ('independent_parent_fields',len(freeze['synthetic']['seeds'])),('generator',freeze['synthetic']['generator'])]:
            if cache.get(key)!=value:raise ValueError('synthetic cache metadata differs: '+key)
    if cache.get('all_derivatives_correlated')is not(kind=='native'):raise ValueError('independence declaration differs')
    return controls

def read_run(path,freeze,kind):
    path=Path(path).resolve();run=read_json(path);validate_run_header(run,freeze,kind)
    parent_map={p['parent_id']:p for p in freeze['native']['parents']}
    expected={(p,profile,role)for p in parent_map for profile in PROFILES for role in ROLES}if kind=='native'else{('synthetic',profile,role)for profile in PROFILES for role in ROLES}
    found={};references=[]
    for output in run['outputs']:
        location=Path(output['path']).resolve()
        if location.parent!=path.parent:raise ValueError('cache outside declared run directory')
        pieces=location.name.removesuffix('.json.gz').rsplit('-',2)
        if len(pieces)!=3:raise ValueError('cache filename schema invalid')
        key=tuple(pieces)
        if key not in expected or key in found:raise ValueError('undeclared or duplicate cache output')
        if digest(location)!=output['sha256']:raise ValueError('cache byte hash mismatch')
        found[key]=(location,output['summary']);references.append(dict(path=str(location),sha256=output['sha256']))
    if set(found)!=expected:raise ValueError('missing cache manifest outputs')
    return found,dict(path=str(path),sha256=digest(path),cache_references=references)

def load_pair(found,freeze,kind,parent,profile,paired,latent_registry):
    metadata={};fields={};diagnostics={};controls=[]
    for role in ROLES:
        key=(parent['parent_id']if kind=='native'else'synthetic',profile,role);location,declared=found[key];cache=read_json(location)
        control=cache_metadata(cache,freeze,kind,parent,profile,role)
        if control:controls.append(control)
        validate_trial_plan(cache['fields'],kind,parent,freeze)
        actual=recompute_summary(cache['fields'],bool(control and control['peak_cap_reached']))
        if cache['summary']!=actual or declared!=actual:raise ValueError('cache/run completion summary differs from actual trials')
        for f in cache['fields']:validate_field(f,kind,times_hours=cache['times_hours']if kind=='native'else None)
        validate_shared_latents(cache,kind,latent_registry)
        if any(f.get('partition',freeze['scope'])!=freeze['scope']for f in cache['fields']):raise ValueError('trial partition differs')
        fields[role]=[slim(f)for f in cache['fields']]
        diagnostics[role]=dict(summary=actual,peak_cap_trials=actual['peak_cap_trials'],control_peak_cap_reached=bool(control and control['peak_cap_reached']),
            detector_cpu_seconds=sum(f['detector_cpu_seconds']for f in cache['fields']),model_cpu_seconds=sum(f['model_cpu_seconds']for f in cache['fields']),
            detector_wall_seconds_sum=sum(f['detector_wall_seconds']for f in cache['fields']),model_wall_seconds_sum=sum(f['model_wall_seconds']for f in cache['fields']),
            worker_peak_rss_mib=max(f['rss_mib']for f in cache['fields']))
        metadata[role]={k:v for k,v in cache.items()if k not in ['fields','control']};del cache
    paired.validate_cache_pair(metadata['baseline'],metadata['candidate'])
    return fields,diagnostics,controls

def paired_result(pair,paired,samples,heuristic=False):
    score='baseline'if heuristic else'scores'
    return paired.paired_report(pair['baseline'],pair['candidate'],[f[score]for f in pair['baseline']],[f[score]for f in pair['candidate']],bootstrap_samples=samples)

def span(points):return max((math.dist(a,b)for a in points for b in points),default=0.)

def geometry_pair(pair,kind):
    """Independent truth geometry selects objects, preserving every candidate row."""
    result={role:[]for role in ROLES}
    for role in ROLES:
        for field in pair[role]:
            if kind=='native':
                covered=[xy for xy,flag in zip(field['expected_xy'],field['center_usable_flags'])if flag]
                keep=[0]if len(covered)>=3 and span(covered)>=3 else[]
            else:keep=[i for i,path in enumerate(field['expected_xy'])if span(path)>=3]
            if not keep:continue
            mapping={truth:i for i,truth in enumerate(keep)}
            item={**field,'truth_count':len(keep),'matches':[mapping.get(m,-2 if kind=='native'else-1)for m in field['matches']]}
            if kind=='synthetic':item['expected_xy']=[field['expected_xy'][i]for i in keep]
            result[role].append(item)
    return result

def per_group(pair,paired):
    groups=defaultdict(lambda:{role:[]for role in ROLES})
    for role in ROLES:
        for f in pair[role]:groups[str(f['parent_id'])if'parent_id'in f else str(f['seed'])][role].append(f)
    output={}
    for key,values in sorted(groups.items()):
        report=paired_result(values,paired,1)
        # A single-group bootstrap adds no uncertainty information; retain counts,
        # recalls and denominators, while the pooled report owns parent CIs.
        for cohort in ['all_planned','common_attributable','common_finite_center_ge3']:
            for metric in ['paired_parent_ci95_top1','paired_parent_ci95_top3']:report[cohort].pop(metric,None)
        output[key]=report
    return output

def native_strata(pair,paired,samples):
    output={}
    for key,values in [('speed_px_hour',SPEEDS),('brightness',BRIGHTNESS)]:
        output[key]={str(v):paired_result({role:[f for f in pair[role]if f[key]==v]for role in ROLES},paired,samples)for v in values}
    return output

def summarize(freeze_path,freeze_sha,native_manifest,synthetic_manifest,bootstrap_samples=10000,development=False):
    if type(bootstrap_samples)is not int or not 1<=bootstrap_samples<=10000:raise ValueError('bootstrap sample bounds invalid')
    if development and any(not Path(p).resolve().is_relative_to(DEV_ROOT)for p in [native_manifest,synthetic_manifest]):raise ValueError('development inputs restricted to declared DEV schemas')
    freeze,paired=verify_freeze(freeze_path,freeze_sha,development)
    # Validate BOTH completed manifests before opening any cache or calculating a
    # metric; no partial aggregate/promotion gate is published.
    native,native_ref=read_run(native_manifest,freeze,'native');synthetic,synthetic_ref=read_run(synthetic_manifest,freeze,'synthetic')
    reports={'native':{},'synthetic':{}};all_controls=[];latent_registry={}
    for profile in PROFILES:
        combined={role:[]for role in ROLES};costs={}
        for parent in freeze['native']['parents']:
            pair,diagnostics,controls=load_pair(native,freeze,'native',parent,profile,paired,latent_registry)
            for role in ROLES:combined[role].extend(pair[role])
            costs[parent['parent_id']]=diagnostics;all_controls.extend(controls)
        reports['native'][profile]=dict(model=paired_result(combined,paired,bootstrap_samples),
            heuristic=paired_result(combined,paired,bootstrap_samples,True),
            resolved_truth_span_ge3px=paired_result(geometry_pair(combined,'native'),paired,bootstrap_samples),
            per_parent=per_group(combined,paired),strata=native_strata(combined,paired,bootstrap_samples),runtime_and_caps=costs)
        del combined
        pair,diagnostics,_=load_pair(synthetic,freeze,'synthetic',None,profile,paired,latent_registry)
        reports['synthetic'][profile]=dict(model=paired_result(pair,paired,bootstrap_samples),
            heuristic=paired_result(pair,paired,bootstrap_samples,True),
            resolved_truth_span_ge3px=paired_result(geometry_pair(pair,'synthetic'),paired,bootstrap_samples),
            per_field=per_group(pair,paired),runtime_and_caps=diagnostics)
        del pair
    gate=paired.promotion_gate(reports['synthetic']['primary']['model'],reports['native']['primary']['model'])
    return dict(schema_version=1,freeze_sha256=freeze_sha,scope=freeze['scope'],summary_source_sha256=digest(__file__),
        manifests=dict(native=native_ref,synthetic=synthetic_ref),all_outputs_complete_and_integrity_verified=True,
        reports=reports,native_real_controls=all_controls,
        primary_recovery_gate=gate,runtime_gate='REQUIRES_SEPARATE_COORDINATOR_REVIEW',integration_gate='REQUIRES_SEPARATE_COORDINATOR_REVIEW',
        promotion_authorized=False,selection_or_refit_performed=False,
        interpretation=dict(primary_only_gate=True,secondary='Slow min-speed .005 diagnostic on the same parents, never pooled with primary',
            uncertainty_unit='Native independent parent; synthetic whole field; derivatives remain clustered',
            resolved_geometry='Independent truth span >=3 pixels; native requires >=3 finite centers. Candidate rows preserved, other truths do not count. Diagnostic only.',
            all_planned='Includes unresolved and ambiguous/preexisting-match trials; common-attributable separately excludes shared attribution failures',
            scores='Uncalibrated ranking scores, not real-object probabilities',native_precision='UNKNOWN: real control identities remain unlabelled; no real precision estimate',
            caps='Cap flags are separate search-coverage limits; zero runtime failures does not imply uncapped search',
            runtime='Per-worker stage sums and peak RSS; reused detector work can appear in both systems. Not service latency.'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ['freeze','freeze-sha256','native-manifest','synthetic-manifest','output']:parser.add_argument('--'+flag,required=True)
    parser.add_argument('--both-runs-finished',action='store_true',required=True)
    parser.add_argument('--bootstrap-samples',type=int,default=10000)
    args=parser.parse_args()
    output=Path(args.output).resolve();namespace=Path(__file__).resolve().parents[2]
    if not output.is_relative_to(namespace):raise ValueError('summary output must be namespaced')
    if output.exists():raise ValueError('refusing to overwrite a summary')
    result=summarize(args.freeze,args.freeze_sha256,args.native_manifest,args.synthetic_manifest,args.bootstrap_samples)
    output.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive final write: failures above publish no aggregate or gate.
    with output.open('x')as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(dict(path=str(output),sha256=digest(output),primary_recovery_gate=result['primary_recovery_gate'],promotion_authorized=False)))

if __name__=='__main__':main()
