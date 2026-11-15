#!/usr/bin/env python3
"""Build strict v1 service overlays while retaining the original VPS images."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from bundle import Engine, normalize_image_id, validate_inventory, validate_loaded_image


def source_revision(root):
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    if not re.fullmatch(r'[0-9a-f]{40}',revision):raise ValueError('A full Git revision is required')
    owned=['frontend/src','ml/service.py','ml/catalogue_db.py','science/archive_gateway.py','science/motion/live.py','backend/python/irsa_cutout.py']
    dirty=subprocess.check_output(['git','status','--porcelain','--untracked-files=all','--',*owned],cwd=root,text=True)
    if dirty.strip():raise ValueError('Commit service source changes before building versioned real-only images')
    return revision


def inspect(engine, reference):
    return engine.json('image','inspect',reference)[0]


def build(inventory_path, output, executable='podman'):
    root=Path(__file__).resolve().parents[2]
    inventory=validate_inventory(json.loads(Path(inventory_path).read_text()))
    engine=Engine(executable)
    revision=source_revision(root)
    result=copy.deepcopy(inventory)
    result['source_images']=inventory.get('source_images') or list({x['image_id']:x for x in inventory['services'].values()}.values())
    result['demo_profile']='v1-real'
    result['service_source_revision']=revision
    env=os.environ.copy();env.update({'VITE_DEMO_REAL_ONLY':'true','VITE_BACKEND_URL':'/backend'})
    subprocess.run(['npm','run','build'],cwd=root/'frontend',env=env,check=True)
    for name, kind in [('frontend','frontend'),('ml-inference','ml')]:
        original=inventory['services'][name]
        actual=inspect(engine,original['image'])
        validate_loaded_image(original,actual)
        tags=actual.get('RepoTags') or []
        base=next((t for t in tags if t.startswith('localhost/')),original['image'])
        if not re.fullmatch(r'[A-Za-z0-9_./:@-]+',base):raise ValueError('Unsafe source image reference')
        tag='localhost/spaceapps-demo-'+kind+'-real:'+revision
        with tempfile.TemporaryDirectory(prefix='spaceapps-real-variant-') as tmp:
            stage=Path(tmp)
            common=f'FROM {base}\nARG DEMO_REVISION={revision}\nLABEL org.opencontainers.image.revision="${{DEMO_REVISION}}" org.opencontainers.image.source="https://github.com/Nirbaan13/team_showerless" org.spaceapps.demo.profile="v1-real" org.spaceapps.demo.parent_image="{original["image_id"]}"\n'
            if kind=='frontend':
                shutil.copytree(root/'frontend/dist',stage/'dist')
                (stage/'dist/demo-mode.json').write_text(json.dumps({'profile':'v1-real','real_only':True,'revision':revision,'parent_image_id':original['image_id']}))
                text=common+'ENV FRONTEND_REVISION=${DEMO_REVISION}\nRUN rm -rf /usr/share/nginx/html/*\nCOPY dist/ /usr/share/nginx/html/\nRUN printf \'{"version":"%s"}\\n\' "$DEMO_REVISION" > /usr/share/nginx/html/frontend-version.json\n'
            else:
                for rel in ['ml/service.py','ml/catalogue_db.py','science/archive_gateway.py','science/motion/live.py','backend/python/irsa_cutout.py']:
                    shutil.copy2(root/rel,stage/Path(rel).name)
                text=common+'ENV APP_REVISION=${DEMO_REVISION} DEMO_REAL_ONLY=1\nCOPY --chown=10001:10001 service.py catalogue_db.py /app/\nCOPY --chown=10001:10001 archive_gateway.py /app/science/\nCOPY --chown=10001:10001 live.py /app/science/motion/\nCOPY --chown=10001:10001 irsa_cutout.py /app/backend/python/irsa_cutout.py\n'
            (stage/'Dockerfile').write_text(text)
            pull='--pull=never' if executable=='podman' else '--pull=false'
            format_args=['--format','docker'] if executable=='podman' else []
            engine.call('build',pull,*format_args,'--file',str(stage/'Dockerfile'),'--tag',tag,str(stage))
        built=inspect(engine,tag)
        result['services'][name]={'image':tag,'image_id':normalize_image_id(built['Id']),'revision':revision,'os':built['Os'],'architecture':built['Architecture'],'parent_image_id':original['image_id'],'demo_profile':'v1-real','derived_from_deployed_image':True}
        if built.get('Variant'):result['services'][name]['variant']=built['Variant']
    Path(output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'inventory':str(output),'revision':revision,'overlays':[result['services'][n]['image'] for n in ['frontend','ml-inference']]}))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--engine',choices=['docker','podman'],default='podman')
    args=parser.parse_args();build(args.inventory,args.output,args.engine)
