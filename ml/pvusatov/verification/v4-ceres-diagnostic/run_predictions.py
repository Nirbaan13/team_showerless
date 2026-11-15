"""Fixed known-case CLI and same-pool scorers; no ephemeris positions read here."""
from pathlib import Path
from types import ModuleType
import datetime,hashlib,importlib.util,json,os,resource,shutil,subprocess,sys,time
OWN=Path(__file__).resolve().parent;REPO=OWN.parents[3]

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def main():
 if (OWN/'prediction-seal.json').exists():raise ValueError('Predictions already sealed; no adaptive rerun')
 plan=json.loads((OWN/'plan.json').read_text());handoff_path=Path(plan['handoff']['path']);assert sha(handoff_path)==plan['handoff']['sha256'];handoff=json.loads(handoff_path.read_text())
 before=[]
 for row in handoff['images']:
  path=Path(row['path']).resolve();assert path.parent==Path('/tmp/spaceapps-v4-native-data/known_objects/known-ceres-2025-07-01-d2')and sha(path)==row['sha256'];before.append(dict(path=str(path),sha256=sha(path)))
 assert len(before)==4
 for source,expected in plan['runtime_sources_sha256'].items():assert sha(REPO/source)==expected
 for model in plan['models'].values():assert sha(Path(model['path'])/'ranker.onnx')==model['artifact_sha256']and sha(Path(model['path'])/'metadata.json')==model['metadata_sha256']
 runtime=OWN/'runtime';package=runtime/'ml_inference';package.mkdir(parents=True,exist_ok=False)
 for source,expected in plan['runtime_sources_sha256'].items():
  target=package/Path(source).name;shutil.copyfile(REPO/source,target);assert sha(target)==expected
 assert not list(runtime.rglob('*.pyc'))
 observations=[dict(path=r['path'],frame_id=Path(r['path']).stem,observation_id=r['obs_id'],sha256=r['sha256'])for r in handoff['images']]
 request=dict(schema_version=1,analysis_id='ceres-fixed-default-postselection',model_dir=plan['models']['candidate']['path'],source=dict(kind='fits',observations=observations,region=dict(right_ascension_deg=handoff['center'][0],declination_deg=handoff['center'][1],width_arcmin=6.,height_arcmin=6.)),options=dict(pixel_scale_arcsec=6.15,mask_policy='motion'))
 write(OWN/'request.json',request)
 env={**os.environ,'PYTHONPATH':str(runtime),'PYTHONDONTWRITEBYTECODE':'1','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1'}
 start=time.monotonic();command=[sys.executable,'-m','ml_inference','--request',str(OWN/'request.json'),'--output',str(OWN/'cli')];child=subprocess.run(command,cwd=OWN,env=env,capture_output=True,text=True,timeout=300);cli_seconds=time.monotonic()-start
 (OWN/'cli.stdout.log').write_text(child.stdout);(OWN/'cli.stderr.log').write_text(child.stderr);result_path=OWN/'cli/result.json';result=json.loads(result_path.read_text());assert child.returncode in(0,2)
 pool_path=None;comparison_error=None
 if child.returncode==0 and'error'not in result:
  # This phase still has no access to ephemeris coordinates/labels.
  sys.path.insert(0,str(runtime));sys.dont_write_bytecode=True
  import numpy as np
  import ml_inference.pipeline as pipeline
  stack=pipeline.prepare(request);assert len(stack.frames)==4 and int(np.isfinite(stack.images).any(axis=(1,2)).sum())>=3
  residuals=pipeline.leave_one_out_residuals(stack.images);settings=result['settings'];sigma=settings['psf_sigma_px'];assert settings['min_snr']==4. and settings['max_candidates']==100 and sigma==.8 and settings['min_epochs']==3
  peaks=[pipeline._detect_peaks(diff,np.isfinite(diff),sigma,settings['min_snr'],settings['max_peaks'],.8)for diff in residuals]
  tracks=pipeline.link_detections(peaks,stack.times,settings['min_speed_arcsec_per_hour']/stack.pixel_scale,settings['max_speed_arcsec_per_hour']/stack.pixel_scale,1.4,3)
  measured=pipeline.extract_features(stack.images,stack.times,tracks,psf_sigma=.8,outlier=stack.outlier,bloom=stack.bloom,residuals=residuals)
  features=np.asarray(measured['features_v4'],dtype=np.float32).reshape(-1,30);six=np.asarray([t.features()for t in tracks],dtype=np.float32).reshape(-1,6);assert np.array_equal(features[:,:6],six)
  v4=pipeline.load_ranker(plan['models']['candidate']['path']);v4_scores=v4.score(features)
  baseline_source=REPO/'ml/pvusatov/backend/inference/ml_inference/model.py';source=baseline_source.read_bytes();copy=OWN/'baseline-scorer.py';copy.write_bytes(source);module=ModuleType('ceres_frozen_c13_scorer');module.__file__=str(copy);exec(compile(source,str(copy),'exec'),module.__dict__);c13=module.load_ranker(plan['models']['c13']['path']);c13_scores=c13.score(six)
  assert len(tracks)==result['comparison']['leave_one_out_count']
  aligned=0
  for candidate in result['candidates']:
   if candidate['method']!='residual_track':continue
   index=candidate['baseline_rank']-1;track=tracks[index]
   assert list(track.epochs)==[d['frame_index']for d in candidate['detections']]
   assert np.array_equal(np.asarray(track.positions_xy),np.asarray([[d['x'],d['y']]for d in candidate['detections']]))
   assert float(v4_scores[index])==candidate['score'];aligned+=1
  def ranks(values):
   out=np.empty(len(values),dtype=int);out[np.argsort(-values,kind='stable')]=np.arange(1,len(values)+1);return out
  v4_ranks=ranks(v4_scores);c13_ranks=ranks(c13_scores);rows=[]
  for index,track in enumerate(tracks):rows.append(dict(pool_index=index,candidate_id=measured['candidate_ids'][index],epochs=list(track.epochs),positions_xy=np.asarray(track.positions_xy).tolist(),features6=six[index].tolist(),features30=features[index].tolist(),heuristic_rank=index+1,v4_rank=int(v4_ranks[index]),c13_rank=int(c13_ranks[index]),v4_score=float(v4_scores[index]),c13_score=float(c13_scores[index])))
  pool_path=OWN/'pre-label-shared-pool.json';write(pool_path,dict(scope='Predictions only; identical Ceres images/proposals; no target ephemeris coordinates read',candidate_count=len(rows),cli_residual_rows_aligned=aligned,legacy_prefix_exact=True,comparison='Frozen C13 scorer under shared current preparation, not old end-to-end system',c13_source_sha256=hashlib.sha256(source).hexdigest(),score_kinds=dict(c13=c13.metadata['score_kind'],v4=v4.metadata['score_kind']),rows=rows))
 for row in before:assert sha(row['path'])==row['sha256']
 for source,expected in plan['runtime_sources_sha256'].items():assert sha(REPO/source)==expected
 for model in plan['models'].values():assert sha(Path(model['path'])/'ranker.onnx')==model['artifact_sha256']and sha(Path(model['path'])/'metadata.json')==model['metadata_sha256']
 seal=dict(scope='Fixed postselection known-object diagnostic; predictions sealed before ephemeris-to-pixel matching',sealed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),plan_sha256=sha(OWN/'plan.json'),request_sha256=sha(OWN/'request.json'),cli_result_sha256=sha(result_path),cli_exit_code=child.returncode,cli_error=result.get('error'),cli_seconds=cli_seconds,cli_child_peak_rss_mib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss/1024,shared_pool_sha256=sha(pool_path)if pool_path else None,original_input_hashes_unchanged=True,raw_inputs=before,source_sha256=plan['runtime_sources_sha256'],models=plan['models'],ephemeris_coordinates_read_before_prediction_seal=False,final_pixels_accessed=False)
 write(OWN/'prediction-seal.json',seal);print(json.dumps(dict(sealed=True,cli_exit=child.returncode,cli_seconds=cli_seconds,shared_pool=bool(pool_path),result_sha256=seal['cli_result_sha256'])))
if __name__=='__main__':main()
