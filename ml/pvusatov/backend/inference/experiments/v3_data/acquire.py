"""Bounded IRSA discovery/acquisition with predeclared field partitions.

Final FITS bytes are downloaded and hashed but never opened by this module.
Uses Python standard-library HTTP and XML only; no model imports or fitting.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


PLAN = {
    'schema_version': 1,
    'declared_utc': '2026-11-14T20:13:00Z',
    'unit': 'sky field containing all physical exposure OBSIDs and all detector/crop/version derivatives',
    'final_policy': 'Bytes and hash metadata only until coordinator freezes model/code; no final pixel access, injection, detection or scoring.',
    'detectors': [1, 2, 3],
    'cutout_size_deg': 0.12,
    'target_exposures_per_group': 5,
    'minimum_exposures_per_group': 3,
    'selection': 'Metadata only: one SWIR detector; earliest metadata cadence window with >=3 unique OBSIDs in <=1.5 hours; prefer five exposures and temporal span, alternate preferred detector by group index. Fallback earliest five unique exposures within <=48 hours, flagged long-cadence.',
    'groups': [
        {'group_id': 'train01', 'split': 'train', 'center': [15., -30.]},
        {'group_id': 'train02', 'split': 'train', 'center': [45., 20.]},
        {'group_id': 'train03', 'split': 'train', 'center': [75., -15.]},
        {'group_id': 'train04', 'split': 'train', 'center': [105., 40.]},
        {'group_id': 'train05', 'split': 'train', 'center': [150., -20.]},
        {'group_id': 'train06', 'split': 'train', 'center': [180., 25.]},
        {'group_id': 'train07', 'split': 'train', 'center': [240., -25.]},
        {'group_id': 'train08', 'split': 'train', 'center': [270., 35.]},
        {'group_id': 'validation01', 'split': 'validation', 'center': [30., 45.]},
        {'group_id': 'validation02', 'split': 'validation', 'center': [165., 5.]},
        {'group_id': 'validation03', 'split': 'validation', 'center': [300., -20.]},
        {'group_id': 'final01', 'split': 'final', 'center': [60., -45.]},
        {'group_id': 'final02', 'split': 'final', 'center': [135., 20.]},
        {'group_id': 'final03', 'split': 'final', 'center': [225., 15.]},
        {'group_id': 'final04', 'split': 'final', 'center': [330., 40.]},
    ],
    'excluded_development_fields': [[210.80227,54.34895], [127.69444,-39.17760]],
    'notes': ['M101, v2 final, comet and Vesta are v3 development only.',
              'Unknown unmodified real controls stay unlabeled.',
              'Field feasibility failures remain recorded; no model-outcome-based replacement.'],
}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def fetch(url, target, timeout=120):
    failures=[]
    for attempt in range(4):
        try:
            result=fetch_once(url,target,timeout)
            if failures:
                result['transient_failures']=failures
            return result
        except Exception as error:
            failures.append(f'{type(error).__name__}: {error}')
            if attempt==3:
                raise
            time.sleep(2*(attempt+1))


def fetch_once(url, target, timeout=120):
    request = Request(url, headers={'User-Agent': 'SpaceApps-native-v3-research/1.0'})
    digest = hashlib.sha256()
    temporary = target.with_suffix(target.suffix + '.part')
    with urlopen(request, timeout=timeout) as response, temporary.open('wb') as output:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            output.write(chunk)
    temporary.replace(target)
    return {'url': url, 'path': str(target), 'bytes': target.stat().st_size,
            'sha256': digest.hexdigest()}


def parse_sia(path):
    root = ET.parse(path).getroot()
    fields = [node.attrib['name'] for node in root.findall('.//{*}TABLE/{*}FIELD')]
    rows = [dict(zip(fields, [''.join(cell.itertext()).strip() for cell in row]))
            for row in root.findall('.//{*}TABLEDATA/{*}TR')]
    statuses = [node.attrib for node in root.findall('.//{*}INFO')]
    return rows, statuses


def discover(group, root):
    destination = root / 'metadata' / group['group_id']
    destination.mkdir(parents=True, exist_ok=True)
    params = {'POS': f"CIRCLE {group['center'][0]} {group['center'][1]} 0.001",
              'COLLECTION': 'spherex_dr1', 'RESPONSEFORMAT': 'VOTABLE', 'MAXREC': 512}
    url = 'https://irsa.ipac.caltech.edu/SIA?' + urlencode(params)
    started = time.monotonic()
    result = dict(group, query_url=url)
    try:
        provenance = fetch(url, destination/'sia.xml', timeout=150)
        rows, statuses = parse_sia(destination/'sia.xml')
        result.update(query_source=provenance, rows=rows, statuses=statuses)
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    result['elapsed_seconds'] = time.monotonic()-started
    write_json(destination/'discovery.json', result)
    return result


def select(group, index):
    preferred = 1 + index % 3
    choices = []
    for detector in [preferred] + [d for d in [1,2,3] if d != preferred]:
        rows = [r for r in group.get('rows', []) if r.get('energy_bandpassname') == f'SPHEREx-D{detector}'
                and '/dr1/' in r.get('access_url', '')]
        rows.sort(key=lambda r: (float(r['t_min']), r['obs_id']))
        unique = list({r['obs_id']: r for r in reversed(rows)}.values())
        unique.sort(key=lambda r: float(r['t_min']))
        for max_hours in [1.5, 48.]:
            for start in range(len(unique)):
                window = [r for r in unique[start:] if (float(r['t_min'])-float(unique[start]['t_min']))*24 <= max_hours]
                if len(window) < 3:
                    continue
                # Evenly span the window rather than select nearly simultaneous variants.
                n = min(5, len(window))
                chosen = [window[round(i*(len(window)-1)/(n-1))] for i in range(n)]
                choices.append((max_hours, detector != preferred, float(chosen[0]['t_min']), detector, chosen))
                break
    if not choices:
        return dict(group_id=group['group_id'], split=group['split'], center=group['center'], error='No supported SWIR detector with >=3 unique physical OBSIDs in a <=48-hour metadata window')
    max_hours, _, _, detector, rows = min(choices, key=lambda x: x[:3])
    return dict(group_id=group['group_id'], split=group['split'], center=group['center'], detector=detector,
                cadence_selection_window_hours=max_hours, exposures=rows,
                span_hours=(float(rows[-1]['t_max'])-float(rows[0]['t_min']))*24)


def download_group(group, root):
    if group.get('error'):
        return group
    directory = root / ('quarantine_final' if group['split']=='final' else 'development') / group['group_id']
    directory.mkdir(parents=True, exist_ok=True)
    downloads = []
    failures=[]
    for row in group['exposures']:
        url = row['access_url'] + '?' + urlencode({'center': ','.join(map(str, group['center'])), 'size': PLAN['cutout_size_deg']})
        target = directory / Path(row['access_url']).name
        try:
            if target.exists():
                info = {'url': url, 'path': str(target), 'bytes': target.stat().st_size,
                        'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
            else:
                info = fetch(url, target, timeout=240)
            info.update(obs_id=row['obs_id'], detector=group['detector'], t_min_mjd=float(row['t_min']), t_max_mjd=float(row['t_max']))
            downloads.append(info)
            write_json(directory/'downloads.json', downloads)
        except Exception as error:
            failures.append({'url': url, 'path': str(target), 'error': f'{type(error).__name__}: {error}', 'obs_id': row['obs_id']})
            write_json(directory/'download-failures.json', failures)
            write_json(directory/'downloads.json', downloads)
    result = dict(group, directory=str(directory), downloads=downloads, download_failures=failures)
    result['downloaded_exposures'] = sum('sha256' in row for row in downloads)
    result['pixels_opened'] = False
    write_json(directory/'group.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['declare','discover','select','download','download-supplements'])
    parser.add_argument('--root', type=Path, default=Path('/tmp/spaceapps-v3-native-data'))
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--groups', nargs='*')
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error('network concurrency must be <=4')
    args.root.mkdir(parents=True, exist_ok=True)
    plan_path=args.root/'partition-plan.json'
    if args.command == 'declare':
        if plan_path.exists():
            raise SystemExit('Refusing to overwrite predeclared plan')
        write_json(plan_path, PLAN)
        print(hashlib.sha256(plan_path.read_bytes()).hexdigest(), flush=True)
        return
    plan=json.loads(plan_path.read_text())
    groups=[g for g in plan['groups'] if not args.groups or g['group_id'] in args.groups]
    if args.command == 'discover':
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            for future in as_completed([executor.submit(discover,g,args.root) for g in groups]):
                result=future.result()
                print(result['group_id'],len(result.get('rows',[])),result.get('error','ok'), flush=True)
    elif args.command == 'select':
        selected=[]
        seen={}
        for index,g in enumerate(plan['groups']):
            path=args.root/'metadata'/g['group_id']/'discovery.json'
            if not path.exists():
                continue
            result=select(json.loads(path.read_text()),index)
            for row in result.get('exposures',[]):
                if row['obs_id'] in seen:
                    raise ValueError(f"Cross-group physical OBSID leakage: {row['obs_id']}")
                seen[row['obs_id']]=g['group_id']
            selected.append(result)
            print(g['group_id'],result.get('detector'),len(result.get('exposures',[])),result.get('span_hours'),result.get('error','ok'),flush=True)
        write_json(args.root/'selected-groups.json',selected)
    else:
        if args.command=='download-supplements':
            selected=json.loads((args.root/'cadence-supplement-plan.json').read_text())['groups']
        else:
            selected=json.loads((args.root/'selected-groups.json').read_text())
        selected=[g for g in selected if not args.groups or g['group_id'] in args.groups]
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            for future in as_completed([executor.submit(download_group,g,args.root) for g in selected]):
                result=future.result()
                print(result['group_id'],result.get('downloaded_exposures',0),result.get('error','ok'),flush=True)


if __name__=='__main__':
    main()
