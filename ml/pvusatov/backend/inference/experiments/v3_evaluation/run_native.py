"""Freeze-gated paired native evaluation. No network, fitting or implicit data discovery."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from collections import deque
import gzip
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import tempfile
import time
import resource
from types import SimpleNamespace

V2_SHA='dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9'
SPEEDS=[.01,.03,.1,.3,1.,4.,10.,25.,50.]
BRIGHTNESS=[3.,6.,12.,24.,48.]
MATRIX=dict(speeds_px_hour=SPEEDS,directions_per_speed=6,brightness=BRIGHTNESS,
            recenter_into_coverage=False,brightness_rule='supported_finite_center_v1')
OPTIONS=dict(min_snr=4.,max_peaks=100,max_speed=60.,match_radius=1.4,min_epochs=3,
             min_support=.8,leave_one_out=True)
SOURCES=dict(run_native='experiments/v3_evaluation/run_native.py',
             run_synthetic='experiments/v3_evaluation/run_synthetic.py',
             paired='experiments/v3_evaluation/paired.py',detector='ml_inference/detector.py',
             prepare='ml_inference/prepare.py',model='ml_inference/model.py',contracts='ml_inference/contracts.py',
             inference_init='ml_inference/__init__.py',inference_main='ml_inference/__main__.py',
             pipeline='ml_inference/pipeline.py',render='ml_inference/render.py',cli='ml_inference/cli.py',
             training_init='training/__init__.py',
             simulate_v2='training/simulate_v2.py',evaluate_background='training/evaluate_background.py')
ROLES=('baseline','candidate')
PROFILES=('primary','secondary')


def digest(path):
    sha=hashlib.sha256()
    with Path(path).open('rb')as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):sha.update(block)
    return sha.hexdigest()


def versions():
    return {'python':platform.python_version(),**{name:importlib.metadata.version(name)
            for name in ['numpy','scipy','astropy','onnxruntime','pillow']}}


def _json(path):
    def invalid_constant(value):raise ValueError('nonfinite JSON constant '+value)
    try:return json.loads(Path(path).read_text(),parse_constant=invalid_constant)
    except (OSError,ValueError)as exc:raise ValueError('freeze JSON unavailable or invalid: '+str(path))from exc


def _validate_freeze(path,expected_sha256):
    """Read/hash bytes only; never import a scientific reader, simulator or model."""
    path=Path(path).resolve()
    try:
        if not isinstance(expected_sha256,str)or not re.fullmatch('[0-9a-f]{64}',expected_sha256):
            raise ValueError('freeze requires an external SHA256 trust anchor')
        if digest(path)!=expected_sha256:raise ValueError('freeze SHA256 mismatch')
    except OSError as exc:raise ValueError('freeze file unavailable')from exc
    freeze=_json(path)
    if not isinstance(freeze,dict)or freeze.get('schema_version')!=1 or freeze.get('status')!='frozen':
        raise ValueError('freeze must have schema_version1 and status frozen')
    scope=freeze.get('scope')
    if scope not in ['development','final']:raise ValueError('freeze scope is required')
    if scope=='final'and freeze.get('authorized_final')is not True:raise ValueError('freeze final execution unauthorized')
    if scope=='development'and freeze.get('authorized_final')is not False:raise ValueError('development freeze must forbid final execution')
    try:
        root=Path(freeze['package_root']).resolve()
        if '/ml/pvusatov/'not in root.as_posix()+'/':raise ValueError('source package_root must be namespaced')
        runtime=freeze['runtime']
        if (set(runtime)!= {'workers','math_threads','max_frames','max_grid'}or
            type(runtime['workers'])is not int or not 1<=runtime['workers']<=6 or
            runtime['math_threads']!=1 or runtime['max_frames']!=32 or runtime['max_grid']!=512):
            raise ValueError('freeze runtime bounds are invalid')
        expected={name:{**OPTIONS,'min_speed':speed}for name,speed in [('primary',.5),('secondary',.005)]}
        if freeze['options']!=expected:raise ValueError('freeze profiles differ from fixed paired options')
        if freeze['native']['matrix']!=MATRIX:raise ValueError('freeze native matrix differs')
        region=freeze['native']['region']
        if set(region)!= {'width_arcmin','height_arcmin','pixel_scale_arcsec','mask_policy'}:
            raise ValueError('freeze native region/options missing')
        if (any(not isinstance(region[k],(float,int))or not math.isfinite(region[k])or region[k]<=0
                for k in ['width_arcmin','height_arcmin','pixel_scale_arcsec'])or region['mask_policy']!='motion'):
            raise ValueError('freeze native region/options invalid')
        shape=[math.ceil(region[k]*60/region['pixel_scale_arcsec'])for k in ['height_arcmin','width_arcmin']]
        if max(shape)>512 or min(shape)<17:raise ValueError('freeze grid is outside bounded injection support')
        parents=freeze['native']['parents'];ids=[p['parent_id']for p in parents];seeds=[p['seed']for p in parents]
        if not parents or ids!=sorted(set(ids))or any(not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,127}',v)for v in ids):
            raise ValueError('freeze parent IDs must be unique and canonical sorted')
        if len(set(seeds))!=len(seeds)or any(type(seed)is not int for seed in seeds):raise ValueError('freeze parent seeds invalid')
        synthetic=freeze['synthetic'];synthetic_seeds=synthetic['seeds']
        if not synthetic_seeds or synthetic_seeds!=sorted(set(synthetic_seeds))or any(type(seed)is not int for seed in synthetic_seeds):
            raise ValueError('freeze synthetic seed list invalid')
        if scope=='final':
            if len(parents)!=10 or seeds!=list(range(2200001,2200011)):raise ValueError('freeze final native map differs')
            if synthetic_seeds!=list(range(2000000,2002000)):raise ValueError('freeze final synthetic range differs')
        elif any(not 1900000<=seed<2000000 for seed in seeds+synthetic_seeds):
            raise ValueError('development freeze only permits1900000-series seeds')
        if synthetic['generator']!=dict(extended_every_nth_field=3,varying_psf=True):
            raise ValueError('freeze synthetic generator differs')
        if freeze['versions']!=versions():raise ValueError('freeze software versions differ')
        if set(freeze['models'])!=set(ROLES):raise ValueError('freeze needs exactly two systems')
        if freeze['models']['baseline']['psf_sigma']!=1.2 or freeze['models']['candidate']['psf_sigma']not in [1.2,.8]:
            raise ValueError('freeze sigma selection invalid')
    except (KeyError,TypeError,AttributeError)as exc:raise ValueError('freeze required schema is missing')from exc

    def checked(ref,label):
        if not isinstance(ref,dict)or set(ref)!= {'path','sha256'}or not re.fullmatch('[0-9a-f]{64}',str(ref.get('sha256',''))):
            raise ValueError('freeze invalid file reference: '+label)
        location=Path(ref['path']);location=(path.parent/location).resolve()if not location.is_absolute()else location.resolve()
        try:
            if digest(location)!=ref['sha256']:raise ValueError('freeze file SHA256 mismatch: '+label)
        except OSError as exc:raise ValueError('freeze required file unavailable: '+label)from exc
        ref['path']=str(location)
        return location

    if set(freeze.get('sources',{}))!=set(SOURCES):raise ValueError('freeze required source hashes missing')
    for name,relative in SOURCES.items():
        source=checked(freeze['sources'][name],'source '+name)
        if not source.is_relative_to(root)or source!=(root/relative).resolve():raise ValueError('freeze source does not match configured package: '+name)
    if Path(__file__).resolve()!=Path(freeze['sources']['run_native']['path']):raise ValueError('freeze runner source path mismatch')
    for role,model in freeze['models'].items():
        checked(model['artifact'],role+' artifact');metadata=checked(model['metadata'],role+' metadata')
        document=_json(metadata)
        if not isinstance(document,dict)or document.get('sha256')!=model['artifact']['sha256']:raise ValueError('freeze model metadata artifact hash mismatch')
        model['_metadata_document']=document
        if 'detector_profile'in document and document['detector_profile']!={**freeze['options']['primary'],'psf_sigma':model['psf_sigma']}:
            raise ValueError('freeze metadata detector profile differs from frozen primary')
    if scope=='final'and freeze['models']['baseline']['artifact']['sha256']!=V2_SHA:
        raise ValueError('freeze final baseline differs from deployed v2')
    for index,ref in enumerate(freeze.get('provenance_files',[])):checked(ref,'selection provenance '+str(index))
    acquisition=freeze['native'].get('acquisition_manifests')
    if not isinstance(acquisition,list)or not acquisition:raise ValueError('freeze acquisition manifest hashes missing')
    for index,ref in enumerate(acquisition):checked(ref,'acquisition manifest '+str(index))
    for parent in parents:
        try:
            center=parent['center_deg']
            if len(center)!=2 or not all(isinstance(v,(float,int))and math.isfinite(v)for v in center)or not 0<=center[0]<360 or not -90<center[1]<90:
                raise ValueError('freeze native center invalid')
            download_path=Path(parent['downloads_manifest']['path'])
            if scope=='development'and any(part.lower().startswith(('final','quarant'))for part in download_path.parts):
                raise ValueError('development freeze cannot access final native manifests')
            manifest=checked(parent['downloads_manifest'],parent['parent_id']+' downloads manifest');downloads=_json(manifest)
            if not isinstance(downloads,list)or not 3<=len(downloads)<=32 or(scope=='final'and len(downloads)!=8):
                raise ValueError('freeze native exposure count invalid')
            observations=[]
            for index,row in enumerate(downloads):
                if not isinstance(row,dict):raise ValueError('freeze download row invalid')
                location=Path(row['path']);location=(manifest.parent/location).resolve()if not location.is_absolute()else location.resolve()
                if scope=='development'and any(part.lower().startswith(('final','quarant'))for part in location.parts):
                    raise ValueError('development freeze cannot access final native pixels')
                ref=dict(path=str(location),sha256=row['sha256']);checked(ref,parent['parent_id']+' observation '+str(index))
                observations.append({**row,**ref,'frame_id':str(row.get('frame_id')or location.stem)})
            if len({r['sha256']for r in observations})!=len(observations):raise ValueError('freeze contains repeated exposure bytes')
            parent['_observations']=observations
        except (KeyError,TypeError)as exc:raise ValueError('freeze native parent schema invalid')from exc
    checked(synthetic['calibration_bank'],'synthetic calibration')
    freeze['_sha256']=expected_sha256;freeze['_path']=str(path);freeze['_shape']=shape;freeze['package_root']=str(root)
    return freeze



def validate_freeze(path,expected_sha256):
    try:return _validate_freeze(path,expected_sha256)
    except (KeyError,TypeError,AttributeError,OverflowError)as exc:raise ValueError('freeze schema invalid')from exc


def _threads():
    for name in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[name]='1'



def _bounded_map(pool,function,tasks,limit):
    """Ordered bounded submission, including on Python3.12 without map.buffersize."""
    iterator=iter(tasks);pending=deque()
    for _ in range(limit):
        try:pending.append(pool.submit(function,next(iterator)))
        except StopIteration:break
    while pending:
        yield pending.popleft().result()
        try:pending.append(pool.submit(function,next(iterator)))
        except StopIteration:pass


def _science(freeze):
    """Only invoked after complete freeze validation."""
    _threads();sys.path.insert(0,freeze['package_root'])
    modules={name:importlib.import_module(module)for name,module in dict(detector='ml_inference.detector',
        prepare='ml_inference.prepare',model='ml_inference.model',contracts='ml_inference.contracts',
        inference_init='ml_inference',training_init='training',simulate_v2='training.simulate_v2',
        evaluate_background='training.evaluate_background').items()}
    for name,module in modules.items():
        if Path(module.__file__).resolve()!=Path(freeze['sources'][name]['path']):raise ValueError('freeze imported source path differs: '+name)
    models={};errors={}
    for role,model in freeze['models'].items():
        try:
            with tempfile.TemporaryDirectory(prefix='frozen-evaluation-model-')as temporary:
                shutil.copyfile(model['artifact']['path'],Path(temporary)/'ranker.onnx')
                shutil.copyfile(model['metadata']['path'],Path(temporary)/'metadata.json')
                if digest(Path(temporary)/'ranker.onnx')!=model['artifact']['sha256']or digest(Path(temporary)/'metadata.json')!=model['metadata']['sha256']:
                    raise ValueError('frozen model changed after preflight validation')
                models[role]=modules['model'].load_ranker(temporary)
        except Exception as exc:errors[role]=_error('model_loading',exc)
    return SimpleNamespace(prepare=modules['prepare'].prepare,find_candidates=modules['detector'].find_candidates,
        difference_frames=modules['detector'].difference_frames,detect_peaks=modules['detector']._detect_peaks,
        baseline_score=modules['detector'].baseline_score,read_native=modules['evaluate_background'].read_native,
        project_response=modules['evaluate_background'].project_response,add_injection=modules['evaluate_background'].add_projected_injection,
        simulate=modules['simulate_v2'].simulate,load_bank=modules['simulate_v2'].load_bank,models=models,model_errors=errors)


def _error(phase,exc):return dict(phase=phase,type=type(exc).__name__,message=str(exc)[:1000])


class AtomicCache:
    """Stream one planned field at a time; never buffer270 candidate-heavy trials."""
    def __init__(self,path,metadata):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists():raise ValueError('refusing to overwrite evaluation cache: '+str(path))
        handle=tempfile.NamedTemporaryFile(dir=self.path.parent,prefix='.'+self.path.name+'.',delete=False)
        self.temporary=Path(handle.name);self.handle=handle
        self.stream=gzip.GzipFile(fileobj=handle,mode='wb',mtime=0);self.first=True
        self.control_capped=bool(metadata.get('control_diagnostics',{}).get('peak_cap_reached'))
        encoded=json.dumps(metadata,allow_nan=False,separators=(',',':'))[:-1]+',"fields":['
        self.stream.write(encoded.encode())
        self.summary=dict(planned=0,candidate_rows=0,spatial_recovered=0,spatial_recovered_trials=0,resolved_truth_span_ge3px=0,truth_count_unknown_trials=0,
                          error_trials=0,peak_cap_trials=0,errors_by_phase={})
    def append(self,field):
        if not self.first:self.stream.write(b',')
        self.first=False;self.stream.write(json.dumps(field,allow_nan=False,separators=(',',':')).encode())
        self.summary['truth_count_unknown_trials']+=int(field.get('truth_count_known')is False)
        self.summary['planned']+=1;self.summary['candidate_rows']+=len(field['matches'])
        self.summary['spatial_recovered']+=len(set(m for m in field['matches']if m>=0))
        self.summary['spatial_recovered_trials']+=int(any(m>=0 for m in field['matches']))
        self.summary['resolved_truth_span_ge3px']+=len(set(g['truth_index']for g in field.get('matched_geometry',[])if g['true_displacement_px']>=3))
        self.summary['peak_cap_trials']+=int(field.get('peak_cap_reached')is True)
        if field.get('error'):
            self.summary['error_trials']+=1;phase=field['error']['phase'];self.summary['errors_by_phase'][phase]=self.summary['errors_by_phase'].get(phase,0)+1
    def finish(self):
        self.summary['evaluation_complete']=self.summary['error_trials']==0 and self.summary['truth_count_unknown_trials']==0
        self.summary['search_coverage_complete']=self.summary['evaluation_complete']and self.summary['peak_cap_trials']==0 and not self.control_capped
        self.stream.write(('],"summary":'+json.dumps(self.summary,allow_nan=False)+'}').encode());self.stream.close();self.handle.flush();os.fsync(self.handle.fileno());self.handle.close();os.replace(self.temporary,self.path)
        return str(self.path)
    def abort(self):
        self.stream.close();self.handle.close();self.temporary.unlink(missing_ok=True)


def _record(tracks,truth,native):
    import numpy as np
    features=[];matches=[];geometry=[]
    for index,track in enumerate(tracks):
        features.append(list(map(float,track.features())));xy=np.asarray(track.positions_xy);epochs=list(track.epochs)
        distances=[np.linalg.norm(xy-path[epochs],axis=1)for path in truth]
        ids=[i for i,d in enumerate(distances)if np.all(d<=1.5)]
        match=min(ids,key=lambda i:float(distances[i].mean()))if ids else(-2 if native else-1);matches.append(match)
        if match>=0:
            expected=truth[match][epochs]
            geometry.append(dict(candidate_index=index,truth_index=match,epochs=epochs,
                true_displacement_px=float(np.max(np.linalg.norm(expected[:,None,:]-expected[None,:,:],axis=-1))),
                measured_displacement_px=float(np.max(np.linalg.norm(xy[:,None,:]-xy[None,:,:],axis=-1))),
                max_offset_px=float(distances[match].max())))
    return dict(features=features,matches=matches,matched_geometry=geometry,truth_count=len(truth),
                candidate_epochs=[list(t.epochs)for t in tracks],candidate_positions_xy=[list(t.positions_xy)for t in tracks])


def _measure(images,times,settings,science):
    import numpy as np
    started=time.perf_counter();cpu=time.process_time()
    try:
        tracks=science.find_candidates(images,times,**settings)
        residual=science.difference_frames(images,True)
        peaks=[len(science.detect_peaks(d,np.isfinite(d),settings['psf_sigma'],settings['min_snr'],settings['max_peaks'],settings['min_support']))for d in residual]
        result=dict(tracks=tracks,peaks_per_epoch=peaks,peak_cap_reached=any(p>=settings['max_peaks']for p in peaks),error=None)
    except Exception as exc:result=dict(tracks=[],peaks_per_epoch=None,peak_cap_reached=None,error=_error('detection',exc))
    return {**result,'detector_wall_seconds':time.perf_counter()-started,'detector_cpu_seconds':time.process_time()-cpu,
            'rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024}


def _field(identity,measurement,truth,role,science,native):
    import numpy as np
    result=_record(measurement['tracks'],truth,native);error=measurement['error']or science.model_errors.get(role)
    scores=[];score_started=time.perf_counter();score_cpu=time.process_time()
    if not error:
        try:
            scores=list(map(float,science.models[role].score(np.asarray(result['features'],np.float32).reshape(-1,6))))
            if len(scores)!=len(result['features'])or not all(math.isfinite(v)and 0<=v<=1 for v in scores):raise ValueError('invalid aligned model scores')
        except Exception as exc:error=_error('model_scoring',exc)
    if error:
        unscored=result;result=_record([],truth,native);result['unscored_candidate_rows']=len(unscored['matches']);result['unscored_measurements']=unscored;scores=[]
    return {**identity,**result,'baseline':[float(science.baseline_score(t))for t in measurement['tracks']]if not error else[],
            'scores':scores,'error':error,**{k:v for k,v in measurement.items()if k not in ['tracks','error']},
            'model_wall_seconds':time.perf_counter()-score_started,'model_cpu_seconds':time.process_time()-score_cpu,
            'rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024}


def _measures(images,times,freeze,science):
    measured={};result={}
    for profile in PROFILES:
        for role in ROLES:
            settings={**freeze['options'][profile],'psf_sigma':freeze['models'][role]['psf_sigma']}
            key=tuple(sorted(settings.items()))
            if key not in measured:measured[key]=_measure(images,times,settings,science)
            result[profile,role]=measured[key]
    return result


def _metadata(freeze,profile,role,**extra):
    result=dict(schema_version=1,designation=freeze['scope']+' frozen paired evaluation',freeze_sha256=freeze['_sha256'],
        model={k:v for k,v in freeze['models'][role].items()if not k.startswith('_')},model_metadata=freeze['models'][role]['_metadata_document'],versions=freeze['versions'],profile=profile,system=role,partition=freeze['scope'],
        detector_settings={**freeze['options'][profile],'psf_sigma':freeze['models'][role]['psf_sigma']},
        all_derivatives_correlated=True,detection_reused_across_systems=freeze['models']['baseline']['psf_sigma']==freeze['models']['candidate']['psf_sigma'],source_sha256={k:v['sha256']for k,v in freeze['sources'].items()})
    result.update(extra);return result


def _latent_id(parent,trajectory_id,speed,direction,brightness,origin,velocity,positions,flux,usable,epsf,known=True):
    import numpy as np
    covered=positions[np.asarray(usable)]if positions is not None else []
    span=float(np.linalg.norm(covered[-1]-covered[0]))if len(covered)>=2 else 0.
    return dict(parent_id=parent['parent_id'],partition=parent['_scope'],seed=parent['seed'],
        trajectory_id=trajectory_id,speed_px_hour=speed,direction_id=direction,brightness=brightness,
        origin_xy=origin.tolist(),velocity_xy_hour=velocity.tolist(),expected_xy=None if positions is None else positions.tolist(),
        injected_flux=flux,epsf=epsf,usable_center_epochs=int(sum(usable)),center_usable_flags=usable,
        expected_covered_displacement_px=span,coverage_known=known,
        independent_geometry=dict(finite_center_epochs=int(sum(usable)),covered_true_displacement_px=span))


def _native_latents(parent,stack,natives,science,shape,setup_error):
    import numpy as np
    rng=np.random.default_rng(parent['seed']);h,w=shape
    noise=None
    if setup_error is None:
        noise=np.asarray([1.4826*np.median(abs(v-np.median(v)))for image in stack.images for v in [image[np.isfinite(image)]]])
        if not np.isfinite(noise).all()or np.any(noise<=0):setup_error=_error('background_normalization',ValueError('nonpositive native background MAD'))
    for speed in SPEEDS:
        for direction in range(6):
            origin=rng.uniform([8,8],[w-8,h-8]);angle=rng.uniform(0,2*np.pi);velocity=speed*np.array([np.cos(angle),np.sin(angle)])
            trajectory_id=f'{speed:g}-{direction}';positions=None if stack is None else origin+stack.times[:,None]*velocity
            usable=[];epsf=[];response=None;typical=None;error=setup_error
            geometry_known=stack is not None and list(stack.images.shape[1:])==shape
            if geometry_known:
                for image,(x,y)in zip(stack.images,np.rint(positions).astype(int)):
                    usable.append(bool(0<=x<w and 0<=y<h and np.isfinite(image[y,x])))
            if error is None:
                try:
                    projected=[science.project_response(n,stack.grid,xy)for n,xy in zip(natives,positions)]
                    response=np.asarray([p[0]for p in projected]);epsf=[p[1]for p in projected]
                    peaks=np.max(response,axis=(1,2));covered=peaks[np.asarray(usable)&(peaks>0)]
                    supported=covered if len(covered)else peaks[peaks>0]
                    if not len(supported):
                        fallback=[science.project_response(n,stack.grid,np.array([w/2,h/2]))[0].max()for n in natives]
                        supported=np.asarray([v for v in fallback if v>0])
                    typical=float(np.median(supported))if len(supported)else 1.
                    if not math.isfinite(typical)or typical<=0:raise ValueError('invalid supported response normalization')
                except Exception as exc:error=_error('injection_projection',exc)
            for brightness in BRIGHTNESS:
                flux=brightness*float(np.median(noise))/typical if error is None else None
                identity=_latent_id(parent,trajectory_id,speed,direction,brightness,origin,velocity,positions,flux,usable,epsf,geometry_known)
                images=None;trial_error=error
                if trial_error is None:
                    try:
                        images=science.add_injection(stack.images,response,flux)
                        for image in images:image-=np.nanmedian(image)
                    except Exception as exc:trial_error=_error('injection_addition',exc)
                yield identity,images,positions,trial_error


def _empty_measurement(error):
    return dict(tracks=[],peaks_per_epoch=None,peak_cap_reached=None,error=error,
                detector_wall_seconds=0.,detector_cpu_seconds=0.,rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)


def _native_one(task):
    freeze_path,freeze_sha256,output_dir,parent_id=task
    freeze=validate_freeze(freeze_path,freeze_sha256)
    parent=next(p for p in freeze['native']['parents']if p['parent_id']==parent_id);parent['_scope']=freeze['scope']
    destinations={(profile,role):Path(output_dir)/f'{parent_id}-{profile}-{role}.json.gz'for profile in PROFILES for role in ROLES}
    if any(p.exists()for p in destinations.values()):raise ValueError('refusing to overwrite evaluation cache')
    science=_science(freeze);stack=None;natives=[];setup_error=None
    try:
        if science.model_errors:raise ValueError('paired model initialization failed')
        region=freeze['native']['region'];observations=parent['_observations']
        request=dict(schema_version=1,analysis_id='frozen-'+parent_id,
            source=dict(kind='fits',observations=observations,region=dict(right_ascension_deg=parent['center_deg'][0],
                declination_deg=parent['center_deg'][1],width_arcmin=region['width_arcmin'],height_arcmin=region['height_arcmin'])),
            options=dict(pixel_scale_arcsec=region['pixel_scale_arcsec'],mask_policy=region['mask_policy']))
        stack=science.prepare(request)
        if not 3<=len(stack.images)<=32 or list(stack.images.shape[1:])!=freeze['_shape']:
            raise ValueError('prepared native stack differs from bounded frozen grid')
        if freeze['scope']=='final'and len(stack.images)!=8:raise ValueError('final native stack must contain8 independent epochs')
        lookup={row['frame_id']:row for row in observations}
        natives=[science.read_native(lookup[frame['frame_id']]['path'],stack.grid,stack.images.shape[1:])for frame in stack.frames]
    except Exception as exc:setup_error=_error('model_loading'if science.model_errors else'native_preparation',exc)
    controls=_measures(stack.images,stack.times,freeze,science)if setup_error is None else {
        key:_empty_measurement(setup_error)for key in destinations}
    writers={}
    try:
        for(profile,role),destination in destinations.items():
            measurement=controls[profile,role];control=_record(measurement['tracks'],[],True)
            metadata=_metadata(freeze,profile,role,kind='native',parent_id=parent_id,seed=parent['seed'],
                input_sources=parent['_observations'],center_deg=parent['center_deg'],
                times_hours=[]if stack is None else stack.times.tolist(),
                registered_shape=[len(parent['_observations']),*freeze['_shape']]if stack is None else list(stack.images.shape),
                frames=[]if stack is None else stack.frames,warnings=[]if stack is None else stack.warnings,
                acquisition_manifests=freeze['native']['acquisition_manifests'],downloads_manifest=parent['downloads_manifest'],
                preparation_options=freeze['native']['region'],injection_matrix=MATRIX,control=control,control_labels='unknown',control_error=measurement['error'],
                control_diagnostics={k:v for k,v in measurement.items()if k!='tracks'},
                limitations=['source added after registration','fixed source flux across passbands','no added photon noise or variance update',
                    'spatial matches are not confirmed motion','real control identities remain unknown','ranking scores are uncalibrated'])
            writers[profile,role]=AtomicCache(destination,metadata)
        for identity,images,positions,error in _native_latents(parent,stack,natives,science,freeze['_shape'],setup_error):
            truth=[]if positions is None else[positions]
            measurements=_measures(images,stack.times,freeze,science)if error is None else{
                key:_empty_measurement(error)for key in destinations}
            for key,writer in writers.items():
                profile,role=key;control=controls[key];measurement=measurements[key]
                control_known=control['error']is None
                preexisting=any(m>=0 for m in _record(control['tracks'],truth,True)['matches'])if control_known else None
                if control['error']and measurement['error']is None:measurement={**measurement,'error':_error('control_detection',ValueError(control['error']['message']))}
                field=_field({**identity,'attribution_eligible':control_known and not preexisting,
                    'preexisting_control_match':preexisting},measurement,truth,role,science,True)
                field['truth_count']=1
                writer.append(field)
        return[(writer.finish(),writer.summary)for writer in writers.values()]
    except BaseException:
        for writer in writers.values():writer.abort()
        raise



def write_run_manifest(kind,freeze,results,output_dir):
    path=Path(output_dir)/('run-'+kind+'-manifest.json')
    if path.exists():raise ValueError('refusing to overwrite evaluation run manifest')
    payload=dict(schema_version=1,kind=kind,freeze_sha256=freeze['_sha256'],scope=freeze['scope'],
        versions=freeze['versions'],options=freeze['options'],
        evaluation_complete=all(summary['evaluation_complete']for _,summary in results),
        outputs=[dict(path=str(p),sha256=digest(p),summary=summary)for p,summary in results])
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,prefix='.'+path.name+'.',delete=False)as stream:
        temporary=Path(stream.name);json.dump(payload,stream,allow_nan=False);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)
    return payload


def run(freeze_path,freeze_sha256,output_dir):
    freeze=validate_freeze(freeze_path,freeze_sha256);_threads()
    tasks=[(str(freeze_path),freeze_sha256,str(output_dir),p['parent_id'])for p in freeze['native']['parents']]
    if freeze['runtime']['workers']==1:results=[item for task in tasks for item in _native_one(task)]
    else:
        with ProcessPoolExecutor(max_workers=freeze['runtime']['workers'])as pool:
            results=[item for items in pool.map(_native_one,tasks)for item in items]
    write_run_manifest('native',freeze,results,output_dir)
    return[path for path,summary in results]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--freeze',required=True);parser.add_argument('--freeze-sha256',required=True);parser.add_argument('--output-dir',required=True);args=parser.parse_args()
    paths=run(args.freeze,args.freeze_sha256,args.output_dir);print(json.dumps(paths,indent=2))
    if not _json(Path(args.output_dir)/'run-native-manifest.json')['evaluation_complete']:raise SystemExit(2)

if __name__=='__main__':main()
