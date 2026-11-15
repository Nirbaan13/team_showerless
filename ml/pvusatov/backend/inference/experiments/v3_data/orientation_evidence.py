"""Development-only numerical evidence for native ePSF -> registered axes.

No detector/ranker is invoked. An asymmetric response marker tests axis ordering
and WCS rotation using the same native-patch sampler and pull map as evaluation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import map_coordinates
from astropy.io import fits

from ml_inference.prepare import prepare
from training.evaluate_background import native_psf_patch,read_native


ROOT=Path('/tmp/spaceapps-v3-native-data')


def main():
    selected=json.loads((ROOT/'selected-groups.json').read_text())
    records=[]
    for gid in ['train04','train02','train03']:
        group=next(g for g in selected if g['group_id']==gid)
        directory=ROOT/'development'/gid
        downloads=json.loads((directory/'downloads.json').read_text())
        paths=[Path(row['path'])for row in downloads]
        request=dict(schema_version=1,analysis_id='development-coordinate-probe-'+gid,
                     source=dict(kind='fits',observations=[dict(path=str(p),frame_id=p.stem,observation_id=row['obs_id'])for p,row in zip(paths,downloads)],
                                 region=dict(right_ascension_deg=group['center'][0],declination_deg=group['center'][1],width_arcmin=6,height_arcmin=6)))
        stack=prepare(request)
        lookup={p.stem:p for p in paths}
        for frame in stack.frames:
            path=lookup[frame['frame_id']]
            native=read_native(path,stack.grid,stack.images.shape[1:])
            with fits.open(path,memmap=False)as hdus:
                image_frame=hdus['IMAGE'].header.get('DETCOORD')
                epsf_frame=hdus['EPSF'].header.get('DETCOORD')
                oversampling=[int(hdus['EPSF'].header['OVSMPX']),int(hdus['EPSF'].header['OVSMPY'])]
            assert image_frame==epsf_frame=='sky'
            assert oversampling==[5,5]
            x,y=native['wcs'].world_to_pixel_values(*group['center'])
            x,y=map(int,np.rint([x,y]))
            # Positive EPSF array column/row offsets must map to positive native
            # x/y, then to the registered grid through the physical WCS once.
            epsf=np.zeros((33,33));epsf[26,21]=1.
            patch,x0,y0=native_psf_patch(epsf,5,5,x,y)
            native_peak=np.unravel_index(np.argmax(patch),patch.shape)
            assert[x0+native_peak[1],y0+native_peak[0]]==[x+1,y+2]
            projected=map_coordinates(patch,[native['native_y']-y0,native['native_x']-x0],order=1,cval=0.)
            yy,xx=np.indices(projected.shape)
            actual=np.array([(xx*projected).sum(),(yy*projected).sum()])/projected.sum()
            expected=np.array(stack.grid.world_to_pixel_values(*native['wcs'].pixel_to_world_values(x+1,y+2)))
            base=np.array(stack.grid.world_to_pixel_values(*native['wcs'].pixel_to_world_values(x,y)))
            jac=np.column_stack([np.array(stack.grid.world_to_pixel_values(*native['wcs'].pixel_to_world_values(x+1,y)))-base,
                                 np.array(stack.grid.world_to_pixel_values(*native['wcs'].pixel_to_world_values(x,y+1)))-base])
            error=float(np.linalg.norm(actual-expected))
            assert error<.3,f'Axis probe registration mismatch {path}: {error}'
            records.append(dict(parent_group_id=gid,filename=path.name,detector=group['detector'],
                                image_frame=image_frame,epsf_frame=epsf_frame,
                                native_marker_offset_xy=[1,2],registered_expected_xy=expected.tolist(),
                                registered_centroid_xy=actual.tolist(),centroid_error_px=error,
                                native_to_registered_local_jacobian=jac.tolist()))
    report=dict(schema_version=1,scope='SWIR1–3 development only; no final pixel access or detector/model calls',
                physical_interpretation='The ePSF defines native detector-pixel response. DETCOORD=sky is the common SWIR view, not ICRS north-up. Sample the ePSF on native IMAGE axes, then WCS-project that response to the registered grid exactly once.',
                primary_sources=[dict(url='https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp.pdf',version='2.1,2026-11-10',pages=[52,59,60,74,81],sha256='9f3085cea74c6cdb647cc373bef27aaae50e394d348402e68ea2558ea06011cd'),
                                 dict(url='https://caltech-ipac.github.io/irsa-tutorials/spherex-psf/',sections=['4.3','5.1','6.2'])],
                caveats=['No MWIR4–6 orientation claim; MWIR requires explicit flip/zone-frame verification.',
                         'Numerical axis consistency and authoritative format support do not independently validate empirical shape fidelity or color-dependent source flux.'],
                source_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                probe_frames=len(records),max_centroid_error_px=max(r['centroid_error_px']for r in records),records=records)
    output=ROOT/'expansion-v2/evidence/orientation-evidence.json'
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items()if k!='records'},indent=2))


if __name__=='__main__':
    main()
