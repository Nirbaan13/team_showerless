"""Losslessly publish query bytes compactly; omit anonymous HTTP cookies."""
from pathlib import Path
import gzip,hashlib,json,shutil
OWN=Path(__file__).resolve().parent;CASE=OWN/'point-grid-0750';PRIVATE=Path('/tmp/spaceapps-v4-native-data/known_objects/metadata-originals')
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    destination=CASE/'xml-publication-index.json'
    if destination.exists():raise ValueError('Metadata publication already exists')
    PRIVATE.mkdir(parents=True,exist_ok=True);rows=[];redactions=[]
    for path in sorted((CASE/'evidence').glob('*.xml')):
        raw=path.read_bytes();compressed=gzip.compress(raw,mtime=0);out=path.with_suffix('.xml.gz');assert gzip.decompress(compressed)==raw;out.write_bytes(compressed)
        backup=PRIVATE/path.name
        if backup.exists():assert sha(backup.read_bytes())==sha(raw)
        else:backup.write_bytes(raw)
        rows.append(dict(original_path=str(path),published_path=str(out.relative_to(CASE)),original_sha256=sha(raw),original_bytes=len(raw),published_sha256=sha(compressed),published_bytes=len(compressed)));path.unlink()
    # Only unauthenticated IRSA anonymous cookies; no scientific content altered.
    requests=list((CASE/'evidence').glob('*.request.json'))+[OWN/'evidence/later-minimal-diagnostic.json']
    for path in requests:
        raw=path.read_bytes();value=json.loads(raw);headers=value.get('headers',{});removed=[k for k in headers if k.lower()in('set-cookie','set-cookie2')]
        if removed:
            backup=PRIVATE/('http-'+sha(raw)+'.json');backup.write_bytes(raw)
            for key in removed:del headers[key]
            value.update(redacted_header_names=removed,original_http_metadata_sha256=sha(raw),original_http_metadata_retained_external=True);path.write_text(json.dumps(value,indent=2)+'\n');redactions.append(dict(path=str(path.relative_to(OWN)),redacted_header_names=removed,original_metadata_sha256=sha(raw)))
    value=dict(role='Exact original query paths preserved by lossless gzip translation; original manifests unchanged',xml_files=rows,original_xml_bytes=sum(r['original_bytes']for r in rows),published_xml_bytes=sum(r['published_bytes']for r in rows),http_metadata_redactions=redactions,native_pixels_included=False)
    destination.write_text(json.dumps(value,indent=2)+'\n');print('XML',len(rows),value['original_xml_bytes'],'->',value['published_xml_bytes'],'bytes; cookie metadata redactions',len(redactions))
if __name__=='__main__':main()
