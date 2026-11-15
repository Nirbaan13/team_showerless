"""Explain observed coverage/median differences without adjusting parity criteria."""
import os
os.environ.update(OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',MKL_NUM_THREADS='2')
import resource
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
import json
import sys
from pathlib import Path
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates
import validate_transport as vt

plan=json.loads((vt.HERE/'frozen-plan.json').read_text())
assert vt.protected()==plan['protected_sha256']
sys.path.insert(0,str(vt.RUNTIME))
from ml_inference.prepare import make_grid,SOURCE_BIT,OUTLIER_BIT
grid=make_grid(*plan['center_deg'],59,59,6.15)
yy,xx=np.indices((59,59));sky=grid.pixel_to_world_values(xx,yy)
data=[]
for path in [Path(plan['selected_source']['path']),vt.FULL]:
    with fits.open(path,memmap=False,lazy_load_hdus=True) as hs:
        header=hs[0].header.copy();header.update(hs['IMAGE'].header)
        wcs=WCS(header).celestial;x,y=wcs.world_to_pixel_values(*sky)
        signal=np.asarray(hs['IMAGE'].data,dtype=float)-hs['ZODI'].data
        flags=hs['FLAGS'].data.astype(np.int64);variance=hs['VARIANCE'].data
        good=((flags&~(SOURCE_BIT|OUTLIER_BIT))==0)&np.isfinite(signal)&np.isfinite(variance)&(variance>0)
        support=map_coordinates(good.astype(float),[y,x],order=1,cval=0)
        usable=support>=.995
        p=map_coordinates(np.where(good,signal,0),[y,x],order=1,cval=0)
        p=np.divide(p,support,where=usable,out=np.full(p.shape,np.nan))
        data.append(dict(x=x,y=y,shape=signal.shape,support=support,usable=usable,
                         projected=p,median=float(np.nanmedian(p)),header=dict(header),
                         flags_scaling={k:hs['FLAGS'].header.get(k) for k in ['BITPIX','BSCALE','BZERO']}))
a,b=data
common=a['usable']&b['usable'];added=b['usable']&~a['usable'];lost=a['usable']&~b['usable']
inside=(a['x']>=0)&(a['x']<=a['shape'][1]-1)&(a['y']>=0)&(a['y']<=a['shape'][0]-1)
delta=b['projected'][common]-a['projected'][common]
median_delta=b['median']-a['median']
residual=(b['projected'][common]-b['median'])-(a['projected'][common]-a['median'])+median_delta
allkeys=set(a['header'])|set(b['header'])
header_differences={k:[str(a['header'].get(k)),str(b['header'].get(k))] for k in sorted(allkeys)
                    if str(a['header'].get(k))!=str(b['header'].get(k))}
diagnostic=dict(
    designation='Post-observation diagnosis only; original exact preparation parity criteria unchanged',
    plan_sha256=vt.sha(vt.HERE/'frozen-plan.json'),script_sha256=vt.sha(__file__),
    roi_target_size_pixels=[59,59], cutout_native_shape=list(a['shape']),full_native_shape=list(b['shape']),
    target_coordinate_range_in_cutout=dict(x_min=float(a['x'].min()),x_max=float(a['x'].max()),
                                          y_min=float(a['y'].min()),y_max=float(a['y'].max())),
    grid_samples_outside_cutout=int((~inside).sum()), usable_full_samples_added=int(added.sum()),
    usable_cutout_samples_lost=int(lost.sum()), added_samples_outside_cutout=int((added&~inside).sum()),
    added_samples_inside_cutout=int((added&inside).sum()),
    support_difference_inside_cutout=vt.compare(a['support'][inside],b['support'][inside]),
    uncentered_common_projection=vt.compare(a['projected'][common],b['projected'][common]),
    common_projection_delta_min=float(delta.min()),common_projection_delta_max=float(delta.max()),
    background_median_cutout=a['median'],background_median_full=b['median'],
    background_median_full_minus_cutout=median_delta,
    centered_difference_plus_background_delta_max_abs=float(np.max(np.abs(residual))),
    image_header_differences=header_differences,
    flags_scaling_cutout=a['flags_scaling'],flags_scaling_full=b['flags_scaling'],
    protected_all_unchanged=vt.protected()==plan['protected_sha256'],
    peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
vt.save('difference-diagnosis.json',diagnostic)
print(json.dumps(diagnostic,indent=2))
