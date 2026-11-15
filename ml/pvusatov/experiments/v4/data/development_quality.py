"""V4 DEVELOPMENT-only coverage/axis checks; no detection, scoring or fitting."""
from pathlib import Path
from datetime import datetime,timezone
import sys,json,hashlib
import numpy as np
from scipy.ndimage import map_coordinates
from astropy.io import fits
OWN=Path(__file__).resolve().parent;NAMESPACE=OWN.parents[2];PACKAGE=NAMESPACE/'backend/inference'
sys.path.insert(0,str(PACKAGE))
from ml_inference.prepare import prepare
from training.evaluate_background import read_native,native_psf_patch

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    handoff=json.loads((OWN/'development-handoff.json').read_text());chosen=[]
    for detector in [1,2,3]:
        candidates=[g for g in handoff['groups']if g['split']=='train'and g['detector']==detector]
        if not candidates:raise ValueError('Waiting for at least one completed TRAIN parent for each SWIR detector')
        chosen.append(sorted(candidates,key=lambda g:g['parent_id'])[0])
    records=[];quality=[]
    for group in chosen:
        if group['split']!='train'or 'quarantine'in group['directory']:raise ValueError('Development-only path guard')
        rows=json.loads(Path(group['downloads_manifest']['path']).read_text())
        request=dict(schema_version=1,analysis_id='v4-data-coordinate-'+group['parent_id'],source=dict(kind='fits',observations=[dict(row,frame_id=Path(row['path']).stem)for row in rows],region=dict(right_ascension_deg=group['center'][0],declination_deg=group['center'][1],width_arcmin=6.,height_arcmin=6.)),options=dict(pixel_scale_arcsec=6.15,mask_policy='motion'))
        stack=prepare(request);lookup={Path(row['path']).stem:row for row in rows}
        per_epoch=[]
        for frame,image in zip(stack.frames,stack.images):
            row=lookup[frame['frame_id']];path=Path(row['path'])
            if digest(path)!=row['sha256']:raise ValueError('Development byte hash changed')
            native=read_native(path,stack.grid,stack.images.shape[1:])
            with fits.open(path,memmap=False)as hdus:
                image_frame=hdus['IMAGE'].header.get('DETCOORD');epsf_frame=hdus['EPSF'].header.get('DETCOORD');oversampling=[hdus['EPSF'].header['OVSMPX'],hdus['EPSF'].header['OVSMPY']]
            if image_frame!=epsf_frame or epsf_frame!='sky'or oversampling!=[5,5]:raise ValueError('Unsupported native development axis convention')
            x,y=map(int,np.rint(native['wcs'].world_to_pixel_values(*group['center'])))
            marker=np.zeros((33,33));marker[26,21]=1.
            patch,x0,y0=native_psf_patch(marker,5,5,x,y);peak=np.unravel_index(np.argmax(patch),patch.shape)
            if[x0+peak[1],y0+peak[0]]!=[x+1,y+2]:raise ValueError('Native ePSF axis marker mismatch')
            response=map_coordinates(patch,[native['native_y']-y0,native['native_x']-x0],order=1,cval=0.)
            yy,xx=np.indices(response.shape);actual=np.array([(xx*response).sum(),(yy*response).sum()])/response.sum()
            expected=np.array(stack.grid.world_to_pixel_values(*native['wcs'].pixel_to_world_values(x+1,y+2)))
            error=float(np.linalg.norm(actual-expected))
            if not np.isfinite(error)or error>=.3:raise ValueError('Native-to-registered orientation marker mismatch')
            records.append(dict(parent_id=group['parent_id'],detector=group['detector'],obs_id=row['obs_id'],source_sha256=row['sha256'],image_detcoord=image_frame,epsf_detcoord=epsf_frame,native_marker_offset_xy=[1,2],registered_expected_xy=expected.tolist(),registered_centroid_xy=actual.tolist(),centroid_error_px=error))
            values=image[np.isfinite(image)];per_epoch.append(dict(obs_id=row['obs_id'],finite_signal_fraction=float(np.isfinite(image).mean()),motion_mask_outlier_fraction=float(stack.outlier[len(per_epoch)].mean()),robust_signal_sigma=float(1.4826*np.median(abs(values-np.median(values))))if len(values)else None))
        quality.append(dict(parent_id=group['parent_id'],detector=group['detector'],shape=list(stack.images.shape),times_hours=stack.times.tolist(),span_hours=float(stack.times[-1]-stack.times[0]),frames=stack.frames,per_epoch=per_epoch,warnings=stack.warnings))
    previous=NAMESPACE/'backend/inference/experiments/v3_data/evidence/acquisition/expansion-v2/evidence/orientation-evidence.json';official=json.loads(previous.read_text())
    report=dict(schema_version=4,created_utc=datetime.now(timezone.utc).isoformat(),scope='New V4 TRAIN only. No FINAL pixel access, detector/model call or fitting.',
        source_sha256={str(path):digest(path)for path in [Path(__file__),PACKAGE/'ml_inference/prepare.py',PACKAGE/'training/evaluate_background.py']},
        original_official_orientation_evidence=dict(path=str(previous),sha256=digest(previous)),primary_sources=official['primary_sources'],
        interpretation='SWIR ePSFs use native IMAGE axes; SKY is common SWIR view, not north-up. Sample native ePSF once, then apply WCS projection once.',
        final_pixels_opened=False,new_probe_frames=len(records),detectors_verified=[1,2,3],max_centroid_error_px=max(r['centroid_error_px']for r in records),records=records,development_quality=quality,
        limitations=['Axis consistency checks do not validate empirical PSF shape/photometry.','No MWIR D4–D6 orientation claim.','Coverage/background statistics do not select or replace declared parents.','Real controls remain UNKNOWN; no real precision or probability estimate.'])
    destination=OWN/'development-quality-orientation.json'
    with destination.open('x')as f:json.dump(report,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(dict(path=str(destination),sha256=digest(destination),new_probe_frames=len(records),max_centroid_error_px=report['max_centroid_error_px'],parent_quality=[dict(parent_id=g['parent_id'],minimum_finite_fraction=min(e['finite_signal_fraction']for e in g['per_epoch']))for g in quality]),indent=2))
if __name__=='__main__':main()
