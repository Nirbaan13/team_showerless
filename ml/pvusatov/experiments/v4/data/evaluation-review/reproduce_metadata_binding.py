"""Metadata-only component probes; no raw FITS, models, or science calls."""
from pathlib import Path
import copy,hashlib,json,types
OWN=Path(__file__).resolve().parent;DATA=OWN.parent;EVALUATION=DATA.parent/'evaluation'
def main():
    path=EVALUATION/'freeze.py';source=path.read_bytes();m=types.ModuleType('review_exact_freeze');m.__file__=str(path);exec(compile(source,str(path),'exec'),m.__dict__)
    acquisition=json.loads((DATA/'partition-plan.json').read_text());final=[g for g in acquisition['groups']if g['split']=='final'];final.sort(key=lambda g:g['parent_id'])
    value=dict(schema_version=4,status='frozen',scope='final',authorized_final=True,runtime=dict(workers=6,math_threads=1,max_frames=32,max_grid=512),proposal_policy='c13-sigma08-v1',detector_settings=m.PROFILE,models=dict(baseline=dict(artifact=dict(sha256=m.C13)),candidate={}),native=dict(parents=[dict(parent_id=g['parent_id'],seed=3950001+i,center_deg=[(g['center'][0]+.01)%360,g['center'][1]])for i,g in enumerate(final)],region=dict(width_arcmin=6.,height_arcmin=6.,pixel_scale_arcsec=6.15,mask_policy='motion')),synthetic=dict(seeds=list(range(3900000,3903000))))
    m.validate_plan(value)
    development=copy.deepcopy(value);development.update(scope='development',authorized_final=False);development['native']['parents']=development['native']['parents'][:1];development['native']['parents'][0]['seed']=3800001;development['synthetic']['seeds']=[3800000];m.validate_plan(development)
    handoff=json.loads((DATA/'development-handoff.json').read_text());g=next(g for g in handoff['groups']if g['parent_id']=='v4-train04');rows=json.loads(Path(g['downloads_manifest']['path']).read_text());parents=[]
    for i in range(2):
        parents.append(dict(parent_id=f'dev-relabel-{i}',observations=[{**r,'obs_id':f'fake-{i}-{j}'}for j,r in enumerate(rows)]))
    m.check_physical_ids(parents,{f'dummy-exclusion-{i}'for i in range(338)})
    evidence=dict(scope='Component checks only; no full fixture yet, no FITS/model/pixel/final access',source_sha256=hashlib.sha256(source).hexdigest(),final_centers_shifted_by_deg=.01,changed_final_centers_accepted_by_validate_plan=True,development_final_parent_name_accepted_by_validate_plan=development['native']['parents'][0]['parent_id'],same_eight_TRAIN04_bytehashes_reused_under_two_fake_parent_IDs_accepted_by_check_physical_ids=True,actual_unique_bytehashes=len({r['sha256']for p in parents for r in p['observations']}),claimed_physical_ids=len({r['obs_id']for p in parents for r in p['observations']}),arbitrary_dummy_exclusion_set_count=338)
    (OWN/'metadata-binding-repro.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence,indent=2))
if __name__=='__main__':main()
