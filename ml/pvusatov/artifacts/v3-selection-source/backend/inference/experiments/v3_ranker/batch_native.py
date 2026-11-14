"""Snapshot declared native development groups and cache in bounded processes."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

def run_group(item):
    group,variant=item
    if group.startswith('train'):partition='train';seed=1500000+int(group[-2:]);trajectories=60
    elif group.startswith('validation'):partition='validation';seed=1600000+int(group[-2:]);trajectories=30
    else:raise ValueError('only train/validation groups allowed')
    source=Path('/tmp/spaceapps-v3-native-data/development')/group
    metadata=json.loads((source/'group.json').read_text())
    if metadata['split']!=partition:raise ValueError('split mismatch')
    downloads=json.loads((source/'downloads.json').read_text())
    if len(downloads)<3:raise ValueError('three complete epochs required')
    destination=Path('/tmp/spaceapps-v3-ranker/native-inputs')/(group+'-'+variant)
    destination.mkdir(parents=True,exist_ok=True)
    for row in downloads:shutil.copy2(source/Path(row['path']).name,destination/Path(row['path']).name)
    (destination/'downloads.json').write_text(json.dumps(downloads,indent=2)+'\n')
    (destination/'group.json').write_text(json.dumps(metadata,indent=2)+'\n')
    output=Path('/tmp/spaceapps-v3-ranker')/('native-'+group+'-'+variant+'.json.gz')
    command=[sys.executable,'backend/inference/experiments/v3_ranker/cache_native.py','--input-dir',str(destination),'--parent-id',group,'--partition',partition,'--ra',str(metadata['center'][0]),'--dec',str(metadata['center'][1]),'--seed',str(seed),'--trajectories',str(trajectories),'--output',str(output)]
    with output.with_suffix('.log').open('w') as log:
        result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
    return dict(group=group,epochs=len(downloads),returncode=result.returncode,output=str(output))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('groups',nargs='+');p.add_argument('--workers',type=int,default=6);p.add_argument('--variant',default='short-v1');args=p.parse_args()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(run_group,[(g,args.variant) for g in args.groups]):print(json.dumps(row),flush=True)
