"""Publish compact exact query evidence; no native pixels copied/read."""
from pathlib import Path
import gzip,json,hashlib
from acquire import ROOT,OWN,digest

def main():
    plan=json.loads((OWN/'partition-plan.json').read_text());records=[];folder=OWN/'query-evidence';folder.mkdir(exist_ok=True)
    for group in plan['groups']:
        discovery=ROOT/'metadata'/group['parent_id']/'discovery.json';record=json.loads(discovery.read_text());files=[]
        sources=[discovery]+[Path(attempt['source']['path'])for attempt in record['attempts']if'source'in attempt]
        for source in sources:
            destination=folder/(group['parent_id']+'-'+source.name+'.gz')
            payload=source.read_bytes();compressed=gzip.compress(payload,mtime=0)
            if destination.exists():
                if destination.read_bytes()!=compressed:raise ValueError('Published query evidence changed')
            else:destination.write_bytes(compressed)
            files.append(dict(original_path=str(source),uncompressed_sha256=hashlib.sha256(payload).hexdigest(),uncompressed_bytes=len(payload),published_path=str(destination),gzip_sha256=digest(destination),gzip_bytes=len(compressed)))
        records.append(dict(parent_id=group['parent_id'],split=group['split'],center=group['center'],query_url=record.get('query_url'),rows=len(record.get('rows',[])),status=record.get('status'),error=record.get('error'),files=files))
    result=dict(schema_version=4,scope='Exact official IRSA SIA query metadata bytes compressed for offline provenance; NO native image pixels',plan_sha256=digest(OWN/'partition-plan.json'),queries=records,
        total_gzip_bytes=sum(f['gzip_bytes']for r in records for f in r['files']))
    path=OWN/'query-provenance.json'
    if path.exists():raise ValueError('Append-only query publication already exists')
    path.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(path=str(path),sha256=digest(path),queries=len(records),total_gzip_bytes=result['total_gzip_bytes']),indent=2))
if __name__=='__main__':main()
