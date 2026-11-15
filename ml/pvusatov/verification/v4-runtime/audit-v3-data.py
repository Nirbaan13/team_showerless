"""Read-only engineering evidence audit; no FINAL, model session or inference.

Default replays local artifact/input hashes. --ssh-pngs additionally reads seven
existing engineering/DEV PNGs with cat over strict SSH, then Pillow in UtilsAI.
Only this audit's JSON/report and local /tmp PNG copies are written.
"""
from __future__ import annotations
import argparse,datetime,hashlib,json,math,re,shlex,subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent;REPO=HERE.parents[3];EVID=HERE/'vps-evidence-v3'
GRAPH='c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35'
META='472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13'
BUNDLE='809638b1148a94574816c6827ad4f14303639fe6c33e2bc37f926731d3171829'
EXPECTED_SOURCE={'pipeline.py':'1d4a7793f89f190cb580c2b9da7defdf2c6ecc864842d3173ceb9c099dda19b0','median_reference.py':'353f4d0a7b6032d18158df99cf90fa992d3cb0bfc714c96e50c05e75c4b18a2e','prepare.py':'27ef087aa19f394eaf16ee19c0801ed6c7557a79a7ea77b3410445363f4624ec','features.py':'8433495da9d0eda745903a9d63f430e3fc8b7c283b2ad7aded96511059b91282','model.py':'cd7154e2bbba3595b656c4207e9a6afe890a35e1f12ffa4203ab0b7cf6a74598'}
LIMITS=dict(Memory=1073741824,MemorySwap=1073741824,NanoCpus=1000000000,PidsLimit=64,NetworkMode='none',ReadonlyRootfs=True)
MODES=('presets','maximum','native-coverage')

def require(condition,message):
    if not condition:raise ValueError(message)
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(path):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError('duplicate JSON key')
            out[k]=v
        return out
    return json.loads(Path(path).read_text(),object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in()).throw(ValueError('nonfinite JSON')))
def artifact(root,row):
    path=(root/row['path']).resolve();require(path.is_relative_to(root.resolve()),'artifact escapes evidence root')
    require(path.stat().st_size==row['bytes']and digest(path)==row['sha256'],'artifact byte/hash mismatch: '+row['path']);return path

def model_identity(value):
    require(value.get('sha256')==GRAPH and value.get('feature_source_sha256')==EXPECTED_SOURCE['features.py'],'wrong graph/features used')
    require(value.get('selected_feature_indices')==list(range(27))and value.get('full_feature_count')==30,'feature subset differs')
    require(value.get('score_kind')=='sigmoid_pairwise_utility'and value.get('model_family')=='RankNetTreeBoost','score family differs')

def png_resources(result):
    resources=result['resources'];names=[r['name']for r in resources]
    require(len(names)==len(set(names)),'duplicated PNG resource')
    require(all(Path(r['name']).name==r['name']and r['name'].endswith('.png')and r['media_type']=='image/png'and 0<r['size_bytes']<=1048576 for r in resources),'invalid PNG metadata')
    require(all(f[key]in names for f in result['frames']for key in ('image_url','difference_url')),'frame PNG missing from resource manifest')
    return resources

def fetch_pngs(samples):
    from PIL import Image
    output=Path('/tmp/spaceapps-v4-runtime-png-audit');output.mkdir(parents=True,exist_ok=True);records=[]
    for sample in samples:
        remote=sample['remote_path'];require(remote.startswith('/opt/spaceapps/ml-pvusatov-v4-probe/evidence-v3-')and remote.endswith('.png'),'non-engineering PNG path')
        command=['ssh','-i','/home/usatovpavel/.ssh/spaceapps-netherlands-admin-20261114','-o','UserKnownHostsFile=/home/usatovpavel/.local/state/spaceapps-migration-20261114/known_hosts','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=15','root@144.124.238.101','cat -- '+shlex.quote(remote)]
        value=subprocess.run(command,capture_output=True,timeout=30);require(value.returncode==0,'read-only PNG fetch failed: '+sample['identity']);require(len(value.stdout)==sample['bytes'],'PNG byte size differs: '+sample['identity'])
        path=output/(sample['identity']+'.png');path.write_bytes(value.stdout)
        with Image.open(path)as image:require(image.format=='PNG','unexpected image format');image.verify()
        with Image.open(path)as image:
            image.load();size=list(image.size);mode=image.mode;extrema=image.getextrema();black=all(pair==(0,0)for pair in extrema)if isinstance(extrema[0],tuple)else extrema==(0,0)
            if sample.get('must_be_black'):require(black,'zero-coverage PNG contains nonzero pixels')
            require(size==sample['dimensions'],'PNG dimensions differ')
        records.append(dict(identity=sample['identity'],remote_path=remote,local_tmp_path=str(path),bytes=len(value.stdout),sha256=hashlib.sha256(value.stdout).hexdigest(),dimensions=size,pixel_mode=mode,png_verified=True,all_pixels_black=black,required_black=sample.get('must_be_black',False)))
    return records

def audit(ssh_pngs=False):
    capsule_path=EVID/'resource-capsule-manifest-v3.json';capsule=read(capsule_path);require(len(capsule['files'])==25,'expected25 evidence files')
    require(len({r['path']for r in capsule['files']})==25,'duplicate evidence path')
    for row in capsule['files']:artifact(EVID,row)
    bundle_path=HERE/'bundle-v3-manifest.json';require(digest(bundle_path)==BUNDLE,'wrong bundle manifest');bundle=read(bundle_path);require(len(bundle['files'])==26,'expected26 bundle inputs')
    files={row['path']:row for row in bundle['files']};require(len(files)==26,'duplicate bundle path');external=[]
    for row in bundle['files']:
        source=Path(row['source']);source=source if source.is_absolute()else REPO/source
        if not source.is_relative_to(REPO):
            require(source.parent==Path('/tmp/spaceapps-v4-evaluation/coverage-fixture-v3')and source.name in {'0.fits','1.fits','2.fits','3.fits','request.json'},'non-engineering external input');external.append(str(source))
        require(source.stat().st_size==row['bytes']and digest(source)==row['sha256'],'bundle source/hash changed: '+str(source))
    for name,value in EXPECTED_SOURCE.items():require(files['inference/ml_inference/'+name]['sha256']==value,'wrong bound runtime source')
    require(files['inference/models/ranker.onnx']['sha256']==GRAPH and files['inference/models/metadata.json']['sha256']==META,'wrong bound model pair')
    receipts=read(EVID/'host-container-receipt-v3.json');hostruns=read(EVID/'host-probe-run-v3.json');require(len(receipts)==len(hostruns)==3,'host evidence modes missing')
    receipt={r['name']:r for r in receipts};host={r['mode']:r for r in hostruns};require(set(host)==set(MODES),'host modes differ');versions=None;image_ids=set();volumes=[];reports=[];samples=[]
    for mode in MODES:
        record=host[mode];r=receipt[record['name']];inspected=read(EVID/f'evidence-v3-{mode}/host-inspect.json');require(inspected==record,'host inspect/run mismatch')
        require(r['host']=={**LIMITS,'Tmpfs':{'/tmp':'rw,size=256m,mode=1777'}}and record['limits']==LIMITS,'host hard limits differ')
        require(r['user']=='app'and r['image_id']==record['image_id'],'configured UID/image differs');image_ids.add(r['image_id'])
        require(record['docker_start_exit']==0 and record['state']['ExitCode']==0 and record['state']['OOMKilled']is False and record['state']['Running']is False and r['state']['ExitCode']==0 and r['state']['OOMKilled']is False,'container did not finish cleanly')
        mounts={p['Destination']:p for p in r['mounts']};require(set(mounts)=={'/probe','/evidence','/app/data'},'unexpected mount')
        require(mounts['/probe']['Type']=='bind'and mounts['/probe']['RW']is False and mounts['/probe']['Source'].endswith('/bundle-v3'),'input bundle not readonly')
        require(mounts['/evidence']['Type']=='bind'and mounts['/evidence']['RW']is True and mounts['/evidence']['Source'].endswith('/evidence-v3-'+mode),'evidence mount differs')
        require(mounts['/app/data']['Type']=='volume'and mounts['/app/data']['RW']is True,'inherited data volume differs');volumes.append(mounts['/app/data']['Source'])
        proof=read(EVID/f'evidence-v3-{mode}/{mode}/proof.json');require(proof['mode']==mode and proof['passes']is True and proof['schema_version']==4,'probe failed')
        require(proof['model_sha256']==GRAPH and proof['bundle_manifest_sha256']==BUNDLE and proof['probe_source_sha256']==files['vps_probe.py']['sha256'],'probe binding differs')
        require(proof['python']=='3.12.3','wrong VPS interpreter');versions=proof['versions']if versions is None else versions;require(proof['versions']==versions,'probe versions differ')
        require(proof['fitting_import_guard']['source_sha256']==files['inference/sitecustomize.py']['sha256']and proof['fitting_import_guard']['forbidden']==['joblib','skl2onnx','sklearn','training'],'fitting import guard differs')
        for stage in ('cgroup_before','cgroup_after'):
            group=proof[stage];require(group['memory.max']=='1073741824'and group['memory.swap.max']=='0'and group['cpu.max']=='100000 100000','effective cgroup changed')
            events=dict(line.split()for line in group['memory.events'].splitlines());require(all(int(events[k])==0 for k in ('max','oom','oom_kill')),'memory limit/OOM event occurred')
        peak=int(proof['cgroup_after']['memory.peak']);require(0<peak<=1073741824,'cgroup peak exceeds bound')
        report=dict(mode=mode,elapsed_seconds=proof['elapsed_seconds'],whole_cgroup_peak_mib=peak/1048576,hard_one_cpu_one_gib_no_swap=True,configured_user='app',readonly_rootfs=True,network='none',pids_limit=64,tmpfs_mib=256,exit_code=0,oom_killed=False)
        if mode=='presets':
            require([x['preset']for x in proof['results']]==['comet-d2','comet-d6','vesta-d3','vesta-d6'],'preset coverage differs');report['cases']=[]
            for case in proof['results']:
                identity=case['preset'];path=EVID/f'evidence-v3-presets/presets/{identity}/result.json';result=read(path);require(digest(path)==case['result_sha256']and 'error'not in result,'preset result changed/failed');model_identity(result['model']);require(result['model']==case['model'],'preset model differs');resources=png_resources(result);require(len(resources)==case['pngs']and len(result['candidates'])==case['candidates'],'preset counts differ')
                require(all(c['score']is None and c['score_kind']=='flagged_bloom_evidence'if c['method']=='bloom_track'else c['score_kind']=='sigmoid_pairwise_utility'for c in result['candidates']),'wrong score semantics')
                report['cases'].append(dict(preset=identity,candidates=case['candidates'],declared_pngs=case['pngs']))
                frame=result['frames'][0];resource=next(x for x in resources if x['name']==frame['image_url']);samples.append(dict(identity=identity+'-frame000',remote_path=mounts['/evidence']['Source']+'/presets/'+identity+'/'+resource['name'],bytes=resource['size_bytes'],dimensions=[frame['width'],frame['height']]))
        elif mode=='maximum':
            raw=proof['results'][0]['raw_proof'];raw_path=EVID/'evidence-v3-maximum/maximum/maximum-rss-raw.json';require(read(raw_path)==raw and digest(raw_path)==proof['results'][0]['raw_proof_sha256'],'maximum raw proof changed')
            expected={Path(row['path']).name:row['sha256']for row in bundle['files']if row['path'].startswith('inference/ml_inference/')};require(raw['source_sha256']==expected,'maximum executed-source vector differs')
            require(raw['model_sha256']==GRAPH and raw['model_metadata_sha256']==META and raw['measurement_source_sha256']==files['inference/measure_maximum.py']['sha256'],'maximum source/model binding differs');model_identity(raw['runtime_model'])
            require(raw['shape']==[32,512,512]and len(raw['cpu_affinity'])==1 and raw['candidate_count']==1 and raw['detection_counts']==[32]and raw['resources']==66,'maximum workload changed')
            require(raw['settings']['min_snr']==10. and raw['settings']['max_candidates']==3,'controlled workload options differ')
            report.update(shape=raw['shape'],measured_tracks=1,track_epochs=32,min_snr=10.,publication_cap=3,declared_pngs=66,child_peak_rss_mib=raw['worker_peak_rss_mib'],child_cli_seconds=raw['elapsed_seconds'],scope='Controlled maximum shape; not worst candidate density; maximum PNGs were transient and cannot be byte-reverified')
        else:
            case=proof['results'][0];path=EVID/'evidence-v3-native-coverage/native-coverage/native-coverage/result.json';result=read(path);require(digest(path)==case['result_sha256']and'error'not in result,'native engineering result changed/failed');model_identity(result['model']);resources=png_resources(result);frames=result['frames']
            require(case['engineering_fixture']is True and case['physical_epochs']==4 and len(frames)==4 and case['retained_frame_ids']==['0','1','2','3']==[f['frame_id']for f in frames],'native engineering epoch dropped')
            require([f['physical_observation_id']for f in frames]==['coverage-'+str(i)for i in range(4)],'native physical identities changed')
            require([f['sha256']for f in frames]==[files[f'coverage-fixture/{i}.fits']['sha256']for i in range(4)],'native result/input identity mismatch')
            require([f['coverage_fraction']for f in frames]==[1.,0.,1.,1.]and'observations_without_usable_requested_coverage'in result['warnings'],'blank native epoch fabricated/unreported')
            require(len(resources)==case['pngs']==8,'native PNG count differs');require(all(abs(f['midpoint_mjd']-(61000+i/24))<1e-9 for i,f in enumerate(frames)),'physical dates changed')
            for label,frame_index,key,black in [('native-blank-frame',1,'image_url',True),('native-blank-difference',1,'difference_url',True),('native-covered-frame',0,'image_url',False)]:
                frame=frames[frame_index];resource=next(x for x in resources if x['name']==frame[key]);samples.append(dict(identity=label,remote_path=mounts['/evidence']['Source']+'/native-coverage/native-coverage/'+resource['name'],bytes=resource['size_bytes'],dimensions=[frame['width'],frame['height']],must_be_black=black))
            report.update(physical_epochs=4,frame_ids=case['retained_frame_ids'],zero_coverage_epoch=1,declared_pngs=8,coverage_warning=True,candidate_count=len(result['candidates']))
        reports.append(report)
    require(len(image_ids)==1 and len(set(volumes))==3,'probe image or isolated anonymous volumes differ')
    old_path=HERE/'vps-evidence/evidence-v1-maximum/maximum/proof.json';old=read(old_path);require(old['model_sha256']==GRAPH,'prototype comparison graph differs');old_raw=old['results'][0]['raw_proof'];require(old_raw['shape']==[32,512,512]and old_raw['settings']['min_snr']==10. and old_raw['settings']['max_candidates']==3 and old_raw['candidate_count']==1 and old_raw['detection_counts']==[32]and old_raw['resources']==66,'prototype workload differs');require(old['python']=='3.12.3'and old['versions']==versions,'prototype software environment differs')
    maximum=next(r for r in reports if r['mode']=='maximum');comparison=dict(reference='Earlier V4 prototype, not production V3; one observation each',old_proof_sha256=digest(old_path),old_elapsed_seconds=old['elapsed_seconds'],old_cgroup_peak_mib=int(old['cgroup_after']['memory.peak'])/1048576,new_elapsed_seconds=maximum['elapsed_seconds'],new_cgroup_peak_mib=maximum['whole_cgroup_peak_mib'],observed_speedup=old['elapsed_seconds']/maximum['elapsed_seconds'])
    pngs=fetch_pngs(samples)if ssh_pngs else[]
    return dict(schema_version=4,status='PASS',audited_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='Engineering evidence only; no FINAL, inference/scoring, model sessions, deployment or VPS writes',evidence_files_verified=25,evidence_manifest_sha256=digest(capsule_path),bundle_inputs_verified=26,bundle_manifest_sha256=BUNDLE,external_engineering_inputs=external,model_sha256=GRAPH,model_metadata_sha256=META,selected_source_sha256=EXPECTED_SOURCE,probe_image_id=next(iter(image_ids)),python='3.12.3',versions=versions,probes=reports,prototype_comparison=comparison,png_sample_bytes_independently_verified=len(pngs),png_samples=pngs,limits=['Numeric process UID not recorded; Docker configured user app verified','Writable output bind, 256 MiB tmpfs and distinct inherited anonymous /app/data volumes exist; rootfs and input bundle are read-only','Optional PNG-byte verification covers only sampled retained images; maximum-run PNGs were deleted with its temporary directory','Controlled one-track maximum shape at minSNR 10/publication cap 3 is not a worst-density/default-options guarantee','One run per mode; observed timings are not p95, concurrency or throughput guarantees','Five bundle inputs live outside git in the declared engineering fixture directory; full input rehash requires those exact files','Standalone maximum child text says no cgroup claim; outer actual cgroup proof supplies the hard bound','Resource/integration engineering audit does not substitute for independent recovery or promotion approval'])

def markdown(value):
    lines=['# Independent VPS engineering audit: bundle v3','',f"Verified **{value['evidence_files_verified']} evidence artifacts and {value['bundle_inputs_verified']} bundle inputs**. Graph `{GRAPH}` and metadata `{META}` match the selected V4 package. No FINAL data, inference/model session, service/container change or VPS write was performed.",'','| Probe | Wall time | Whole-cgroup peak |','|---|---:|---:|']
    for row in value['probes']:lines.append(f"| {row['mode']} | {row['elapsed_seconds']:.3f} s | {row['whole_cgroup_peak_mib']:.2f} MiB |")
    lines+=['','All three completed with one CPU quota, 1 GiB hard memory, no swap, no OOM/max-memory events, network none, read-only rootfs/input bundle, configured user `app`, PID cap 64 and 256 MiB `/tmp`. Writable evidence binds and three separate inherited anonymous `/app/data` volumes were present; no production data bind appears in the receipts. Python 3.12.3 and dependency versions agree across probes.','',f"The native engineering fixture retains all four physical IDs/timestamps and reports epoch 1 at zero coverage with its warning. Independently fetched/decoded PNG samples: **{value['png_sample_bytes_independently_verified']}**. {('Both blank-epoch frame and difference PNGs are entirely black; four preset frames and one covered engineering frame were also verified.' if value['png_sample_bytes_independently_verified'] == 7 else 'The archived probe reports black blank-epoch PNGs; this local-only replay did not independently recheck PNG bytes.')}",'',f"The controlled 32×512×512 maximum ran one measured 32-epoch track at minSNR 10 and publication cap 3, generating 66 transient resources. Its child CLI took {next(r for r in value['probes']if r['mode']=='maximum')['child_cli_seconds']:.3f}s / {next(r for r in value['probes']if r['mode']=='maximum')['child_peak_rss_mib']:.2f}MiB child maxRSS. The outer cgroup measurement includes the probe process and child; it is not Docker CLI RSS.",'',f"Earlier **V4 prototype**, same graph/workload: {value['prototype_comparison']['old_elapsed_seconds']:.2f}s / {value['prototype_comparison']['old_cgroup_peak_mib']:.2f}MiB versus {value['prototype_comparison']['new_elapsed_seconds']:.2f}s / {value['prototype_comparison']['new_cgroup_peak_mib']:.2f}MiB now ({value['prototype_comparison']['observed_speedup']:.2f}× observed wall-time ratio). This is not a production V3 comparison or a repeated latency study.",'','Limits:']
    lines+=['','\n'.join('- '+s for s in value['limits']),'','Run `python ml/pvusatov/verification/v4-runtime/audit-v3-data.py --ssh-pngs` using the shared UtilsAI interpreter for the optional Pillow byte checks. SSH uses the externally held key and strict known-host verification; it only cats the seven declared existing engineering/DEV PNGs. Omit the flag for local metadata/hash replay; that does not repeat PNG-byte verification. Default execution prints a check result without overwriting the published audit; add `--write` explicitly to produce a new JSON/report.']
    return '\n'.join(lines)+'\n'

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ssh-pngs',action='store_true');parser.add_argument('--write',action='store_true');args=parser.parse_args();value=audit(args.ssh_pngs)
    if args.write:
        (HERE/'audit-v3-data.json').write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');(HERE/'audit-v3-data.AI.md').write_text(markdown(value))
    print(json.dumps(dict(status=value['status'],evidence=25,inputs=26,pngs=value['png_sample_bytes_independently_verified'],probes=[{k:r[k]for k in ('mode','elapsed_seconds','whole_cgroup_peak_mib')}for r in value['probes']])))
