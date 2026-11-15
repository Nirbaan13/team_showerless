"""Build separate development handoff and final opaque-byte manifests.

Requires the completed append-only audit. Does not authorize final pixel access.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from acquire import write_json

ROOT=Path('/tmp/spaceapps-v3-native-data')
EXPANSION=ROOT/'expansion-v2'
CODE=Path(__file__).resolve().parent
BACKEND=CODE.parents[2]


def hashed(path):
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def final_group(parent,directory,short_directory,center,detector,stratum):
    rows=json.loads((directory/'downloads.json').read_text())
    assert len(rows)==8,f'Incomplete primary final variant {parent}'
    assert len({r['obs_id']for r in rows})==8
    for row in rows:
        source=Path(row['path'])
        assert hashlib.sha256(source.read_bytes()).hexdigest()==row['sha256']
    return dict(parent_group_id=parent,independent_parent_fields=1,split='final',stratum=stratum,
                primary_variant='augmented8',directory=str(directory),center=center,detector=detector,
                physical_midpoint_span_hours=24*((max(r['t_max_mjd']for r in rows)+max(r['t_min_mjd']for r in rows))/2-
                                                   (min(r['t_max_mjd']for r in rows)+min(r['t_min_mjd']for r in rows))/2),
                downloads=rows,pixels_opened=False,secondary_short_directory=str(short_directory))


def main():
    audit=json.loads((EXPANSION/'audit-expanded-v2.json').read_text())
    assert all(g['downloaded_exposures']==g['planned_exposures']==8 for g in audit['new_groups'])
    assert audit['final_pixels_opened']is False and audit['cross_parent_physical_obsid_overlap']==0
    originals=json.loads((ROOT/'selected-groups.json').read_text())
    expanded=json.loads((EXPANSION/'selected-groups.json').read_text())
    finals=[]
    for group in originals:
        if group['split']=='final':
            parent=group['group_id']
            finals.append(final_group(parent,ROOT/'quarantine_final/variants'/(parent+'-augmented'),
                                       ROOT/'quarantine_final'/parent,group['center'],group['detector'],'original_predeclared_field'))
    for group in expanded:
        if group['split']=='final':
            parent=group['parent_group_id']
            finals.append(final_group(parent,EXPANSION/'quarantine_final'/group['group_id'],
                                       EXPANSION/'quarantine_final/variants'/(parent+'-short'),group['center'],group['detector'],group['stratum']))
    assert len(finals)==10
    seen=set()
    for group in finals:
        for row in group['downloads']:
            assert row['obs_id']not in seen
            seen.add(row['obs_id'])
    final_manifest=dict(schema_version=2,designation='quarantined_final_metadata_and_byte_audit_only',
                        independent_parent_fields=10,native_mefs=80,primary='augmented8 per parent',
                        secondary='short variants, same parents; no N inflation',final_pixels_opened=False,
                        model_or_evaluation_frozen_by_this_file=False,groups=finals)
    write_json(EXPANSION/'final-byte-audit-v2.json',final_manifest)
    development=[dict(parent_group_id=g['parent_group_id'],directory=str(EXPANSION/'development'/g['group_id']),
                       center=g['center'],detector=g['detector'],stratum=g['stratum'],
                       native_epochs=g['downloaded_exposures'],span_hours=g['metadata_span_hours'])
                 for g in audit['new_groups']if g['split']=='validation']
    write_json(EXPANSION/'development-handoff-v2.json',dict(schema_version=2,designation='additional_validation_DEVELOPMENT_only',groups=development))
    evidence=EXPANSION/'evidence'
    source_paths=[ROOT/'data-handoff.json',EXPANSION/'partition-plan.json',EXPANSION/'selected-groups.json',
                  EXPANSION/'audit-expanded-v2.json',EXPANSION/'final-byte-audit-v2.json',EXPANSION/'development-handoff-v2.json',
                  evidence/'orientation-evidence.json',CODE/'expand_v2.py',CODE/'audit_expansion_v2.py',
                  CODE/'orientation_evidence.py',Path(__file__),
                  BACKEND/'docs/implementation/ML-NATIVE-V3-DATA-EXPANSION-V2.AI.md',
                  BACKEND/'inference/training/evaluate_background.py',BACKEND/'inference/ml_inference/prepare.py']
    report=dict(schema_version=2,purpose='Expanded native-data handoff; coordinator still owns model/code freeze and final pixel authorization',
                sources=[hashed(p)for p in source_paths],counts=audit['counts'],final_pixels_opened=False,
                cross_parent_physical_obsid_overlap=0,minimum_expansion_separation_deg=audit['minimum_new_to_existing_or_new_center_separation_deg'],
                official_orientation_evidence=dict(url='https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp.pdf',
                    version='2.1',document_date='2026-11-10',pages=[52,59,60,74,81],pdf=hashed(evidence/'SPHEREx_Expsupp-v2.1.pdf'),
                    marker_source=hashed(CODE/'orientation_evidence.py'),marker_evidence=hashed(evidence/'orientation-evidence.json'),
                    maximum_marker_centroid_error_px=.02414033838337186,scope='SWIR1–3; MWIR4–6 unsupported'))
    write_json(EXPANSION/'data-handoff-v2.json',report)
    print(json.dumps(report,indent=2))
    print('handoff_sha256',hashlib.sha256((EXPANSION/'data-handoff-v2.json').read_bytes()).hexdigest())


if __name__=='__main__':
    main()
