"""Assemble same-parent cadence manifests/symlinks without opening any FITS.

Final variants stay under quarantine_final. This does not authorize evaluation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('/tmp/spaceapps-v3-native-data'))
    args=parser.parse_args()
    groups=json.loads((args.root/'selected-groups.json').read_text())
    supplements=json.loads((args.root/'cadence-supplement-plan.json').read_text())['groups']
    for supplement in supplements:
        group=next(g for g in groups if g['group_id']==supplement['parent_group_id'])
        base=args.root/('quarantine_final'if group['split']=='final'else'development')
        destination=base/'variants'/(group['group_id']+'-augmented')
        destination.mkdir(parents=True,exist_ok=True)
        rows=[]
        seen=set()
        for directory in [base/group['group_id'],base/supplement['group_id']]:
            for row in json.loads((directory/'downloads.json').read_text()):
                assert row['obs_id']not in seen
                seen.add(row['obs_id'])
                source=Path(row['path']).resolve()
                link=destination/source.name
                if link.is_symlink():
                    assert link.resolve()==source
                elif link.exists():
                    raise ValueError(f'Refusing to replace file {link}')
                else:
                    link.symlink_to(source)
                rows.append(dict(row,path=str(link),source_path=str(source)))
        rows.sort(key=lambda r:r['t_min_mjd'])
        assert 3<=len(rows)<=8
        (destination/'downloads.json').write_text(json.dumps(rows,indent=2)+'\n')
        metadata={k:group[k]for k in ['group_id','split','center','detector']}
        metadata.update(variant='short_cluster_plus_predeclared_cadence_supplement',
                        parent_group_id=group['group_id'],independent_parents=1,
                        pixels_opened=False,final_quarantine=group['split']=='final',
                        exposures=len(rows),source_directories=[str(base/group['group_id']),str(base/supplement['group_id'])])
        (destination/'group.json').write_text(json.dumps(metadata,indent=2)+'\n')
        print(destination,len(rows),flush=True)


if __name__=='__main__':
    main()
