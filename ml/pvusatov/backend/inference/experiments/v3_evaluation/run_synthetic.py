"""Freeze-gated paired whole-field synthetic evaluation; no runtime fitting."""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
from experiments.v3_evaluation import run_native as shared

_CONTEXT={}


def _one(task):
    freeze_path,freeze_sha256,seeds=task
    key=(str(freeze_path),freeze_sha256)
    if key not in _CONTEXT:
        _CONTEXT.clear()
        freeze=shared.validate_freeze(freeze_path,freeze_sha256);science=shared._science(freeze)
        try:
            if science.model_errors:raise ValueError('paired model initialization failed')
            bank=science.load_bank(freeze['synthetic']['calibration_bank']['path']);bank_error=None
        except Exception as exc:bank=None;bank_error=shared._error('model_loading'if science.model_errors else'calibration_loading',exc)
        _CONTEXT[key]=(freeze,science,bank,bank_error)
    freeze,science,bank,bank_error=_CONTEXT[key]
    results=[]
    for seed in seeds:
        error=bank_error;images=times=None;truth=[];mode='unavailable';metadata={}
        if error is None:
            try:
                images,times,truth,mode,metadata=science.simulate(seed,bank,
                    extended=seed%freeze['synthetic']['generator']['extended_every_nth_field']==0,
                    varying_psf=freeze['synthetic']['generator']['varying_psf'])
            except Exception as exc:error=shared._error('simulation',exc)
        identity=dict(seed=seed,mode=mode,metadata=metadata,expected_xy=[p.tolist()for p in truth]if error is None else None,
                      times_hours=[]if times is None else times.tolist(),registered_shape=[]if images is None else list(images.shape),
                      truth_count_known=error is None,attribution_eligible=True)
        measurements=shared._measures(images,times,freeze,science)if error is None else{
            (profile,role):shared._empty_measurement(error)for profile in shared.PROFILES for role in shared.ROLES}
        results.append({key:shared._field(identity,value,truth,key[1],science,False)for key,value in measurements.items()})
    return results


def run(freeze_path,freeze_sha256,output_dir):
    freeze=shared.validate_freeze(freeze_path,freeze_sha256);shared._threads()
    if Path(__file__).resolve()!=Path(freeze['sources']['run_synthetic']['path']):raise ValueError('freeze synthetic runner path differs')
    destinations={(profile,role):Path(output_dir)/f'synthetic-{profile}-{role}.json.gz'for profile in shared.PROFILES for role in shared.ROLES}
    if any(p.exists()for p in destinations.values()):raise ValueError('refusing to overwrite evaluation cache')
    seeds=freeze['synthetic']['seeds'];writers={};pool=None
    try:
        for(profile,role),path in destinations.items():
            metadata=shared._metadata(freeze,profile,role,kind='synthetic',parent_id='synthetic-whole-fields',
                input_sources=[freeze['synthetic']['calibration_bank']],times_hours=[],registered_shape=[],center_deg=None,
                independent_group='whole synthetic field',independent_parent_fields=len(seeds),all_derivatives_correlated=False,
                candidates_within_field_dependent=True,parent_field_seeds=seeds,generator=freeze['synthetic']['generator'])
            writers[profile,role]=shared.AtomicCache(path,metadata)
        # One field per task caps candidate-heavy queued results independently of final size.
        batches=[[seed]for seed in seeds]
        tasks=[(str(freeze_path),freeze_sha256,batch)for batch in batches]
        if freeze['runtime']['workers']==1:results=map(_one,tasks)
        else:
            pool=ProcessPoolExecutor(max_workers=freeze['runtime']['workers']);results=shared._bounded_map(pool,_one,tasks,freeze['runtime']['workers'])
        for batch in results:
            for fields in batch:
                for key,field in fields.items():writers[key].append(field)
        results=[(writer.finish(),writer.summary)for writer in writers.values()]
        shared.write_run_manifest('synthetic',freeze,results,output_dir)
        return[path for path,summary in results]
    except BaseException:
        for writer in writers.values():writer.abort()
        raise
    finally:
        if pool is not None:pool.shutdown(cancel_futures=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--freeze',required=True);parser.add_argument('--freeze-sha256',required=True);parser.add_argument('--output-dir',required=True);args=parser.parse_args()
    paths=run(args.freeze,args.freeze_sha256,args.output_dir);print(json.dumps(paths,indent=2))
    if not shared._json(Path(args.output_dir)/'run-synthetic-manifest.json')['evaluation_complete']:raise SystemExit(2)

if __name__=='__main__':main()
