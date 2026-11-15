"""Frozen independent association research, with all planned rows retained.

Only root's checked execute.py dispatches this source. No fitting, FINAL cache
discovery, policy selection or production/runtime mutation occurs here.
"""
from concurrent.futures import ProcessPoolExecutor
from collections import deque
import fcntl
import gzip
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import resource
import sys
import time
from types import ModuleType,SimpleNamespace

STATE={}
ROLES=('legacy','learned_pair')
SCRATCH=Path('/tmp/spaceapps-association-validation')


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()


def publish(path,value,root):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);root=Path(root)
    scope=SCRATCH if root.is_relative_to(SCRATCH)else root
    with (scope/'.disklock').open('a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if path.exists():raise ValueError('immutable research output already exists')
        temporary=path.with_suffix(path.suffix+'.tmp');payload=canonical(value)
        try:
            if path.suffix=='.gz':
                with temporary.open('wb')as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0,compresslevel=3)as stream:stream.write(payload)
            else:temporary.write_bytes(payload+b'\n')
            if sum(p.stat().st_size for p in scope.rglob('*')if p.is_file())>8*1024**3:raise ValueError('research scratch exceeds fixed8GiB shared budget')
            temporary.replace(path)
        finally:temporary.unlink(missing_ok=True)
    return dict(path=str(path.resolve()),sha256=digest(path),bytes=path.stat().st_size)


def initialize(frozen,output):
    for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[name]='1'
    allowed=sorted(os.sched_getaffinity(0))[:4]
    ordinal=multiprocessing.current_process()._identity[-1]if multiprocessing.current_process()._identity else 1
    os.sched_setaffinity(0,{allowed[(ordinal-1)%len(allowed)]})
    resource.setrlimit(resource.RLIMIT_AS,(7*1024**3//4,7*1024**3//4))
    # Execute every scientific source from the exact externally frozen bytes.
    ref=frozen['sources']['freeze'];source=Path(ref['path']).read_bytes()
    if hashlib.sha256(source).hexdigest()!=ref['sha256']:raise ValueError('worker preflight source differs')
    validator=ModuleType('association_worker_validator');validator.__file__=ref['path'];exec(compile(source,ref['path'],'exec'),validator.__dict__)
    load=lambda name,key:validator.exact(name,frozen['sources'][key])
    load('ml_inference','legacy_init')
    for name in ('contracts','detector','model'):load('ml_inference.'+name,'legacy_'+name)
    prep=load('ml_inference.prepare','prepare')
    load('training','training_init');native=load('training.evaluate_background','native_psf');sim=load('training.simulate_v2','simulate')
    package=ModuleType('association_physical');package.__path__=[];sys.modules[package.__name__]=package
    feature=load(package.__name__+'.features','features');package.features=feature
    model=load(package.__name__+'.model','runtime_model').load_ranker(Path(frozen['model']['artifact']['path']).parent)
    if model.metadata['sha256']!=frozen['model']['artifact']['sha256']:raise ValueError('research scorer differs')
    policies=load('association_policies','policies');accounting=load('association_accounting','accounting')
    import numpy as np
    # Model verification is complete before any simulator/FITS reader is called.
    STATE.update(frozen=frozen,output=Path(output),np=np,detector=sys.modules['ml_inference.detector'],prepare=prep.prepare,
        native=native,sim=sim,features=feature,model=model,policies=policies,accounting=accounting,
        latents=load('association_native_injections','native_injections'),legacy=load('association_legacy_helpers','native_helpers'),
        bank=sim.load_bank(frozen['calibration']['path']))


def predict(images,times,outlier=None,bloom=None):
    s=STATE;np=s['np'];started=time.perf_counter();cpu=time.process_time()
    residual=s['detector'].difference_frames(images,leave_one_out=True)
    peaks=[s['detector']._detect_peaks(d,np.isfinite(d),.8,4.,100,.8)for d in residual]
    pool,work=s['policies'].build_hypotheses(peaks,times,.5,60.,1.4,3)
    tracks=[t for links,t in pool]
    measured=s['features'].extract_features(images,times,tracks,psf_sigma=.8,outlier=outlier,bloom=bloom,residuals=residual)
    rich=np.asarray(measured['features_v4'],np.float32).reshape(-1,30)
    scores=s['model'].score(rich)
    a,aw=s['policies'].pair_exclusive(pool)
    b,bw=s['policies'].pair_exclusive(pool,scores)
    parity_started=time.process_time()
    legacy=s['detector'].link_detections(peaks,times,.5,60.,1.4,3)
    if [pool[i][1]for i in a]!=legacy:raise ValueError('actual frozen legacy candidate/order parity differs')
    direct=s['features'].extract_features(images,times,legacy,psf_sigma=.8,outlier=outlier,bloom=bloom,residuals=residual)
    direct_rich=np.asarray(direct['features_v4'],np.float32).reshape(-1,30)
    selected=np.asarray(a,dtype=int)
    if not np.array_equal(direct_rich,rich[selected])or not np.array_equal(s['model'].score(direct_rich),scores[selected]):
        raise ValueError('actual retained legacy feature/score parity differs')
    return dict(pool=pool,features=rich.tolist(),candidate_ids=measured['candidate_ids'],scores=scores.tolist(),
        kept={'legacy':[int(i)for i in a],'learned_pair':[int(i)for i in b]},policy_work={'legacy':aw,'learned_pair':bw},
        hypothesis_work=work,peaks_per_epoch=[len(p)for p in peaks],peak_cap_reached=any(len(p)>=100 for p in peaks),
        legacy_candidate_parity=True,legacy_feature_score_parity=True,parity_cpu_seconds=time.process_time()-parity_started,
        prediction_wall_seconds=time.perf_counter()-started,prediction_cpu_seconds=time.process_time()-cpu)


def labels_and_spans(prediction,truth,native):
    np=STATE['np'];labels=[];spans=[]
    for links,track in prediction['pool']:
        e=list(track.epochs);xy=np.asarray(track.positions_xy)
        distances=[np.linalg.norm(xy-np.asarray(path)[e],axis=1)for path in truth]
        matches=[i for i,d in enumerate(distances)if np.all(d<=1.5)]
        match=min(matches,key=lambda i:float(distances[i].mean()))if matches else(-2 if native else-1)
        labels.append(match)
        points=np.asarray(truth[match])[e]if match>=0 else None
        spans.append(float(np.max(np.linalg.norm(points[:,None]-points[None,:],axis=2)))if points is not None else None)
    return labels,spans


def emit(identity,images,times,truth,prediction,control=None):
    # Decisions/feature extraction/scoring above receive no truth coordinates.
    s=STATE;np=s['np'];native=identity['kind']!='synthetic';labels,spans=labels_and_spans(prediction,truth,native)
    attribution=dict(eligible=True,preexisting={r:False for r in ROLES})
    if control is not None:
        control_labels,_=labels_and_spans(control,truth,True)
        attribution=s['accounting'].common_attribution(control_labels,control['kept'])
    rows=[]
    for i,((links,t),features,score,candidate_id,label,span)in enumerate(zip(prediction['pool'],prediction['features'],prediction['scores'],prediction['candidate_ids'],labels,spans)):
        rows.append(dict(pool_index=i,candidate_id=candidate_id,links=[[int(epoch),int(index)]for epoch,index in links],epochs=list(t.epochs),
            positions_xy=[list(xy)for xy in t.positions_xy],features_v4=features,score=score,match=label,matched_truth_span_px=span,
            baseline_score=float(s['detector'].baseline_score(t))))
    counts={r:s['accounting'].policy_counts(labels,prediction['scores'],prediction['kept'][r],spans)for r in ROLES}
    latent=hashlib.sha256()
    for array in (images,times,*truth):latent.update(np.asarray(array,dtype='<f8').tobytes())
    result=dict(identity,truth_count=len(truth),expected_xy=[np.asarray(p).tolist()for p in truth],times_hours=np.asarray(times).tolist(),
        registered_shape=list(images.shape),latent_sha256=latent.hexdigest(),attribution_eligible=attribution['eligible'],
        preexisting_control_match=attribution['preexisting'],policies=counts,kept=prediction['kept'],
        hypothesis_count=len(rows),hypothesis_work=prediction['hypothesis_work'],policy_work=prediction['policy_work'],
        peaks_per_epoch=prediction['peaks_per_epoch'],peak_cap_reached=prediction['peak_cap_reached'],
        prediction_wall_seconds=prediction['prediction_wall_seconds'],prediction_cpu_seconds=prediction['prediction_cpu_seconds'],
        parity_cpu_seconds=prediction['parity_cpu_seconds'],legacy_candidate_parity=prediction['legacy_candidate_parity'],
        legacy_feature_score_parity=prediction['legacy_feature_score_parity'],
        worker_peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,error=None)
    key=identity['case_id'];root=s['output']
    full=publish(root/'full'/(key+'.json.gz'),dict(result,candidates=rows),root)
    union=set(prediction['kept']['legacy'])|set(prediction['kept']['learned_pair'])
    retained=[row for row in rows if row['pool_index']in union or row['match']>=0]
    compact=dict(result,candidates=retained,retained_union_count=len(union),offline_matched_fullpool_rows=sum(v>=0 for v in labels),
       full_pool_recovered_truths=len({v for v in labels if v>=0}),
       full_pool_resolved_truths=len({v for v,span in zip(labels,spans)if v>=0 and span>=3.}),
       full_pool=full,full_feature_matrix_sha256=hashlib.sha256(canonical(prediction['features'])).hexdigest(),
       retention='every field, union of BOTH retained pools plus ALL offline spatially matched hypotheses; no raw pixels')
    published=publish(root/'compact'/(key+'.json.gz'),compact,root)
    return dict(identity,compact=published,full_pool=full,error=None,truth_count=len(truth))


def failed(identity,phase,error):
    text=str(error)[:2000]
    row=dict(identity,truth_count=0 if identity['kind']=='native_control'else 1 if identity['kind']=='native'else None,
        error=dict(phase=phase,type=type(error).__name__,message=text),attribution_eligible=None,policies={},candidates=[])
    ref=publish(STATE['output']/'compact'/(identity['case_id']+'.json.gz'),row,STATE['output'])
    return dict(identity,compact=ref,error=row['error'],truth_count=row['truth_count'])


def synthetic(seed):
    identity=dict(kind='synthetic',seed=seed,case_id=f'synthetic-{seed}')
    try:
        images,times,truth,mode,metadata=STATE['sim'].simulate(seed,STATE['bank'],extended=seed%3==0,varying_psf=True)
        prediction=predict(images,times)
        return [emit(dict(identity,mode=mode,cadence_family=metadata['cadence_family'],simulation_metadata=metadata),images,times,truth,prediction)]
    except Exception as exc:return [failed(identity,'synthetic_generation_or_prediction',exc)]


def native_id(group,speed,direction,brightness):
    return dict(kind='native',parent_id=group['parent_id'],seed=group['seed'],speed_px_hour=speed,direction_id=direction,brightness=brightness,
                case_id=f"{group['parent_id']}-{speed:g}-{direction}-{brightness:g}")


def planned_native(group):
    return [native_id(group,s,d,b)for s in (.01,.03,.1,.3,1.,4.,10.,25.,50.)for d in (0,2,4)for b in (3.,6.,12.,24.,48.)]


def check_records(records,kind,groups=None):
    expected=([dict(kind='synthetic',seed=s,case_id=f'synthetic-{s}')for s in range(4100000,4101000)]if kind=='synthetic'else
        [identity for g in groups for identity in planned_native(g)+[dict(kind='native_control',parent_id=g['parent_id'],seed=g['seed'],case_id=g['parent_id']+'-control')]])
    mapping={r['case_id']:r for r in expected};seen=set()
    if len(records)!=len(expected):raise ValueError('planned research identity count differs')
    for row in records:
        key=row.get('case_id')
        if key not in mapping or key in seen or any(row.get(k)!=v for k,v in mapping[key].items()):
            raise ValueError('planned research identity is missing, duplicated or changed')
        seen.add(key)


def released_groups(frozen,handoff,validator):
    plan=validator.read(validator.checked(frozen['native_plan']))
    amendment=validator.read(validator.checked(frozen['native_seed_amendment']))
    if amendment['original_plan_sha256']!=frozen['native_plan']['sha256']:raise ValueError('native seed amendment plan differs')
    reservation=amendment['native_seed_reservation'];declared={g['group_id']:g for g in plan['groups']};groups=handoff['groups']
    if (len(groups)!=12 or set(reservation.values())!=set(range(4110001,4110013))
            or {g['parent_id']for g in groups}!=set(declared)or set(reservation)!=set(declared)):
        raise ValueError('native release parent cohort or reservation differs')
    for g in groups:
        original=declared[g['parent_id']]
        if (g['seed']!=reservation[g['parent_id']]or g['center']!=original['center']
                or g['split']!='quarantined_association_holdout'or g['detector']not in (1,2,3)or len(g['images'])!=8):
            raise ValueError('native released parent identity/geometry differs')
    excluded=plan['excluded_physical_obsids'];identifiers=[r['obs_id']for g in groups for r in g['images']]
    if len(excluded)!=438 or len(set(identifiers))!=96 or set(identifiers)&set(excluded):raise ValueError('native physical observations reused or excluded')
    return sorted(groups,key=lambda g:g['seed'])


def native(group):
    s=STATE;np=s['np'];control_id=dict(kind='native_control',parent_id=group['parent_id'],seed=group['seed'],case_id=group['parent_id']+'-control')
    output=[];completed=set()
    try:
        observations=[]
        for row in group['images']:
            if digest(row['path'])!=row['sha256']:raise ValueError('released native input hash differs')
            observations.append(dict(row,frame_id=Path(row['path']).stem,observation_id=row['obs_id']))
        center=group['center'];request=dict(schema_version=1,analysis_id='association-'+group['parent_id'],source=dict(kind='fits',observations=observations,
            region=dict(right_ascension_deg=center[0],declination_deg=center[1],width_arcmin=6.,height_arcmin=6.)),options=dict(pixel_scale_arcsec=6.15,mask_policy='motion'))
        stack=s['prepare'](request)
        if len(stack.frames)!=8:raise ValueError('native physical epoch count changed')
        source_by_id={r['obs_id']:r for r in group['images']}
        if {f['physical_observation_id']for f in stack.frames}!=set(source_by_id):raise ValueError('prepared native physical identities differ')
        for frame in stack.frames:
            original=source_by_id[frame['physical_observation_id']]
            if (frame['detector']!=group['detector']or frame['sha256']!=original['sha256']
                    or abs(frame['midpoint_mjd']-original['midpoint_mjd'])*86400>.0011):raise ValueError('prepared native detector/hash/midpoint differs')
        control=predict(stack.images,stack.times,stack.outlier,stack.bloom)
        output.append(emit(control_id,stack.images,stack.times,[],control));completed.add(control_id['case_id'])
        lookup={row['frame_id']:row for row in observations}
        natives=[s['native'].read_native(lookup[f['frame_id']]['path'],stack.grid,list(stack.images.shape[1:]))for f in stack.frames]
        science=SimpleNamespace(project_response=s['native'].project_response,add_injection=s['native'].add_projected_injection)
        parent=dict(parent_id=group['parent_id'],seed=group['seed'],_scope='independent_association_research')
        # The canonical generator draws ALL six directions; filter only AFTER
        # each immutable identity has been generated, without changing RNG.
        for identity,images,positions,error in s['latents'].native_latents(parent,stack,natives,science,list(stack.images.shape[1:]),s['legacy']):
            if identity['direction_id']not in (0,2,4):continue
            key=native_id(group,identity['speed_px_hour'],identity['direction_id'],identity['brightness'])
            if error is not None:
                output.append(failed(key,'native_injection',ValueError(json.dumps(error))));completed.add(key['case_id']);continue
            try:
                prediction=predict(images,stack.times,stack.outlier,stack.bloom)
                output.append(emit(dict(identity,**key),images,stack.times,[positions],prediction,control))
            except Exception as exc:output.append(failed(key,'native_prediction',exc))
            completed.add(key['case_id'])
    except Exception as exc:
        for identity in [control_id]+planned_native(group):
            if identity['case_id']not in completed:output.append(failed(identity,'native_setup_or_generation',exc))
    if len(output)!=136:raise ValueError('native planned record cardinality differs')
    return output


def bounded(pool,function,tasks,safe_call,limit=8):
    tasks=iter(tasks);pending=deque()
    for _ in range(limit):
        try:pending.append(pool.submit(safe_call,function,next(tasks)))
        except StopIteration:break
    while pending:
        yield pending.popleft().result()
        try:pending.append(pool.submit(safe_call,function,next(tasks)))
        except StopIteration:pass


def report(args,frozen,validator):
    output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
    if not output.is_relative_to(SCRATCH):raise ValueError('research output must use frozen shared scratch root outside Git')
    portable_path=output/'portable-fields.jsonl.gz';portable_tmp=portable_path.with_suffix('.gz.tmp')
    if portable_path.exists()or portable_tmp.exists():raise ValueError('immutable portable research evidence exists')
    portable_raw=portable_tmp.open('wb');portable=gzip.GzipFile(filename='',fileobj=portable_raw,mode='wb',mtime=0,compresslevel=6)
    portable.write(canonical(dict(record='header',freeze_sha256=frozen['_anchor'],protocol=frozen['_protocol'],
        model=frozen['model'],selection=frozen['selection'],format='One header followed by every compact field; source/full paths are provenance strings, no raw pixels'))+b'\n')
    manifests=[]
    for kind,path in [('synthetic',args.synthetic_manifest),('native',args.native_manifest)]:
        if path is None:
            manifests.append((kind,None));continue
        value=validator.read(path)
        if value['freeze_sha256']!=frozen['_anchor']or value['kind']!=kind:raise ValueError('research run manifest differs')
        manifests.append((kind,value))
    accounting=validator.exact('association_report_accounting',frozen['sources']['accounting']);result={}
    for kind,manifest in manifests:
        expected=1000 if kind=='synthetic'else 1620
        if manifest is None:
            result[kind]=dict(complete=False,planned_trials=expected,missing_trials=expected,reason='run unavailable; acquisition failure is not no coverage');continue
        groups=None
        if kind=='native':
            handoff=validator.read(validator.checked(manifest['handoff']));groups=released_groups(frozen,handoff,validator)
        check_records(manifest['outputs'],kind,groups)
        rows=[];controls=[]
        for ref in manifest['outputs']:
            path=validator.checked(ref['compact'])
            with gzip.open(path,'rt')as stream:field=json.load(stream)
            for key in ('case_id','seed','kind','parent_id','speed_px_hour','direction_id','brightness'):
                if ref.get(key)!=field.get(key):raise ValueError('compact research identity differs from run manifest')
            if field.get('error')is None:
                validator.checked(ref['full_pool'])
                if (field['full_pool']!=ref['full_pool']or field['legacy_candidate_parity']is not True
                        or field['legacy_feature_score_parity']is not True):raise ValueError('research full-pool binding/parity differs')
                verify_compact(field,accounting)
            portable.write(canonical(dict(record='field',domain=kind,field=field))+b'\n')
            slim={k:v for k,v in field.items()if k not in ('candidates','expected_xy','times_hours','simulation_metadata','kept')}
            (controls if field['kind']=='native_control'else rows).append(slim)
        if len(rows)!=expected:raise ValueError('missing planned research identities')
        domain=accounting.paired(rows);domain['peak_cap_trials']=sum(bool(r.get('peak_cap_reached'))for r in rows)
        domain['prediction_cpu_seconds']=sum(r.get('prediction_cpu_seconds',0.)for r in rows)
        domain['parity_cpu_seconds']=sum(r.get('parity_cpu_seconds',0.)for r in rows)
        domain['hypotheses_total']=sum(r.get('hypothesis_count',0)for r in rows)
        domain['full_pool_recovered_truths']=sum(r.get('full_pool_recovered_truths',0)for r in rows)
        domain['full_pool_resolved_truths']=sum(r.get('full_pool_resolved_truths',0)for r in rows)
        domain['prediction_wall_seconds_sum']=sum(r.get('prediction_wall_seconds',0.)for r in rows)
        domain['control_records']=len(controls);domain['controls']={role:sum(r.get('policies',{}).get(role,{}).get('candidate_rows',0)for r in controls)for role in ROLES}
        strata={}
        for key in (('parent_id','speed_px_hour','brightness')if kind=='native'else('mode','cadence_family')):
            for value in sorted({str(r.get(key))for r in rows}):
                selected=[r for r in rows if str(r.get(key))==value]
                # Strata are descriptive totals, never tiny-stratum population CIs.
                strata[key+':'+value]=dict(planned=len(selected),truths=sum(r.get('truth_count')or 0 for r in selected),
                  errors=sum(r.get('error')is not None for r in selected),
                  policies={role:{metric:sum(r.get('policies',{}).get(role,{}).get(metric,0)for r in selected)for metric in ('top1','top3','detected','resolved_top1','resolved_top3','unresolved_top1','unresolved_top3')}for role in ROLES})
        domain['strata']=strata;result[kind]=domain
    portable.close();portable_raw.close()
    if sum(p.stat().st_size for p in SCRATCH.rglob('*')if p.is_file())>8*1024**3:raise ValueError('research shared disk budget exceeded')
    portable_tmp.replace(portable_path)
    proof=dict(designation='Independent association RESEARCH; same frozen C596; no production promotion',freeze_sha256=frozen['_anchor'],reports=result,
        complete=all(domain.get('complete')is True for domain in result.values()),
        portable=dict(path=str(portable_path),sha256=digest(portable_path),bytes=portable_path.stat().st_size),
        limitation='Actual matched truth spans are descriptive; UNKNOWN workload is not precision; selection was DEV-informed, this holdout cannot be used for reselection',
        production_promotion_authorized=False)
    return publish(output/'research-report.json',proof,output)['path']


def verify_compact(field,accounting):
    """Independently measure retained/offline-match geometry without scoring."""
    import numpy as np
    rows=field['candidates'];mapping={row['pool_index']:i for i,row in enumerate(rows)}
    if len(mapping)!=len(rows):raise ValueError('duplicate retained research pool index')
    truth=[np.asarray(p)for p in field['expected_xy']];native=field['kind']!='synthetic'
    labels=[];spans=[]
    for row in rows:
        e=row['epochs'];xy=np.asarray(row['positions_xy'])
        ds=[np.linalg.norm(xy-p[e],axis=1)for p in truth];matches=[i for i,d in enumerate(ds)if np.all(d<=1.5)]
        label=min(matches,key=lambda i:float(ds[i].mean()))if matches else(-2 if native else-1)
        points=truth[label][e]if label>=0 else None
        span=float(np.max(np.linalg.norm(points[:,None]-points[None,:],axis=2)))if points is not None else None
        if label!=row['match']or span!=row['matched_truth_span_px']:raise ValueError('retained research spatial labels/span differ')
        labels.append(label);spans.append(span)
    scores=[row['score']for row in rows]
    for role in ROLES:
        kept=[mapping[i]for i in field['kept'][role]]
        if accounting.policy_counts(labels,scores,kept,spans)!=field['policies'][role]:raise ValueError('portable research budget accounting differs')


def run(args,frozen,validator):
    if globals().get('__source_sha256__')!=frozen['sources']['runner']['sha256']:raise ValueError('use exact checked research entry point')
    if args.kind=='report':return report(args,frozen,validator)
    output=Path(args.output).resolve();output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):raise ValueError('research run directory must be new and empty')
    handoff=None
    if args.kind=='native':
        if not args.authorize_native or not args.handoff or not args.handoff_sha256:raise ValueError('root-authorized exact native handoff required before native reads')
        path=validator.checked(dict(path=args.handoff,sha256=args.handoff_sha256));handoff=validator.read(path)
        groups=released_groups(frozen,handoff,validator);function=native;tasks=groups
    else:function=synthetic;tasks=range(4100000,4101000)
    if not output.is_relative_to(SCRATCH):raise ValueError('research output must use frozen shared scratch root outside Git')
    results=[];started=time.perf_counter()
    transport=validator.exact('association_safe_transport',frozen['sources']['worker_transport'])
    with ProcessPoolExecutor(max_workers=4,mp_context=multiprocessing.get_context('fork'),initializer=initialize,initargs=(frozen,str(output)))as pool:
        for records in bounded(pool,function,tasks,transport.safe_call):
            results.extend(records);print(json.dumps(dict(kind=args.kind,planned_records_finished=len(results),elapsed_seconds=time.perf_counter()-started)),flush=True)
    expected=1000 if args.kind=='synthetic'else 1632
    check_records(results,args.kind,groups if args.kind=='native'else None)
    validator.validate(args.freeze,args.anchor)
    value=dict(schema_version=1,kind=args.kind,freeze_sha256=frozen['_anchor'],planned=expected,outputs=results,
        complete=all(r['error']is None for r in results),error_records=sum(r['error']is not None for r in results),
        elapsed_seconds=time.perf_counter()-started,handoff=dict(path=args.handoff,sha256=args.handoff_sha256)if handoff else None)
    return publish(output/'run-manifest.json',value,output)['path']
