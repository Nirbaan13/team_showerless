"""Validate paired trial identity and freshly indexed measured-peak geometry."""
import argparse,gzip,hashlib,json
from pathlib import Path
import numpy as np


def read(path):
    with gzip.open(path,'rt')as stream:return json.load(stream)


def validate(path):
    report=read(path);source=read(report['source_cache'])
    assert hashlib.sha256(Path(report['source_cache']).read_bytes()).hexdigest()==report['source_cache_sha256']
    assert len(report['fields'])==len(source['fields'])==270
    assert report['detector_settings']=={**source['detector_settings'],'psf_sigma':.8}
    total_candidates=spatial=resolved=errors=preexisting=0
    for field,original in zip(report['fields'],source['fields']):
        for key in ['parent_id','partition','seed','trajectory_id','speed_px_hour','brightness','expected_xy','injected_flux']:
            assert field[key]==original[key],key
        assert 'common_attribution_eligible_sigma12_profiles'not in field
        expected=np.asarray(field['expected_xy']);count=len(field['features']);total_candidates+=count
        assert all(len(field[key])==count for key in ['matches','baseline','candidate_epochs','candidate_positions_xy','expected_span_among_candidate_epochs_px'])
        assert set(field['matches'])<={-2,0}
        geometry={g['candidate_index']:g for g in field['matched_geometry']}
        assert set(geometry)=={i for i,label in enumerate(field['matches'])if label==0}
        for i,(epochs,positions)in enumerate(zip(field['candidate_epochs'],field['candidate_positions_xy'])):
            assert len(field['features'][i])==6
            truth=expected[epochs];xy=np.asarray(positions);offset=np.linalg.norm(xy-truth,axis=1)
            matched=bool(np.all(offset<=1.5));assert matched==(field['matches'][i]==0)
            span=float(np.max(np.linalg.norm(truth[:,None,:]-truth[None,:,:],axis=-1)))
            assert np.isclose(span,field['expected_span_among_candidate_epochs_px'][i])
            if matched:
                g=geometry[i];assert g['epochs']==epochs
                assert np.isclose(g['true_displacement_px'],span)
                assert np.isclose(g['max_offset_px'],offset.max())
        control_match=any(np.all(np.linalg.norm(np.asarray(xy)-expected[epochs],axis=1)<=1.5)for xy,epochs in zip(report['control']['candidate_positions_xy'],report['control']['candidate_epochs']))
        assert field['preexisting_control_match']==control_match
        assert field['attribution_eligible']==(not control_match)
        preexisting+=int(control_match);errors+=int('detector_error'in field)
        spatial+=int(bool(geometry));resolved+=int(any(g['true_displacement_px']>=3 for g in geometry.values()))
    return dict(path=str(path),sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),parent_id=report['parent_id'],profile=report['profile'],min_speed=report['detector_settings']['min_speed'],planned_trials=270,candidate_rows=total_candidates,raw_spatial_recovered=spatial,raw_resolved_span_ge3px=resolved,preexisting_control_matches=preexisting,detector_error_trials=errors,geometry_validated=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',action='append',required=True);p.add_argument('--output',required=True);a=p.parse_args();reports=[validate(path)for path in a.cache]
    Path(a.output).write_text(json.dumps(reports,indent=2,allow_nan=False)+'\n');print(json.dumps(reports,indent=2))
if __name__=='__main__':main()
