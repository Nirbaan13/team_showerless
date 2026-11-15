"""Declared TRAIN-only latent packets; no fitting or candidate generation."""
from pathlib import Path
import json
import numpy as np
from ml_inference.prepare import prepare
from training.evaluate_background import read_native,project_response,add_projected_injection
from ml.pvusatov.experiments.v4.operating_points.study import digest,atomic,image_hash


def prepare_packets(protocol,scratch):
    tasks=[]
    for parent,info in protocol['native'].items():
        for row in info['input_sources']:
            if digest(row['path'])!=row['sha256']:raise ValueError('TRAIN bytes differ')
        ra,dec=info['center_deg'];stack=prepare(dict(schema_version=1,analysis_id='association-'+parent,
            source=dict(kind='fits',observations=info['input_sources'],region=dict(right_ascension_deg=ra,declination_deg=dec,width_arcmin=6.,height_arcmin=6.)),options=info['preparation_options']))
        np.testing.assert_array_equal(stack.times,info['times_hours'])
        lookup={r['frame_id']:r for r in info['input_sources']};natives=[read_native(lookup[f['frame_id']]['path'],stack.grid,stack.images.shape[1:])for f in stack.frames]
        def save(identity,images,truth):
            key=identity['case_id'];path=scratch/'packets'/(key+'.npz');meta=scratch/'packets'/(key+'.json');path.parent.mkdir(parents=True,exist_ok=True)
            if path.exists()or meta.exists():raise ValueError('immutable native packet exists')
            np.savez_compressed(path,images=images,times=stack.times,outlier=stack.outlier,bloom=np.zeros(0,bool)if stack.bloom is None else stack.bloom)
            atomic(meta,dict(identity,truth=truth,image_sha256=image_hash(images),finite_mask_sha256=image_hash(np.isfinite(images))))
            tasks.append(dict(kind=identity['kind'],parent_id=parent,path=str(path),sha256=digest(path),metadata=str(meta),metadata_sha256=digest(meta)))
        save(dict(kind='native_control',parent_id=parent,seed=info['seed'],case_id=parent+'-control'),stack.images,[])
        noise=np.asarray([1.4826*np.median(abs(v-np.median(v)))for image in stack.images for v in [image[np.isfinite(image)]]])
        if not np.isfinite(noise).all()or np.any(noise<=0):raise ValueError('invalid TRAIN MAD')
        rng=np.random.default_rng(info['seed']);h,w=stack.images.shape[1:]
        for speed in (.1,1.,10.):
            for direction in range(3):
                origin=rng.uniform([8,8],[w-8,h-8]);angle=rng.uniform(0,2*np.pi);velocity=speed*np.asarray([np.cos(angle),np.sin(angle)]);xy=origin+stack.times[:,None]*velocity
                projected=[project_response(n,stack.grid,p)for n,p in zip(natives,xy)];response=np.asarray([p[0]for p in projected]);peaks=np.max(response,axis=(1,2))
                usable=np.asarray([bool(0<=x<w and 0<=y<h and np.isfinite(im[y,x]))for im,(x,y)in zip(stack.images,np.rint(xy).astype(int))])
                supported=peaks[usable&(peaks>0)]
                if not len(supported):supported=peaks[peaks>0]
                if not len(supported):supported=np.asarray([project_response(n,stack.grid,np.asarray([w/2,h/2]))[0].max()for n in natives]);supported=supported[supported>0]
                typical=float(np.median(supported))if len(supported)else 1.
                for brightness in (3.,12.,48.):
                    flux=brightness*float(np.median(noise))/typical;images=add_projected_injection(stack.images,response,flux)
                    for image in images:image-=np.nanmedian(image)
                    save(dict(kind='native',parent_id=parent,seed=info['seed'],case_id=f'{parent}-{speed:g}-{direction}-{brightness:g}',
                        speed_px_hour=speed,direction_id=direction,brightness=brightness,origin_xy=origin.tolist(),velocity_xy_hour=velocity.tolist(),injected_flux=flux),images,[xy.tolist()])
    return tasks
