"""Offline labels/plots AFTER fixed predictions; no detector or scoring calls."""
from pathlib import Path
import datetime,hashlib,json,sys
import numpy as np
from offline import grid_wcs,offsets
OWN=Path(__file__).resolve().parent;REPO=OWN.parents[3]
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def main():
 if (OWN/'diagnostic-proof.json').exists():raise ValueError('Analysis already recorded; no adaptive reanalysis')
 plan=json.loads((OWN/'plan.json').read_text());seal=json.loads((OWN/'prediction-seal.json').read_text());assert seal['plan_sha256']==sha(OWN/'plan.json')and seal['ephemeris_coordinates_read_before_prediction_seal']is False
 result_path=OWN/'cli/result.json';assert sha(result_path)==seal['cli_result_sha256'];result=json.loads(result_path.read_text());assert sha(Path(plan['handoff']['path']))==plan['handoff']['sha256']
 handoff=json.loads(Path(plan['handoff']['path']).read_text());assert all(sha(row['path'])==row['sha256']for row in handoff['images'])
 if'error'in result:
  proof=dict(status='CLI_ERROR',error=result['error'],cli_result_sha256=sha(result_path),prediction_seal_sha256=sha(OWN/'prediction-seal.json'),input_hashes_unchanged=True,no_case_or_threshold_change=True);write(OWN/'diagnostic-proof.json',proof);(OWN/'DIAGNOSTIC.AI.md').write_text('# Ceres postselection diagnostic\n\nThe frozen default CLI failed: '+result['error']['code']+'. No relaxation, substitute case, fitting or model change was attempted. This target-selected unresolved case establishes no survey precision or confirmed motion.\n');return
 # First coordinate-label read occurs here, after result/pool prediction seals.
 ep_path=Path(plan['offline_ephemeris']['path']);assert sha(ep_path)==plan['offline_ephemeris']['sha256'];ep=json.loads(ep_path.read_text());assert ep['handoff_sha256']==plan['handoff']['sha256']and ep['image_sha256s']==[row['sha256']for row in handoff['images']]
 by_id={row['obs_id']:(row,point)for row,point in zip(handoff['images'],ep['positions'])};frames=result['frames'];assert len(frames)==4 and [f['physical_observation_id']for f in frames]==handoff['physical_obsids']
 points=[];time_errors=[]
 for frame in frames:
  original,point=by_id[frame['physical_observation_id']];assert frame['sha256']==original['sha256'];error=abs(frame['midpoint_mjd']-point['mjd'])*86400;assert error<=.0011;time_errors.append(error);points.append(point)
 w=grid_wcs(result['provenance']['grid']);expected=np.asarray(w.world_to_pixel_values([p['ra_deg']for p in points],[p['dec_deg']for p in points])).T
 assert np.isfinite(expected).all();published=[]
 for candidate in result['candidates']:
  measured=offsets(candidate,expected);published.append(dict(id=candidate['id'],method=candidate['method'],publication_rank=candidate['rank'],score=candidate['score'],score_kind=candidate['score_kind'],learned_rank=None if candidate['method']=='bloom_track'else candidate['rank'],**measured))
 pool_path=OWN/'pre-label-shared-pool.json';assert sha(pool_path)==seal['shared_pool_sha256'];pool=json.loads(pool_path.read_text());pool_matches=[]
 for row in pool['rows']:
  candidate=dict(detections=[dict(frame_index=i,x=xy[0],y=xy[1])for i,xy in zip(row['epochs'],row['positions_xy'])]);off=offsets(candidate,expected)
  if off['compatible']:pool_matches.append({key:row[key]for key in ['pool_index','candidate_id','v4_rank','c13_rank','heuristic_rank','v4_score','c13_score']}|off)
 residual=[r for r in published if r['method']=='residual_track'];bloom=[r for r in published if r['method']=='bloom_track'];compatible_residual=[r for r in residual if r['compatible']];compatible_bloom=[r for r in bloom if r['compatible']]
 best=lambda rows,key:min((r[key]for r in rows),default=None)
 comparison={}
 for role in ['v4','c13','heuristic']:
  rank=best(pool_matches,role+'_rank');comparison[role]=dict(best_residual_rank=rank,known_case_retained_top1=bool(rank is not None and rank<=1),known_case_retained_top3=bool(rank is not None and rank<=3))
 # Observables are reopened for a labelled visualization, never fed back to prediction.
 runtime=OWN/'runtime';sys.path.insert(0,str(runtime));sys.dont_write_bytecode=True
 from ml_inference.prepare import prepare
 from ml_inference.median_reference import leave_one_out_residuals
 request=json.loads((OWN/'request.json').read_text());stack=prepare(request);assert stack.frames==[{k:v for k,v in f.items()if k not in ['width','height','image_url','difference_url','bloom_url','coverage_fraction','outlier_fraction']}for f in frames]
 assert int(np.isfinite(stack.images).any(axis=(1,2)).sum())>=3
 residual_images=leave_one_out_residuals(stack.images)
 yy=np.rint(expected[:,1]).astype(int);xx=np.rint(expected[:,0]).astype(int);center_usable=[bool(0<=x<stack.images.shape[2]and 0<=y<stack.images.shape[1]and np.isfinite(image[y,x]))for image,x,y in zip(stack.images,xx,yy)]
 parallax_px=[float(v/6.15)for v in ep['parallax_arcsec_bounds']];span=float(np.max(np.linalg.norm(expected[:,None]-expected[None,:],axis=-1)));minutes=float(np.ptp(stack.times)*60)
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.patches import Circle
 raw_values=stack.images[np.isfinite(stack.images)];diff_values=np.abs(residual_images[np.isfinite(residual_images)]);lo,hi=np.percentile(raw_values,[1,99]);bound=max(float(np.percentile(diff_values,99)),1e-12)
 raw_cmap=plt.get_cmap('gray').copy();diff_cmap=plt.get_cmap('RdBu_r').copy();raw_cmap.set_bad('.25');diff_cmap.set_bad('.25');fig,axes=plt.subplots(2,4,figsize=(14,7),constrained_layout=True)
 selected_ids={r['id']for r in residual[:3]+bloom[:3]+compatible_residual+compatible_bloom}
 for index in range(4):
  axes[0,index].imshow(stack.images[index],origin='lower',cmap=raw_cmap,vmin=lo,vmax=hi,interpolation='nearest');axes[1,index].imshow(residual_images[index],origin='lower',cmap=diff_cmap,vmin=-bound,vmax=bound,interpolation='nearest')
  for ax in axes[:,index]:
   ax.plot(*expected[index],marker='x',color='lime',markersize=8,mew=1.5);ax.add_patch(Circle(expected[index],parallax_px[index],fill=False,color='cyan',linestyle='--',lw=1))
   for candidate in result['candidates']:
    if candidate['id']not in selected_ids:continue
    for d in candidate['detections']:
     if d['frame_index']==index:ax.plot(d['x'],d['y'],marker='o'if candidate['method']=='bloom_track'else'+',mfc='none',color='orange'if candidate['method']=='bloom_track'else'red',markersize=8,mew=1)
   ax.set_xlim(-.5,stack.images.shape[2]-.5);ax.set_ylim(-.5,stack.images.shape[1]-.5);ax.set_xlabel('registered x [px]')
  axes[0,index].set_title(frames[index]['midpoint_utc'][11:23]+' UTC');axes[1,index].set_title(f'leave-one-out residual; +{stack.times[index]*60:.2f} min')
 axes[0,0].set_ylabel('IMAGE − ZODI, median centered\nregistered y [px]');axes[1,0].set_ylabel('residual [MJy/sr]\nregistered y [px]')
 fig.suptitle('Ceres D2 — fixed postselection diagnostic\nGreen ×: geocentric ephemeris; cyan: observer-offset envelope; orange: BLOOM; red: residual\nDark gray: masked. Unresolved span; positional compatibility does not confirm motion.',fontsize=11)
 figure=OWN/'ceres-annotated.png';fig.savefig(figure,dpi=160);plt.close(fig)
 from PIL import Image
 pngs=[]
 for row in result['resources']:
  path=OWN/'cli'/row['name'];assert path.stat().st_size==row['size_bytes']
  with Image.open(path)as image:image.verify()
  pngs.append(dict(path='cli/'+row['name'],sha256=sha(path),bytes=path.stat().st_size))
 with Image.open(figure)as image:image.verify()
 proof=dict(status='COMPLETE_POSTSELECTION_DIAGNOSTIC',prediction_seal_sha256=sha(OWN/'prediction-seal.json'),cli_result_sha256=sha(result_path),ephemeris_sha256=sha(ep_path),analysis_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),model_sha256=result['model']['sha256'],model_metadata_sha256=plan['models']['candidate']['metadata_sha256'],registered_shape=list(stack.images.shape),physical_epochs=4,usable_epochs=int(np.isfinite(stack.images).any(axis=(1,2)).sum()),expected_registered_xy=expected.tolist(),geocentric_span_px=span,observer_parallax_envelope_px=parallax_px,midpoint_match_max_seconds=max(time_errors),time_span_minutes=minutes,ephemeris_center_finite_flags=center_usable,cli_warnings=result['warnings'],settings=result['settings'],published_candidates=len(published),published_residuals=len(residual),published_bloom=len(bloom),compatible_residuals=len(compatible_residual),compatible_bloom=len(compatible_bloom),best_published_residual_rank=best(compatible_residual,'publication_rank'),best_flagged_publication_rank=best(compatible_bloom,'publication_rank'),full_residual_pool=pool['candidate_count'],same_pool_comparison=comparison,compatible_full_pool_rows=pool_matches,published_candidate_offsets=published,pngs_verified=pngs,annotated_figure=dict(path=figure.name,sha256=sha(figure)),raw_inputs_hashes_unchanged=True,original_capsule_unchanged=True,interpretation='Target-selected crop; legacy1.5px positional compatibility only; .52px span unresolved and .637px observer envelope unapplied; unmatched controls UNKNOWN; BLOOM unscored; no survey precision, calibrated probability or confirmed motion; no release criterion or model reselection')
 assert all(sha(row['path'])==row['sha256']for row in handoff['images'])
 capsule=Path(plan['handoff']['path']).parents[1]/'publication-manifest.json';assert sha(capsule)==plan['original_capsule_manifest_sha256'];manifest=json.loads(capsule.read_text());assert all(sha(capsule.parent/r['path'])==r['sha256']for r in manifest['files'])
 write(OWN/'diagnostic-proof.json',proof)
 def rank_text(value):return str(value)if value is not None else'none'
 lines=['# Ceres D2: fixed postselection diagnostic','',f"The frozen default CLI completed on all four preselected exposures. Of {len(published)} published candidates, {len(compatible_residual)} residual and {len(compatible_bloom)} flagged BLOOM tracks satisfy the existing 1.5-pixel positional window at all their observed epochs (at least three).",'',f"Best published residual rank: **{rank_text(proof['best_published_residual_rank'])}**. Best flagged BLOOM publication rank: **{rank_text(proof['best_flagged_publication_rank'])}**. BLOOM tracks remain unscored and are not learned K1/K3 retention or RF probabilities.",'','| Scorer on identical full residual pool | Best compatible residual rank | At K1 | At K3 |','|---|---:|---:|---:|']
 for role in ['v4','c13','heuristic']:
  v=comparison[role];lines.append(f"| {role} | {rank_text(v['best_residual_rank'])} | {v['known_case_retained_top1']} | {v['known_case_retained_top3']} |")
 lines+=['',f"The pool contains {pool['candidate_count']} measured residual proposals. Every published residual's coordinates, epoch order and V4 score matched the pre-label reproduction exactly; the first six feature columns are exact. C13 is its frozen scorer under the **same current preparation/proposals**, not the old end-to-end pipeline. Score scales are uncalibrated and are not compared as probabilities.",'',f"The {minutes:.6f}-minute geocentric span is **{span:.6f} pixel**, with an unapplied conservative observer-offset envelope up to **{max(parallax_px):.6f} pixel**. This is unresolved: position-compatible evidence does not confirm motion or object identity. Ephemerides use geocentric astrometric ICRF, not apparent-of-date positions; WCS/photocenter/ephemeris errors are additional. Ephemeris-center finite-pixel flags are `{center_usable}` and do not filter this case out.",'','![Fixed Ceres diagnostic](ceres-annotated.png)','',f"CLI wall time: {seal['cli_seconds']:.3f}s on the shared local interpreter; this is not a hard-cgroup resource proof. All {len(pngs)} CLI PNG resources and the annotated figure passed decoding. Plot contrast uses fixed 1st/99th-percentile display scaling only; it changes no detection or matching decision.",'',f"Candidate graph: `{proof['model_sha256']}`. Metadata: `{proof['model_metadata_sha256']}`. Result: `{proof['cli_result_sha256']}`. Prediction seal: `{proof['prediction_seal_sha256']}`.",'','This crop was selected using known target metadata before pixels; it is not a blind sky search or survey-precision estimate. Other real tracks remain UNKNOWN. Source/model/default settings and case were unchanged; no fitting, new query, threshold relaxation or substitution occurred. Original four raw hashes and the entire immutable 403-file acquisition capsule remain unchanged. No twelve-FINAL pixels were accessed. This optional diagnostic adds no release criterion and permits no model reselection.']
 (OWN/'DIAGNOSTIC.AI.md').write_text('\n'.join(lines)+'\n');print(json.dumps({key:proof[key]for key in ['status','published_candidates','published_residuals','published_bloom','compatible_residuals','compatible_bloom','best_published_residual_rank','best_flagged_publication_rank','same_pool_comparison','geocentric_span_px']}))
if __name__=='__main__':main()
