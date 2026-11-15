"""Project all authorized scored cache rows; no pixels/model/scoring imports."""
from pathlib import Path
import gzip
import hashlib
import json
import shutil
from datetime import datetime,timezone

HERE=Path(__file__).resolve().parent
REPAIR=HERE.parent
REPORT_SHA='15cabb840cb8af95771f3534f2b5adfb18caaff5f0e8b57ed678f858525f7e56'
EXCLUDE={'features','features_v4','feature_diagnostics','elapsed_seconds','rss_mib'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def project_field(field,source_hash,times=None,shape=None):
    value={k:v for k,v in field.items()if k not in EXCLUDE}
    value['feature_matrix_sha256']={k:hashlib.sha256(canonical(field[k])).hexdigest()for k in ['features','features_v4']}
    value['source_cache_sha256']=source_hash
    if times is not None:value['times_hours']=times
    if shape is not None:value['registered_shape']=shape
    value['projection_sha256']=hashlib.sha256(canonical(value)).hexdigest()
    return value


def main():
    report=json.loads((REPAIR/'report.json').read_text());assert sha(REPAIR/'report.json')==REPORT_SHA
    destination=HERE/'scored-fields.json.gz';assert not destination.exists()
    original=[];field_count=0
    with destination.open('wb')as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0,compresslevel=9)as stream:
        stream.write(b'{"schema_version":1')
        for domain in ['native','synthetic']:
            stream.write((',"'+domain+'":[\n').encode())
            for i,ref in enumerate(report['caches'][domain]):
                source=Path(ref['path']);assert sha(source)==ref['sha256'];original.append(ref['sha256'])
                with gzip.open(source,'rt')as handle:cache=json.load(handle)
                projected={k:v for k,v in cache.items()if k not in ['fields','control']}
                projected['source_cache_sha256']=ref['sha256']
                if domain=='native':projected['control']=project_field(cache['control'],ref['sha256'],cache['times_hours'],cache['registered_shape'])
                projected['fields']=[project_field(f,ref['sha256'],cache.get('times_hours'),cache.get('registered_shape'))for f in cache['fields']]
                field_count+=len(projected['fields'])
                if i:stream.write(b',\n')
                stream.write(canonical(projected));del cache,projected
            stream.write(b']')
        stream.write(b'}\n')
    assert field_count==6240
    for source,name in [('report.json','canonical-report.json'),('freeze.json','freeze.json'),('unblinding-record.json','unblinding-record.json'),('scientific-equality-proof.json','scientific-equality-proof.json')]:
        target=HERE/name;assert not target.exists();shutil.copyfile(REPAIR/source,target)
    files={p.name:dict(sha256=sha(p),bytes=p.stat().st_size)for p in sorted(HERE.iterdir())if p.is_file()and p.name not in ['manifest.json','portability-proof.json']}
    manifest=dict(schema_version=1,purpose='Complete portable scored accounting, not model/feature recomputation',created_utc=datetime.now(timezone.utc).isoformat(),
        canonical_report_sha256=REPORT_SHA,freeze_sha256='1225e2de97c38381818d9ccb3676c1d132701b02b8bc19dc09e0d1785c3e38e4',
        candidate_model_sha256='c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35',
        candidate_metadata_sha256='472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13',
        total_fields=6240,native_fields=3240,synthetic_fields=3000,files=files,original_cache_sha256=original,
        feature_hash_definition='sha256 of UTF-8 canonical JSON decoded matrix, sort_keys=true,separators comma/colon,allow_nan=false;features and features_v4 separately',
        field_projection_hash_definition='sha256 of same canonical JSON field excluding projection_sha256 itself',
        omitted_fields=sorted(EXCLUDE),native_context='Native cache times/shape copied into each field; all candidate/truth coordinate precision preserved as decoded JSON numbers',
        external_paths='Historical provenance strings only; portable verifier never follows them')
    (HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(fields=field_count,capsule_bytes=destination.stat().st_size,manifest_sha256=sha(HERE/'manifest.json'))))


if __name__=='__main__':main()
