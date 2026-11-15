"""Check imported code against exact text and replay fixed cached DEV fields.

This is post-generation controlled integrity evidence. Original workers did not
record code-object fingerprints; this report does not retroactively claim they did.
"""
from pathlib import Path
import gzip,json,sys,types,hashlib,inspect,gc
import numpy as np
import cache_synthetic as generator
import features


def canonical(value):
    if isinstance(value,types.CodeType):
        return dict(bytecode=value.co_code.hex(),constants=[canonical(v)for v in value.co_consts],names=value.co_names,varnames=value.co_varnames,freevars=value.co_freevars,cellvars=value.co_cellvars,argcount=value.co_argcount,posonlyargcount=value.co_posonlyargcount,kwonlyargcount=value.co_kwonlyargcount,flags=value.co_flags,exceptiontable=value.co_exceptiontable.hex())
    if isinstance(value,slice):return {'slice':[canonical(value.start),canonical(value.stop),canonical(value.step)]}
    if isinstance(value,frozenset):return {'frozenset':sorted((canonical(v)for v in value),key=repr)}
    if isinstance(value,complex):return {'complex':[value.real,value.imag]}
    if value is Ellipsis:return {'ellipsis':True}
    if isinstance(value,bytes):return {'bytes':value.hex()}
    if isinstance(value,tuple):return [canonical(v)for v in value]
    return value


def fingerprints(module):
    result={}
    for name,value in vars(module).items():
        if inspect.isfunction(value)and value.__module__==module.__name__:
            result[name]=hashlib.sha256(json.dumps(canonical(value.__code__),sort_keys=True).encode()).hexdigest()
        elif inspect.isclass(value)and value.__module__==module.__name__:
            for method,fn in vars(value).items():
                if inspect.isfunction(fn):result[name+'.'+method]=hashlib.sha256(json.dumps(canonical(fn.__code__),sort_keys=True).encode()).hexdigest()
    return result


def main():
    path=Path(features.__file__);text=path.read_bytes();sourcehash=hashlib.sha256(text).hexdigest()
    fresh=types.ModuleType('features_source_verified');fresh.__file__=str(path)
    exec(compile(text,str(path),'exec',dont_inherit=True,optimize=sys.flags.optimize),fresh.__dict__)
    actual=fingerprints(features);expected=fingerprints(fresh)
    assert actual==expected,'Imported bytecode disagrees with current source text'
    assert features.CONTRACT==fresh.CONTRACT and features.FEATURE_CONTRACT_SHA256==fresh.FEATURE_CONTRACT_SHA256
    generator.FeatureContext=fresh.FeatureContext
    checks=[]
    configurations=[('train',3000000,[0,1,2,3,9,10,11,15,50,99,127,511,999,2047,4095,4999]),('validation',3100000,[0,1,2,3,9,10,11,15,50,99,127,255,511,767,998,999])]
    for partition,start,offsets in configurations:
        cache=Path('/tmp/spaceapps-v4-ranker')/f'synthetic-{partition}-30-v1.json.gz'
        wanted={start+offset for offset in offsets}
        with gzip.open(cache,'rt')as handle:payload=json.load(handle)
        assert payload['source_sha256'][str(path)]==sourcehash
        selected={f['seed']:f for f in payload['fields']if f['seed']in wanted}
        assert set(selected)==wanted
        del payload;gc.collect()
        generator.initialize(generator.BASE/'backend/inference/training/calibration/instrument-epsf-bank.npz',{},partition)
        for seed in sorted(wanted):
            reference=selected[seed];replay=generator.generate(seed);assert replay['error']is None,replay['error']
            for key in ['features','features_v4','candidate_ids','candidate_epochs','candidate_positions_xy','matches','scores_c13','truth_count','times_hours','latent_sha256','feature_diagnostics']:
                assert replay[key]==reference[key],f'Cached scientific field differs at seed{seed} key{key}'
            checks.append(dict(seed=seed,partition=partition,candidate_rows=len(replay['features']),scientific_fields_bitwise_equal=True))
        del selected;gc.collect()
    output=dict(schema_version=4,purpose=__doc__,feature_source_path=str(path),feature_source_sha256=sourcehash,feature_contract_sha256=features.FEATURE_CONTRACT_SHA256,imported_function_fingerprints=actual,fresh_compile_function_fingerprints=expected,all_function_code_matches_text=True,replayed_fields=checks,total_candidate_rows=sum(c['candidate_rows']for c in checks),source_and_cached_observables_agree=True,original_workers_recorded_bytecode_fingerprints=False,limitations='Controlled deterministic32fieldreplay and currentimport verification, not a claim of originalperworkerfingerprintlogging; module size changed during prior streamingrefactor and source was stablebefore/during cachegeneration.')
    target=Path('/tmp/spaceapps-v4-ranker/feature-import-integrity.json');target.write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(dict(success=True,fields=len(checks),candidate_rows=output['total_candidate_rows'],source=sourcehash,function_count=len(actual))),flush=True)

if __name__=='__main__':main()
