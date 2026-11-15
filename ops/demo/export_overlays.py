#!/usr/bin/env python3
"""Export derived images as a modern Docker archive without legacy symlinks."""
import argparse,gzip,json,shutil,subprocess,tarfile
from pathlib import Path,PurePosixPath

def export(inventory_path, output):
 inventory=json.loads(Path(inventory_path).read_text())
 images=list(dict.fromkeys(x['image'] for x in inventory['services'].values() if x.get('derived_from_deployed_image')))
 raw=Path(output).with_name('overlay-podman-export.tar.gz')
 with raw.open('wb') as destination:
  save=subprocess.Popen(['podman','save','--format','docker-archive','--multi-image-archive',*images],stdout=subprocess.PIPE)
  with gzip.GzipFile(fileobj=destination,mode='wb',compresslevel=1) as compressed:shutil.copyfileobj(save.stdout,compressed,1024*1024)
  save.stdout.close()
  if save.wait():raise RuntimeError('Podman image export failed')
 with tarfile.open(raw,'r:gz') as archive:
  manifest=json.load(archive.extractfile('manifest.json'));required={'manifest.json'}
  for image in manifest:required.add(image['Config']);required.update(image['Layers'])
  for name in required:
   path=PurePosixPath(name)
   if path.is_absolute() or '..' in path.parts or not archive.getmember(name).isfile():raise ValueError('Unsafe image payload '+name)
  copied=set()
  with tarfile.open(output,'w:gz',compresslevel=1) as target:
   for member in archive.getmembers():
    if member.name in required:
     if member.name in copied:raise ValueError('Duplicate image payload')
     target.addfile(member,archive.extractfile(member));copied.add(member.name)
  if copied!=required:raise ValueError('Incomplete image export')
 print(json.dumps({'images':images,'output':str(output)}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--inventory',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
 a=p.parse_args();export(a.inventory,a.output)
