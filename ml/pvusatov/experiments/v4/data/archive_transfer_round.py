"""Append-only transfer error/resumption evidence; no native payload access."""
from pathlib import Path
from datetime import datetime,timezone
import json
from acquire import OWN,ROOT,digest

def main():
    selected=json.loads((OWN/'selected-groups.json').read_text());directory=OWN/'transfer-attempts'/'round01';directory.mkdir(parents=True,exist_ok=True)
    copies=[];missing=[]
    for group in selected:
        parent=group['parent_id'];raw=ROOT/('quarantine_final'if group['split']=='final'else'development')/parent
        data=json.loads((raw/'downloads.json').read_text())
        if len(data)==len(group['exposures']):continue
        missing.append(parent)
        for name in ['group.json','downloads.json','download-failures.json']:
            source=raw/name
            if not source.exists():continue
            target=directory/(parent+'-'+name)
            with target.open('xb')as f:f.write(source.read_bytes())
            copies.append(dict(original_path=str(source),snapshot_path=str(target),sha256=digest(target),bytes=target.stat().st_size))
    output=dict(schema_version=4,recorded_utc=datetime.now(timezone.utc).isoformat(),scope='Metadata-only preserved transfer-attempt history before retrying exact same selected URLs; no selection change',
        plan_sha256=digest(OWN/'partition-plan.json'),selection_sha256=digest(OWN/'selected-groups.json'),incomplete_parents=missing,files=copies)
    with(directory/'snapshot-manifest.json').open('x')as f:json.dump(output,f,indent=2);f.write('\n')
    print(' '.join(missing),flush=True)
if __name__=='__main__':main()
