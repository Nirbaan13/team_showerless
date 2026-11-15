"""Narrow-filter detector caches for exact existing v3 native development trials."""
import argparse,gzip,hashlib,json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from experiments.v3_detection import native_scan

def one(path):
    native_scan.CONFIGS=[(.8,4.)]
    result=native_scan.one(path)
    with gzip.open(result['path'],'rt')as s:payload=json.load(s)
    fields=[]
    for field in payload['fields']:
        method=field.pop('methods')['sigma0.8_snr4.0']
        fields.append({**field,**method,'attribution_eligible':not method['preexisting_control_match']})
    payload['fields']=fields;payload['detector_settings']={**native_scan.SETTINGS,'psf_sigma':.8}
    payload['real_unknown_candidates_unlabeled']=True
    payload['control']=dict(features=payload.pop('control_features')['sigma0.8_snr4.0'])
    output=Path(result['path']).with_name(Path(result['path']).name.replace('-scan.json.gz','-sigma08.json.gz'))
    with gzip.open(output,'wt')as s:json.dump(payload,s,allow_nan=False)
    result['path']=str(output);result['sha256']=hashlib.sha256(output.read_bytes()).hexdigest();return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',action='append',required=True);p.add_argument('--workers',type=int,default=4);p.add_argument('--output',required=True);a=p.parse_args();results=[]
    with ProcessPoolExecutor(max_workers=a.workers)as pool:
        for result in pool.map(one,a.cache):results.append(result);print(json.dumps(result),flush=True)
    Path(a.output).write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__':main()
