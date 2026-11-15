#!/usr/bin/env python3
"""Layer the reviewed core revision onto the captured VPS API image."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from bundle import Engine, normalize_image_id, validate_inventory, validate_loaded_image
from build_variants import validate_built_revision

FILES = {
 'backend/python/irsa_mirror.py':'integrations/irsa_mirror.py',
 'backend/python/irsa_catalog.py':'integrations/irsa_catalog.py',
 'backend/python/irsa_cutout.py':'backend/python/irsa_cutout.py',
 'backend/docs/openapi.yaml':'docs/openapi.yaml',
 'science/archive_gateway.py':'science/archive_gateway.py',
 'pipeline/service.py':'pipeline/service.py',
 'pipeline/spherex/query.py':'pipeline/spherex/query.py',
 'pipeline/scripts/grab_cutout.py':'pipeline/scripts/grab_cutout.py',
 'compose.yaml':'deploy/compose.yaml',
}

def build(inventory_path, source, revision, output, executable='podman'):
 source=Path(source).resolve()
 def git(*args):return subprocess.check_output(['git',*args],cwd=source,text=True).strip()
 if not re.fullmatch(r'[0-9a-f]{40}',revision):raise ValueError('Require full core source revision')
 head=git('rev-parse','HEAD')
 if git('rev-parse',head+'^{tree}') != git('rev-parse',revision+'^{tree}'):
  raise ValueError('Compiled worktree must have exactly the requested source tree')
 if git('status','--porcelain','--','backend','ml/pvusatov/backend','science','pipeline'):
  raise ValueError('Core source worktree must be clean before compilation')
 env=os.environ.copy();env['APP_REVISION']=revision
 subprocess.run(['./sbtw','stage'],cwd=source/'backend',env=env,check=True)
 stage=source/'backend/target/stage'
 inventory=validate_inventory(json.loads(Path(inventory_path).read_text()))
 api=inventory['services']['api']
 parent_id=api.get('parent_image_id',api['image_id'])
 original=next(x for x in inventory['source_images'] if x['image_id']==parent_id)
 engine=Engine(executable)
 actual=engine.json('image','inspect',original['image'])[0];validate_loaded_image(original,actual)
 base=next((t for t in actual.get('RepoTags',[]) if t.startswith('localhost/')),original['image'])
 if not re.fullmatch(r'[A-Za-z0-9_./:@-]+',base):raise ValueError('Unsafe base image reference')
 tag='localhost/spaceapps-demo-api-real:'+revision
 with tempfile.TemporaryDirectory(prefix='spaceapps-real-api-') as tmp:
  context=Path(tmp)
  shutil.copytree(stage,context/'stage')
  for rel,target in FILES.items():
   dest=context/'files'/target;dest.parent.mkdir(parents=True,exist_ok=True)
   dest.write_bytes(subprocess.check_output(['git','show',revision+':'+rel],cwd=source))
  dockerfile=(f'FROM {base}\nUSER root\n'
   f'LABEL org.opencontainers.image.revision="{revision}" org.opencontainers.image.source="https://github.com/Nirbaan13/team_showerless" org.spaceapps.demo.profile="v1-real" org.spaceapps.demo.parent_image="{original["image_id"]}"\n'
   f'ENV APP_REVISION={revision} IRSA_CUTOUT_SCRIPT=/app/backend/python/irsa_cutout.py\n'
   'RUN rm -rf /app/classes /app/lib\n'
   'COPY --chown=10001:10001 stage/ /app/\nCOPY --chown=10001:10001 files/ /app/\n'
   'RUN /opt/inference-venv/bin/python -c "import sys; sys.path.insert(0,\'/app/integrations\'); import irsa_catalog; from backend.python.irsa_cutout import cutout"\nUSER app\n')
  (context/'Dockerfile').write_text(dockerfile)
  args=['build','--pull=never','--format','docker'] if executable=='podman' else ['build','--pull=false']
  engine.call(*args,'--file',str(context/'Dockerfile'),'--tag',tag,str(context))
 built=engine.json('image','inspect',tag)[0]
 validate_built_revision(built,revision,'APP_REVISION')
 record={'image':tag,'image_id':normalize_image_id(built['Id']),'revision':revision,'os':built['Os'],'architecture':built['Architecture'],'parent_image_id':original['image_id'],'demo_profile':'v1-real','derived_from_deployed_image':True,'compiled_tree':git('rev-parse',revision+'^{tree}')}
 inventory['services']['api']=record;inventory['services']['pipeline']=copy.deepcopy(record)
 inventory['api_source_revision']=revision
 Path(output).write_text(json.dumps(inventory,indent=2)+'\n')
 print(json.dumps({'api_image':tag,'core_revision':revision,'inventory':str(output)}))

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--inventory',required=True,type=Path);p.add_argument('--source',required=True,type=Path)
 p.add_argument('--revision',required=True);p.add_argument('--output',required=True,type=Path)
 p.add_argument('--engine',choices=['podman','docker'],default='podman')
 a=p.parse_args();build(a.inventory,a.source,a.revision,a.output,a.engine)
