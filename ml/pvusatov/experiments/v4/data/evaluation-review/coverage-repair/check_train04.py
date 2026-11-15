"""TRAIN04-only preparation/injection parity; no models, detections or FINAL."""
from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
import hashlib,importlib.util,json,os,resource,sys,tempfile,time
import numpy as np
from astropy.io import fits

OWN=Path(__file__).resolve().parent
NAMESPACE=OWN.parents[4]
DATA=NAMESPACE/'experiments/v4/data'
BACKEND=NAMESPACE/'backend/inference'
RUNTIME=NAMESPACE/'releases/v4/runtime'
EVALUATION=NAMESPACE/'experiments/v4/evaluation'
SEED=3800904

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
    return h.hexdigest()
def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
def load(name,path,*,package=False):
    source=path.read_bytes();spec=importlib.util.spec_from_file_location(name,path,submodule_search_locations=[str(path.parent)]if package else None);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;exec(compile(source,str(path),'exec'),m.__dict__);return m

def main():
    start=time.monotonic();out=OWN/'train04-proof.json'
    if out.exists():raise ValueError('Refusing to overwrite prior proof')
    handoff=json.loads((DATA/'development-handoff.json').read_text());group=next(g for g in handoff['groups']if g['parent_id']=='v4-train04');manifest=DATA/'manifests/development/v4-train04-downloads.json'
    assert group['split']=='train'and sha(manifest)==group['downloads_manifest']['sha256'];rows=json.loads(manifest.read_text());assert len(rows)==8
    observations=[]
    for row in rows:
        p=Path(row['path']).resolve();assert 'v4-train04'in p.parts and 'development'in p.parts and not any(q.lower().startswith(('final','quarant'))for q in p.parts);assert sha(p)==row['sha256'];observations.append({**row,'frame_id':p.stem,'observation_id':row['obs_id'],'access_url':row['url']})
    paths=dict(old_prepare=BACKEND/'ml_inference/prepare.py',new_prepare=RUNTIME/'ml_inference/prepare.py',legacy_latents=BACKEND/'experiments/v3_evaluation/run_native.py',native_epsf=BACKEND/'training/evaluate_background.py',new_injection=EVALUATION/'native_injections.py',contracts=BACKEND/'ml_inference/contracts.py')
    source_hashes={k:sha(p)for k,p in paths.items()}
    declaration=dict(scope='TRAIN04 only; no detectors/models/FINAL; engineering parity',seed=SEED,source_sha256=source_hashes,manifest_sha256=sha(manifest),physical_obsids=[r['obs_id']for r in rows],covered_trials=270,masked_derivative_trials=270,derivative='Temporary FLAGS|1 in first TRAIN frame; original physical identities/times retained; not archive bytes',outputs='Aggregate equality hashes only; temporary FITS deleted')
    write(OWN/'train04-declaration.json',declaration)
    # Every local module executes the exact source bytes, with no pyc lookup.
    load('ml_inference',BACKEND/'ml_inference/__init__.py',package=True)
    for name in ('contracts','detector','model'):load('ml_inference.'+name,BACKEND/('ml_inference/'+name+'.py'))
    old=load('ml_inference.prepare',paths['old_prepare'])
    load('v4_coverage_review',RUNTIME/'ml_inference/__init__.py',package=True);load('v4_coverage_review.contracts',RUNTIME/'ml_inference/contracts.py');new=load('v4_coverage_review.prepare',paths['new_prepare'])
    load('training',BACKEND/'training/__init__.py',package=True);native=load('training.evaluate_background',paths['native_epsf']);legacy=load('coverage_legacy_latents',paths['legacy_latents']);helper=load('coverage_new_latents',paths['new_injection'])
    center=group['center_deg'];request=dict(schema_version=1,analysis_id='train04-coverage-parity',source=dict(kind='fits',observations=observations,region=dict(right_ascension_deg=center[0],declination_deg=center[1],width_arcmin=6.,height_arcmin=6.)),options=dict(pixel_scale_arcsec=6.15,mask_policy='motion'))
    before=old.prepare(request);after=new.prepare(request)
    for key in ('images','times','outlier','bloom'):
        assert getattr(before,key).dtype==getattr(after,key).dtype and getattr(before,key).tobytes()==getattr(after,key).tobytes(),key
    assert before.frames==after.frames and before.warnings==after.warnings and before.provenance==after.provenance
    assert before.grid.to_header().tostring()==after.grid.to_header().tostring()
    assert np.isfinite(after.images).any(axis=(1,2)).all()
    shape=list(after.images.shape[1:]);lookup={r['frame_id']:r for r in observations};ordered=[lookup[f['frame_id']]for f in after.frames];natives=[native.read_native(r['path'],after.grid,shape)for r in ordered]
    science=SimpleNamespace(project_response=native.project_response,add_injection=native.add_projected_injection);parent=dict(parent_id='v4-train04',seed=SEED,_scope='development')
    expected=legacy._native_latents(parent,before,natives,science,shape,None);actual=helper.native_latents(parent,after,natives,science,shape,legacy);image_hash=hashlib.sha256();identity_hash=hashlib.sha256();positions=[];count=0
    for left,right in zip(expected,actual):
        old_id,old_images,old_xy,old_error=left;identity,images,xy,error=right
        assert old_error is error is None and {k:identity[k]for k in old_id}==old_id
        assert old_images.dtype==images.dtype and old_images.tobytes()==images.tobytes()and old_xy.tobytes()==xy.tobytes()
        image_hash.update(images.tobytes());identity_hash.update(json.dumps(old_id,sort_keys=True,allow_nan=False).encode());positions.append(xy.tobytes());count+=1
    assert count==270
    scratch=Path('/tmp/spaceapps-v4-native-data/review-coverage-repair');scratch.mkdir(parents=True,exist_ok=True);derivative_info=None;masked_count=0
    with tempfile.TemporaryDirectory(prefix='train04-',dir=scratch)as directory:
        derivative=Path(directory)/'explicitly-derived-flags-mask.fits'
        with fits.open(ordered[0]['path'],memmap=False)as source:
            copied=fits.HDUList([h.copy()for h in source]);copied['FLAGS'].data[:]=np.bitwise_or(copied['FLAGS'].data,1);copied[0].header['V4DERIV']=True;copied[0].header['V4ORIG']=ordered[0]['sha256'];copied[0].header.add_history('TRAIN-only coverage derivative FLAGS|1; not original archive bytes')
            for h in copied:h.add_checksum()
            copied.writeto(derivative,checksum=True)
        modified=[dict(r)for r in observations];modified[0].update(path=str(derivative),sha256=sha(derivative),release='dr1');modified[0].pop('access_url',None)
        masked_request={**request,'source':{**request['source'],'observations':modified}};blank=new.prepare(masked_request);assert np.isnan(blank.images[0]).all()and blank.images.shape==after.images.shape and blank.times.tobytes()==after.times.tobytes()
        for index in range(1,8):assert blank.images[index].tobytes()==after.images[index].tobytes()
        assert [f['physical_observation_id']for f in blank.frames]==[f['physical_observation_id']for f in after.frames]
        variant_natives=[native.read_native(r['path'],blank.grid,shape)for r in modified]
        for index,(identity,images,xy,error)in enumerate(helper.native_latents(parent,blank,variant_natives,science,shape,legacy)):
            assert error is None and images.shape==after.images.shape and np.isnan(images[0]).all()and xy.tobytes()==positions[index]
            assert identity['noise_reference_usable_epoch_count']==7 and identity['center_usable_flags'][0]is False and len(identity['center_usable_flags'])==8;masked_count+=1
        assert masked_count==270
        derivative_info=dict(original_sha256=ordered[0]['sha256'],derivative_sha256=sha(derivative),scope='FLAGS-masked TRAIN research version, not an extra physical observation',planned_epochs=8,nonempty_epochs=int(np.isfinite(blank.images).any(axis=(1,2)).sum()),warning=blank.warnings)
    assert not derivative.exists()
    assert all(sha(r['path'])==r['sha256']for r in rows)
    assert all(sha(path)==source_hashes[name]for name,path in paths.items())
    proof=dict(status='PASS',scope='TRAIN04 only; no detectors/models/scoring/FINAL access',source_sha256=source_hashes,seed=SEED,physical_epochs=8,covered_prepare_arrays_bitwise_equal=True,covered_prepare_metadata_equal=True,covered_injection_trials_bitwise_equal=count,covered_injection_image_sha256=image_hash.hexdigest(),covered_core_identity_sha256=identity_hash.hexdigest(),masked_derivative_trials=masked_count,masked_derivative=derivative_info,scratch_fits_deleted=True,all_original_native_bytes_unchanged=True,wall_seconds=time.monotonic()-start,maxrss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
    write(out,proof);print(json.dumps(proof,indent=2))
if __name__=='__main__':main()
