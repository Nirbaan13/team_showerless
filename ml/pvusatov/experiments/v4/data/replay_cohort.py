"""Portable, read-only metadata replay; needs no native files or original /tmp."""
from pathlib import Path
import csv,gzip,hashlib,json,re
import xml.etree.ElementTree as ET
OWN=Path(__file__).resolve().parent;NAMESPACE=OWN.parents[2]
EXPECTED=dict(plan='55e0203db48bc294c6b1f4999d0582d1d9030d9e3e1b558d9f00364ac797e6cd',selection='eacc056ab2506487ee57228e1cf8c634f80e728318ef51658f6b471b267d3ef1',query='446b8527f595ebb5e4fac2f1041e729bc7b0eb9a1b86c015e48c76f8b8dd3cca',audit='f0361395a0787ba4140238d714acc2da693db077a2a7700fc0709b572540ea44')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_text())
def translated(path):
    marker='/ml/pvusatov/'
    if marker not in path:raise ValueError('Only published namespace metadata may be opened')
    target=(NAMESPACE/path.split(marker,1)[1]).resolve()
    if not target.is_relative_to(NAMESPACE):raise ValueError('Metadata path escape')
    return target

def main():
    for name,key in [('partition-plan.json','plan'),('selected-groups.json','selection'),('query-provenance.json','query'),('complete-audit.json','audit')]:
        if sha(OWN/name)!=EXPECTED[key]:raise ValueError('Prospective metadata trust anchor changed: '+name)
    plan=load(OWN/'partition-plan.json');actual=load(OWN/'selected-groups.json');index=load(OWN/'query-provenance.json');audit=load(OWN/'complete-audit.json')
    source=(OWN/'acquire.py').read_bytes()
    if hashlib.sha256(source).hexdigest()!=audit['data_source_sha256']['acquire.py']:raise ValueError('Selection source changed')
    namespace={'__name__':'v4_portable_selection_replay','__file__':str(OWN/'acquire.py')}
    exec(compile(source,str(OWN/'acquire.py'),'exec'),namespace)
    select=namespace['select']
    prior=[]
    for reference in plan['input_provenance']:
        path=translated(reference['path'])
        if sha(path)!=reference['sha256']:raise ValueError('Prior source metadata changed')
        prior.append(path)
    excluded={row['physical_obsid']for row in load(prior[2])['observations']}
    with prior[3].open()as handle:excluded|={re.sub(r'D[1-6]$','',row['observation_id'])for row in csv.DictReader(handle)}
    if excluded!=set(plan['excluded_physical_obsids']):raise ValueError('Previous-cohort exclusions do not match declaration')
    discoveries={};archives=0
    for query in index['queries']:
        discovery=None;xml_rows=None
        for reference in query['files']:
            path=OWN/'query-evidence'/Path(reference['published_path']).name;compressed=path.read_bytes();payload=gzip.decompress(compressed);archives+=1
            if hashlib.sha256(compressed).hexdigest()!=reference['gzip_sha256']or hashlib.sha256(payload).hexdigest()!=reference['uncompressed_sha256']:raise ValueError('Exact query metadata bytes changed')
            if reference['original_path'].endswith('discovery.json'):discovery=json.loads(payload)
            else:
                root=ET.fromstring(payload);columns=[node.attrib['name']for node in root.findall('.//{*}TABLE/{*}FIELD')]
                xml_rows=[dict(zip(columns,[''.join(cell.itertext()).strip()for cell in row]))for row in root.findall('.//{*}TABLEDATA/{*}TR')]
        if discovery is None or discovery.get('rows')!=xml_rows:raise ValueError('Parsed discovery does not match exact official VOTABLE')
        discoveries[query['parent_id']]=discovery
    replay=[]
    for group in plan['groups']:
        result=select(group,discoveries[group['parent_id']]['rows'],excluded);replay.append(result)
        excluded.update(row['obs_id']for row in result.get('exposures',[]))
    if replay!=actual:raise ValueError('Prospective selection replay differs')
    dev=load(OWN/'development-handoff.json');final=load(OWN/'final-quarantine-audit.json')
    if sha(OWN/'development-handoff.json')!=audit['development_handoff_sha256']or sha(OWN/'final-quarantine-audit.json')!=audit['final_quarantine_handoff_sha256']:raise ValueError('Completed handoff changed')
    selected={group['parent_id']:group for group in actual};observed={row['physical_obsid']:row for row in audit['observations']};seen=set(plan['excluded_physical_obsids']);count=0
    for group in dev['groups']+final['groups']:
        path=translated(group['downloads_manifest']['path'])
        if sha(path)!=group['downloads_manifest']['sha256']:raise ValueError('Native manifest metadata changed')
        rows=load(path)
        if len(rows)!=8 or {row['obs_id']for row in rows}!={row['obs_id']for row in selected[group['parent_id']]['exposures']}:raise ValueError('Native metadata parent selection differs')
        for row in rows:
            if row['obs_id']in seen:raise ValueError('Cross-parent or prior physical OBSID reuse')
            seen.add(row['obs_id']);count+=1;record=observed[row['obs_id']]
            if(record['parent_id'],record['split'],record['sha256'],record['bytes'],record['url'])!=(group['parent_id'],group['split'],row['sha256'],row['bytes'],row['url']):raise ValueError('Native byte-audit metadata linkage differs')
    if count!=224 or len(observed)!=224:raise ValueError('Cohort count differs')
    print(json.dumps(dict(passes=True,prospective_selection_replayed_exactly=True,exact_query_archives_verified=archives,prior_metadata_sources_verified=len(prior),selected_physical_observations=count,independent_parents=28,parent_counts={'train':8,'validation':8,'final':12},cross_parent_or_prior_obsid_overlap=0,raw_native_files_opened=False,scope='Published metadata/hash linkage only; original raw native bytes are not rechecked by this portable replay',source_sha256=sha(__file__)),indent=2))
if __name__=='__main__':main()
