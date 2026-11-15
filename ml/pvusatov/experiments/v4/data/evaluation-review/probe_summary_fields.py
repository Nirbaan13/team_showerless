"""DEV smoke field-validation probes; reports no score/outcome values."""
from pathlib import Path
import copy,gzip,hashlib,json,types
OWN=Path(__file__).resolve().parent;EVAL=OWN.parents[1]/'evaluation';DEV=Path('/tmp/spaceapps-v4-evaluation/dev-smoke-v2')
def main():
    source=EVAL/'summarize.py';m=types.ModuleType('review_current_summary');m.__file__=str(source);exec(compile(source.read_bytes(),str(source),'exec'),m.__dict__)
    native=json.loads(gzip.decompress(next((DEV/'native').glob('*.json.gz')).read_bytes()));synthetic=json.loads(gzip.decompress(next((DEV/'synthetic').glob('*.json.gz')).read_bytes()));cases=[]
    def check(name,field,domain,cache):
        try:m.validate_field(field,domain,times=cache.get('times_hours')if domain=='native'else None,shape=cache.get('registered_shape')if domain=='native'else None);accepted=True;error=None
        except Exception as e:accepted=False;error=type(e).__name__+': '+str(e)
        cases.append(dict(probe=name,accepted=accepted,error=error))
    n=copy.deepcopy(native['fields'][0]);check('valid_native',n,'native',native)
    n['attribution_eligible']=not n['attribution_eligible'];check('contradictory_native_attribution',n,'native',native)
    n=copy.deepcopy(native['fields'][0]);n['truth_count_known']=False;check('native_unknown_truth_count_flag',n,'native',native)
    n=copy.deepcopy(native['fields'][0]);n['velocity_xy_hour']=[999.,999.];check('native_velocity_not_matching_recorded_truth',n,'native',native)
    s=copy.deepcopy(synthetic['fields'][0]);check('valid_synthetic',s,'synthetic',synthetic);s['mode']='not_a_generator_mode';s['metadata']={};check('bogus_synthetic_mode_empty_generator_metadata',s,'synthetic',synthetic)
    result=dict(scope='DEV smoke caches only; validation acceptance booleans, no score/outcome reporting; no FINAL',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),probes=cases);print(json.dumps(result,indent=2));(OWN/'summary-field-repro.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
