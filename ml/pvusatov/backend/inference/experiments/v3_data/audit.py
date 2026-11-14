"""Audit partition leakage, native files and development-only FITS metadata.

Quarantine paths are hashed as opaque bytes. The final branch never calls FITS.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path


def separation(a,b):
    ra1,dec1,ra2,dec2=map(math.radians,[*a,*b])
    value=math.sin(dec1)*math.sin(dec2)+math.cos(dec1)*math.cos(dec2)*math.cos(ra1-ra2)
    return math.degrees(math.acos(max(-1.,min(1.,value))))


def development_metadata(path):
    # This import and every FITS access are reachable only for train/validation.
    from astropy.io import fits
    import numpy as np
    with fits.open(path,memmap=False) as hdus:
        required={'IMAGE','FLAGS','VARIANCE','ZODI','EPSF','WCS-WAVE'}
        assert required.issubset({h.name for h in hdus}), f'Missing mission HDU: {path}'
        header=hdus[0].header.copy();header.update(hdus['IMAGE'].header)
        shape=hdus['IMAGE'].shape
        assert shape==hdus['FLAGS'].shape==hdus['VARIANCE'].shape==hdus['ZODI'].shape
        assert int(header['DETECTOR']) in (1,2,3)
        assert hdus['EPSF'].header['DETCOORD']=='sky'
        image=np.asarray(hdus['IMAGE'].data,float)-hdus['ZODI'].data
        good=np.isfinite(image)
        values=image[good]
        sigma=float(1.4826*np.median(abs(values-np.median(values)))) if len(values) else None
        return {'hdu_names':[h.name for h in hdus], 'native_shape':list(shape),
                'detector':int(header['DETECTOR']), 'epsf_coordinate_frame':hdus['EPSF'].header['DETCOORD'],
                'epsf_oversampling':[hdus['EPSF'].header['OVSMPX'],hdus['EPSF'].header['OVSMPY']],
                'finite_signal_fraction':float(good.mean()),'robust_signal_sigma':sigma,
                'physical_obsid_header':header.get('OBSID'),
                'time_header':{key:header.get(key) for key in ['MJD-OBS','MJD-END','MJD-AVG','DATE-OBS','DATE-END','EXPTIME']},
                'native_orientation_preserved':True}


def audit(root,open_development_pixels=False):
    plan=json.loads((root/'partition-plan.json').read_text())
    declared_groups=list(plan['groups'])
    stress_root=root/'crowded-development'
    if(stress_root/'partition-plan.json').exists():
        declared_groups+=json.loads((stress_root/'partition-plan.json').read_text())['groups']
    pairs=[(a['group_id'],b['group_id'],separation(a['center'],b['center']))
           for i,a in enumerate(declared_groups) for b in declared_groups[i+1:]]
    assert min(p[2]for p in pairs)>5
    all_selected=json.loads((root/'selected-groups.json').read_text())
    supplements=root/'cadence-supplement-plan.json'
    if supplements.exists():
        all_selected+=json.loads(supplements.read_text())['groups']
    if(stress_root/'selected-groups.json').exists():
        all_selected+=[dict(g,_data_root=str(stress_root)) for g in json.loads((stress_root/'selected-groups.json').read_text())]
    seen={}
    results=[]
    for group in all_selected:
        parent=group.get('parent_group_id',group['group_id'])
        for row in group.get('exposures',[]):
            previous=seen.setdefault(row['obs_id'],(parent,group['split']))
            assert previous==(parent,group['split']), f"Cross-parent exposure leakage {row['obs_id']}"
        directory=Path(group.get('_data_root',str(root)))/('quarantine_final'if group['split']=='final'else'development')/group['group_id']
        if not(directory/'downloads.json').exists():
            results.append(dict(group_id=group['group_id'],parent_group_id=parent,split=group['split'],downloaded_exposures=0))
            continue
        rows=json.loads((directory/'downloads.json').read_text())
        verified=[]
        for row in rows:
            if'error'in row:
                continue
            path=Path(row['path']);digest=hashlib.sha256(path.read_bytes()).hexdigest()
            assert digest==row['sha256'],f'Checksum mismatch: {path}'
            with path.open('rb') as opaque:
                assert opaque.read(9)==b'SIMPLE  =',f'Not a FITS primary header: {path}'
            assert path.stat().st_size%2880==0,f'Not FITS-block aligned: {path}'
            verified_row=dict(row)
            if group['split']!='final' and open_development_pixels:
                verified_row['native_quality']=development_metadata(path)
                assert verified_row['native_quality']['physical_obsid_header']==row['obs_id']
                midpoint=verified_row['native_quality']['time_header']['MJD-AVG']
                if midpoint is not None:
                    assert abs(float(midpoint)-(row['t_min_mjd']+row['t_max_mjd'])/2)<1e-5
            verified.append(verified_row)
        results.append(dict(group_id=group['group_id'],parent_group_id=parent,split=group['split'],center=group['center'],
                            detector=group.get('detector'),downloaded_exposures=len(verified),
                            pixels_opened=group['split']!='final'and open_development_pixels,
                            downloads=verified))
    report={'created_utc':datetime.now(timezone.utc).isoformat(),
            'plan_sha256':hashlib.sha256((root/'partition-plan.json').read_bytes()).hexdigest(),
            'source_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'minimum_group_center_separation_deg':min(p[2]for p in pairs),
            'physical_obsids_cross_parent_or_split':0,'final_pixels_opened':False,
            'groups':results}
    (root/'audit.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('/tmp/spaceapps-v3-native-data'))
    parser.add_argument('--development-pixels',action='store_true')
    args=parser.parse_args()
    report=audit(args.root,args.development_pixels)
    print(json.dumps({k:v for k,v in report.items()if k!='groups'},indent=2))
    for g in report['groups']:
        print(g['group_id'],g['split'],g['downloaded_exposures'],'pixels_opened',g.get('pixels_opened',False))


if __name__=='__main__':
    main()
