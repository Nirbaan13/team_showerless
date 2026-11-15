"""Fixed-model DEVELOPMENT threshold tradeoffs; no fitting/default/promotion change."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
import gzip
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import resource
import shutil
import time
import numpy as np
from ml_inference.detector import difference_frames, _detect_peaks, link_detections
from ml_inference.model import load_ranker as load_c13
from ml_inference.prepare import prepare
from training.simulate_v2 import simulate, load_bank
from training.evaluate_background import read_native, project_response, add_projected_injection
from ml.pvusatov.experiments.v4.detection.features import extract_features, FEATURE_NAMES
from ml.pvusatov.experiments.v4.detection.runtime_model import load_ranker as load_c596

REPO = Path(__file__).resolve().parents[5]
INF = REPO / 'ml/pvusatov/backend/inference'
HERE = Path(__file__).resolve().parent
SCRATCH = Path('/tmp/spaceapps-v4-operating-points')
THRESHOLDS = (3.,4.,5.,6.)
C13 = 'c13ba9577273610ab09ad4c962322118b27bb06c1a34933ef4252b9e643bd204'
C596 = 'c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35'
CACHE_SHAS = {'v4-train01':'efff6a122afb7537c6c36357dcbce465c199d977979808f978534f57ec0f0368',
              'v4-train03':'008327a0785202f5a91a5fdefa50e12dc46e3933792931cbc7d1f3f4f6f85f82'}
STATE = {}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''):h.update(block)
    return h.hexdigest()


def atomic(path, value):
    path = Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    text = json.dumps(value,allow_nan=False,separators=(',',':'))
    if path.suffix == '.gz':
        with gzip.open(temporary,'wt') as stream:stream.write(text+'\n')
    else:temporary.write_text(text+'\n')
    temporary.replace(path)


def image_hash(images):
    return hashlib.sha256(memoryview(np.ascontiguousarray(images)).cast('B')).hexdigest()


def initialize(path, sha):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha:raise ValueError('protocol SHA changed')
    protocol = json.loads(raw)
    if protocol['synthetic_seeds'] != list(range(3805000,3805100)) or protocol['min_snr'] != list(THRESHOLDS):raise ValueError('undeclared DEVELOPMENT matrix')
    if any(digest(p) != h for p,h in protocol['source_sha256'].items()):raise ValueError('source closure changed')
    for model in protocol['models'].values():
        if digest(Path(model['directory'])/'ranker.onnx') != model['artifact_sha256'] or digest(Path(model['directory'])/'metadata.json') != model['metadata_sha256']:raise ValueError('fixed model snapshot changed')
    STATE['protocol'] = protocol
    STATE['C13'] = load_c13(protocol['models']['C13']['directory'])
    STATE['C596'] = load_c596(protocol['models']['C596']['directory'])
    if STATE['C13'].metadata['sha256'] != C13 or STATE['C596'].metadata['sha256'] != C596:raise ValueError('fixed artifact differs')
    if STATE['C596'].metadata['selected_feature_indices'] != list(range(27)):raise ValueError('selected27-feature contract differs')
    STATE['bank'] = load_bank(INF/'training/calibration/instrument-epsf-bank.npz')


def label_tracks(tracks, truth, native):
    labels = []
    for t in tracks:
        ds = [np.linalg.norm(np.asarray(t.positions_xy)-np.asarray(p)[list(t.epochs)],axis=1) for p in truth]
        good = [i for i,d in enumerate(ds) if np.all(d<=1.5)]
        labels.append(min(good,key=lambda i:float(np.mean(ds[i]))) if good else (-2 if native else -1))
    return labels


def recovery(labels, order):
    count = lambda indexes:len({labels[i] for i in indexes if labels[i]>=0})
    return dict(detected=count(range(len(labels))),top1=count(list(order)[:1]),top3=count(list(order)[:3]))


def measure(images, times, outlier=None, bloom=None):
    residuals = difference_frames(images,leave_one_out=True); profiles = {}
    for threshold in THRESHOLDS:
        started = time.perf_counter(); cpu = time.process_time(); errors = []
        peaks = [_detect_peaks(d,np.isfinite(d),.8,threshold,100,.8) for d in residuals]
        try:tracks = link_detections(peaks,times,.5,60.,1.4,3)
        except Exception as exc:tracks = []; errors.append(dict(phase='linking',type=type(exc).__name__,message=str(exc)))
        legacy = np.asarray([t.features() for t in tracks],np.float32).reshape(-1,6)
        scores = {}; rich = None; ids = []
        try:scores['C13'] = STATE['C13'].score(legacy).tolist()
        except Exception as exc:scores['C13'] = None; errors.append(dict(phase='C13_scoring',type=type(exc).__name__,message=str(exc)))
        try:
            result = extract_features(images,times,tracks,psf_sigma=.8,outlier=outlier,bloom=bloom,residuals=residuals)
            rich = np.asarray(result['features_v4'],np.float32)
            np.testing.assert_array_equal(rich[:,:6],legacy)
            ids = result['candidate_ids']; scores['C596'] = STATE['C596'].score(rich).tolist()
        except Exception as exc:scores['C596'] = None; errors.append(dict(phase='physical_features_or_C596',type=type(exc).__name__,message=str(exc)))
        profiles[str(threshold)] = dict(tracks=tracks,features=legacy.tolist(),features_v4=None if rich is None else rich.tolist(),candidate_ids=ids,
            scores=scores,peaks_per_epoch=[len(p) for p in peaks],peak_cap_reached=any(len(p)>=100 for p in peaks),errors=errors,
            cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-started)
    return profiles


def finish(profiles, truth, native, controls=None):
    output = {}
    for threshold, source in profiles.items():
        tracks = source['tracks']; labels = label_tracks(tracks,truth,native)
        preexisting = controls is not None and any(x>=0 for x in label_tracks(controls[threshold]['tracks'],truth,True))
        models = {}
        for name in ('C13','C596'):
            scores = source['scores'][name]
            order = np.argsort(-np.asarray(scores),kind='stable') if scores is not None else []
            models[name] = recovery(labels,order)
        output[threshold] = {**{k:v for k,v in source.items() if k!='tracks'},'candidate_rows':len(tracks),'matches':labels,
            'candidate_epochs':[list(t.epochs) for t in tracks],'candidate_positions_xy':[t.positions_xy for t in tracks],
            'models':models,'preexisting_control_match':preexisting,'attribution_eligible':not preexisting,
            'known_unmatched_rows':sum(x<0 for x in labels) if not native else None,
            'unknown_rows':sum(x<0 for x in labels) if native else None}
    return output


def record(identity, images, times, truth, native, outlier=None, bloom=None, controls=None, profiles=None):
    started = time.perf_counter()
    # All candidate generation/features/both-model predictions finish BEFORE truth matching.
    if profiles is None:profiles = measure(images,times,outlier,bloom)
    return dict(identity,truth_count=len(truth),expected_xy=[np.asarray(p).tolist() for p in truth],times_hours=np.asarray(times).tolist(),shape=list(images.shape),
        image_sha256=image_hash(images),finite_mask_sha256=image_hash(np.isfinite(images)),
        quality_masks=dict(outlier=None if outlier is None else image_hash(outlier),bloom=None if bloom is None else image_hash(bloom)),
        profiles=finish(profiles,truth,native,controls),wall_seconds=time.perf_counter()-started,rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)


def native_task(parent):
    info = STATE['protocol']['native'][parent]
    for row in info['input_sources']:
        if digest(row['path']) != row['sha256']:raise ValueError('TRAIN FITS bytes changed before reader')
    ra,dec = info['center_deg']
    stack = prepare(dict(schema_version=1,analysis_id='operating-'+parent,source=dict(kind='fits',observations=info['input_sources'],region=dict(right_ascension_deg=ra,declination_deg=dec,width_arcmin=6.,height_arcmin=6.)),options=info['preparation_options']))
    np.testing.assert_array_equal(stack.times,info['times_hours'])
    if list(stack.images.shape) != info['registered_shape']:raise ValueError('native shape differs')
    lookup = {r['frame_id']:r for r in info['input_sources']}
    natives = [read_native(lookup[f['frame_id']]['path'],stack.grid,stack.images.shape[1:]) for f in stack.frames]
    controls = measure(stack.images,stack.times,stack.outlier,stack.bloom)
    control_record = record(dict(kind='native_control',parent_id=parent,seed=info['seed']),stack.images,stack.times,[],True,stack.outlier,stack.bloom,profiles=controls)
    rows = [control_record]; rng = np.random.default_rng(info['seed']); h,w = stack.images.shape[1:]
    noise = np.asarray([1.4826*np.median(abs(v-np.median(v))) for image in stack.images for v in [image[np.isfinite(image)]]])
    if not np.isfinite(noise).all() or np.any(noise<=0):raise ValueError('nonpositive TRAIN background MAD')
    for speed in (.1,1.,10.):
        for direction in range(3):
            origin = rng.uniform([8,8],[w-8,h-8]); angle = rng.uniform(0,2*np.pi); velocity = speed*np.asarray([np.cos(angle),np.sin(angle)])
            xy = origin+stack.times[:,None]*velocity
            projected = [project_response(n,stack.grid,p) for n,p in zip(natives,xy)]
            response = np.asarray([p[0] for p in projected]); peaks = np.max(response,axis=(1,2))
            usable = np.asarray([bool(0<=x<w and 0<=y<h and np.isfinite(image[y,x])) for image,(x,y) in zip(stack.images,np.rint(xy).astype(int))])
            supported = peaks[usable & (peaks>0)]
            if not len(supported):supported = peaks[peaks>0]
            if not len(supported):supported = np.asarray([project_response(n,stack.grid,np.asarray([w/2,h/2]))[0].max() for n in natives]); supported = supported[supported>0]
            typical = float(np.median(supported)) if len(supported) else 1.
            for brightness in (3.,12.,48.):
                flux = brightness*float(np.median(noise))/typical
                images = add_projected_injection(stack.images,response,flux)
                for image in images:image-=np.nanmedian(image)
                identity = dict(kind='native',parent_id=parent,seed=info['seed'],speed_px_hour=speed,direction_id=direction,brightness=brightness,
                    origin_xy=origin.tolist(),velocity_xy_hour=velocity.tolist(),injected_flux=flux,usable_center_epochs=int(usable.sum()))
                rows.append(record(identity,images,stack.times,[xy],True,stack.outlier,stack.bloom,controls))
    return rows


def _one(task):
    if task[0]=='native':rows = native_task(task[1])
    else:
        seed = task[1]
        if not 3805000<=seed<3805100:raise ValueError('only reserved DEVELOPMENT synthetic seeds')
        images,times,truth,mode,metadata = simulate(seed,STATE['bank'],extended=seed%3==0,varying_psf=True)
        rows = [record(dict(kind='synthetic',parent_id=str(seed),seed=seed,mode=mode,simulation_metadata=metadata),images,times,truth,False)]
    paths = []
    for row in rows:
        key = str(row['seed']) if row['kind']=='synthetic' else f"{row['kind']}-{row['seed']}-{row.get('speed_px_hour','control')}-{row.get('direction_id',0)}-{row.get('brightness',0)}"
        path = SCRATCH/'fields'/(key+'.json.gz'); atomic(path,row)
        compact = {k:v for k,v in row.items() if k not in ('profiles','expected_xy','simulation_metadata')}
        compact['profiles'] = {t:{k:p[k] for k in ('candidate_rows','models','peak_cap_reached','errors','cpu_seconds','wall_seconds','attribution_eligible','preexisting_control_match','peaks_per_epoch','known_unmatched_rows','unknown_rows')} for t,p in row['profiles'].items()}
        paths.append(dict(path=str(path),sha256=digest(path),field=compact))
    return paths



def one(task):
    try:
        return _one(task)
    except Exception as exc:
        # A failed parent remains a fully enumerated failed attempt, not a dropped cohort.
        error = dict(phase='task_setup_or_generation',type=type(exc).__name__,message=str(exc))
        if task[0] == 'synthetic':
            identities = [dict(kind='synthetic',parent_id=str(task[1]),seed=task[1],truth_count=None)]
        else:
            seed = STATE['protocol']['native'][task[1]]['seed']
            identities = [dict(kind='native_control',parent_id=task[1],seed=seed,truth_count=0)]
            identities += [dict(kind='native',parent_id=task[1],seed=seed,truth_count=1,speed_px_hour=s,direction_id=d,brightness=b)
                for s in (.1,1.,10.) for d in range(3) for b in (3.,12.,48.)]
        output = []
        for index,identity in enumerate(identities):
            profiles = {str(t):dict(candidate_rows=0,models={m:dict(detected=0,top1=0,top3=0)for m in ('C13','C596')},
                peak_cap_reached=False,errors=[error],cpu_seconds=0.,wall_seconds=0.,attribution_eligible=False,
                preexisting_control_match=None,peaks_per_epoch=[],known_unmatched_rows=None,unknown_rows=None)for t in THRESHOLDS}
            field = dict(identity,profiles=profiles,task_error=error,wall_seconds=0.,rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
            path = SCRATCH/'fields'/f"failed-{identity['seed']}-{index}.json.gz";atomic(path,field)
            output.append(dict(path=str(path),sha256=digest(path),field=field))
        return output


def summarize(entries):
    result = {}
    for kind in ('synthetic','native','native_control'):
        fields = [e['field'] for e in entries if e['field']['kind']==kind]; profiles = {}
        for threshold in map(str,THRESHOLDS):
            ps = [f['profiles'][threshold] for f in fields]
            common = [i for i,f in enumerate(fields) if f['profiles']['4.0']['attribution_eligible'] and ps[i]['attribution_eligible']]
            profiles[threshold] = dict(allplanned=len(fields),truth_count=sum(f['truth_count'] or 0 for f in fields),missing_truth_fields=sum(f['truth_count'] is None for f in fields),
                candidate_rows=sum(p['candidate_rows'] for p in ps),caps=sum(p['peak_cap_reached'] for p in ps),errors=sum(bool(p['errors']) for p in ps),
                cpu_seconds=sum(p['cpu_seconds'] for p in ps),common_attributable_vs4=len(common),models={name:{metric:sum(p['models'][name][metric] for p in ps) for metric in ('detected','top1','top3')} for name in ('C13','C596')},
                common_models={name:{metric:sum(ps[i]['models'][name][metric] for i in common) for metric in ('detected','top1','top3')} for name in ('C13','C596')})
        result[kind] = dict(independent_parents=len({f['parent_id'] for f in fields}),profiles=profiles)
    return result


def plan():
    SCRATCH.mkdir(parents=True,exist_ok=True); models = {}
    for name,source,expected in [('C13',REPO/'ml/pvusatov/releases/v3/model',C13),('C596',REPO/'ml/pvusatov/releases/v4/model',C596)]:
        if digest(source/'ranker.onnx') != expected:raise ValueError('fixed graph differs')
        target = SCRATCH/'models'/name; target.mkdir(parents=True,exist_ok=True)
        for filename in ('ranker.onnx','metadata.json'):
            destination = target/filename
            if destination.exists() and destination.read_bytes() != (source/filename).read_bytes():raise ValueError('existing fixed snapshot differs')
            if not destination.exists():shutil.copyfile(source/filename,destination)
        models[name] = dict(directory=str(target),artifact_sha256=digest(target/'ranker.onnx'),metadata_sha256=digest(target/'metadata.json'))
    native = {}
    for parent,sha in CACHE_SHAS.items():
        path = Path('/tmp/spaceapps-v4-native-cache/main-v2')/(parent+'-both.json.gz')
        if digest(path) != sha:raise ValueError('safe TRAIN cache differs')
        with gzip.open(path,'rt') as stream:cache = json.load(stream)
        if cache['partition']!='train':raise ValueError('only declared TRAIN parents')
        native[parent] = {k:cache[k] for k in ('input_sources','center_deg','preparation_options','times_hours','registered_shape','downloads_manifest')}
        native[parent].update(seed=3805201 if parent=='v4-train01' else 3805203,source_cache=str(path),source_cache_sha256=sha)
    sources = [Path(__file__),HERE/'test_study.py',INF/'training/simulate_v2.py',INF/'training/evaluate_background.py',
        INF/'training/calibration/instrument-epsf-bank.npz',REPO/'ml/pvusatov/experiments/v4/detection/features.py',REPO/'ml/pvusatov/experiments/v4/detection/runtime_model.py'] + sorted((INF/'ml_inference').glob('*.py'))
    return dict(schema_version=1,designation='DEVELOPMENT fixed-model threshold tradeoff, no fitting/default/promotion change',
        synthetic_seeds=list(range(3805000,3805100)),min_snr=list(THRESHOLDS),models=models,native=native,
        source_sha256={str(p.resolve()):digest(p) for p in sources},full_feature_names=list(FEATURE_NAMES),selected_feature_indices=list(range(27)),
        generator=dict(extended='seed%3==0',varying_psf=True,shared_latents_across_thresholds=True),
        detector=dict(psf_sigma=.8,max_peaks=100,min_epochs=3,min_speed=.5,max_speed=60.,match_radius=1.4,min_support=.8,leave_one_out=True),
        native_matrix=dict(speeds=[.1,1.,10.],directions=[0,1,2],brightness=[3.,12.,48.],trials_per_parent=27,recenter=False,normalization='same declared supported_finite_center_v1 fallback'),
        bootstrap=dict(seed=3805099,resamples=5000,unit='whole independent synthetic parent',metric='delta recoveredobjects perfield vs threshold4'),
        limitations=['real unmatched controls UNKNOWN, no real precision','nativeN2 descriptive only','thresholds compared prospectively, default4/gates unchanged','synthetic instrument quality masks absent; native actual masks passed'])


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--workers',type=int,default=4);parser.add_argument('--plan-only',action='store_true');args = parser.parse_args()
    if not 1<=args.workers<=4:raise ValueError('bounded1..4workers')
    value = plan(); protocol = HERE/'protocol.json'
    if protocol.exists():
        if json.loads(protocol.read_text()) != value:raise ValueError('existing immutable protocol differs')
    else:atomic(protocol,value)
    sha = digest(protocol)
    if args.plan_only:print(json.dumps(dict(protocol=str(protocol),sha256=sha)));return
    output = HERE/'results/summary.json'
    if output.exists():raise ValueError('immutable completed study exists')
    tasks = [('synthetic',s) for s in value['synthetic_seeds']] + [('native',p) for p in value['native']]
    started = time.perf_counter(); entries = []
    with ProcessPoolExecutor(max_workers=args.workers,initializer=initialize,initargs=(str(protocol),sha)) as pool:
        for rows in pool.map(one,tasks,chunksize=1):
            entries.extend(rows);print(json.dumps(dict(completed_fields=len(entries),task=rows[0]['field']['parent_id'],elapsed=time.perf_counter()-started)),flush=True)
    if any(digest(p)!=h for p,h in value['source_sha256'].items()):raise ValueError('source changed mid-study')
    report = dict(protocol_sha256=sha,source_sha256=value['source_sha256'],models=value['models'],summary=summarize(entries),fields=entries,
        allplanned=dict(synthetic=100,native=54,native_control=2),elapsed_seconds=time.perf_counter()-started)
    atomic(output,report);print(json.dumps(dict(output=str(output),sha256=digest(output),summary=report['summary'],elapsed=report['elapsed_seconds'])),flush=True)


if __name__=='__main__':main()
