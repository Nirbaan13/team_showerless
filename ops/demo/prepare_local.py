import json,subprocess,os
from pathlib import Path
root=Path(__file__).resolve().parent; build=Path(os.environ.get('DEMO_BUILD_ROOT','/tmp/spaceapps-demo-build'));project='spaceapps-demo-v1-preview'
inventory=json.loads((build/'inventory-v1.json').read_text())['services']
text=(root/'compose.yaml').read_text()
replacements={'DEMO_PROJECT':project,'DEMO_PORT:-8080':'18080'}
for service,key in [('api','API'),('frontend','FRONTEND'),('ml-inference','ML')]:
 item=inventory[service];replacements[key+'_IMAGE:?verified '+('ML' if key=='ML' else key)+' image required']=item['image_id'];replacements[key+'_PLATFORM']=item['os']+'/'+item['architecture']
replacements['FRONTEND_IMAGE:?verified frontend image required']=inventory['frontend']['image_id']
for key,value in replacements.items():text=text.replace('${'+key+'}',value)
if '${' in text:raise ValueError('Unresolved compose variable')
(build/'compose.run.yaml').write_text(text)
engine='podman';image=inventory['api']['image_id']
for suffix in ['api-data','ml-data','runtime-config']:
 name=project+'_'+suffix
 found=subprocess.run([engine,'volume','inspect',name],capture_output=True).returncode==0
 if not found:subprocess.run([engine,'volume','create','--label','org.spaceapps.demo.project='+project,name],check=True)
 if suffix=='runtime-config':
  script="from pathlib import Path; import shutil,os; p=Path('/target/default.conf'); shutil.copyfile('/source/nginx.conf',p); os.chown(p,10001,10001)"
  source=root
 else:
  source=build/'seed-v1'/suffix
  script="from pathlib import Path; import shutil,os; p=Path('/target'); marker=p/'.direct-v1';\nif not marker.exists():\n if any(p.iterdir()): raise RuntimeError('Refusing nonempty volume')\n shutil.copytree('/source',p,dirs_exist_ok=True)\n for f in [p,*p.rglob('*')]: os.chown(f,10001,10001)\n marker.write_text('real-only-v1')\n"
 subprocess.run([engine,'run','--rm','--network','none','--user','0:0','--entrypoint','python3','--volume',str(source)+':/source:ro','--volume',name+':/target',image,'-c',script],check=True)
subprocess.run([engine,'compose','-p',project,'-f',str(build/'compose.run.yaml'),'config','--quiet'],check=True)
print('READY: podman compose -p '+project+' -f '+str(build/'compose.run.yaml')+' up -d --wait')
