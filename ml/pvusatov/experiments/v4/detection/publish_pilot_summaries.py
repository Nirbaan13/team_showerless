"""Publish compact DEVELOPMENT evidence; full immutable raw reports remain hashed.

Reads JSON caches only, never native FITS, final fields, models or pixel readers.
Rechecks every typed native truth match/span from actual fitted epochs/positions.
"""
from pathlib import Path
import gzip
import hashlib
import json
from types import SimpleNamespace
import numpy as np
from ml.pvusatov.experiments.v4.detection.pilot_joint_tracking import CACHE_SHAS, atomic, digest, evaluate, summary
from ml.pvusatov.experiments.v4.detection.pilot_joint_competitor import summary as competitor_summary

HERE = Path(__file__).resolve().parent
SCRATCH = Path('/tmp/spaceapps-v4-detection')
REPORTS = {
    'joint-pilot-full-v1': 'joint-pilot-protocol-v1.json',
    'joint-native-v2': 'joint-native-protocol-v2.json',
    'joint-competitor-full-v1': 'joint-competitor-protocol-v1.json',
    'joint-competitor-native-v2': 'joint-competitor-native-protocol-v2.json',
}
METRICS = ('candidate_rows','detected','top1','top3','resolved_detected','resolved_top1','resolved_top3',
           'attribution_eligible','unknown_control_rows','candidate_cap_reached','hypothesis_search_complete',
           'proposal_publication_complete','errors','top100_detected')


def check_geometry(row, truth):
    """No mutation; raw fitted coordinates are checked against evaluation truth."""
    count = 0
    for name, method in row['methods'].items():
        tracks = [SimpleNamespace(epochs=tuple(t['epochs']), positions_xy=t['positions_xy']) for t in method['typed_hypotheses']]
        expected = evaluate(tracks, [np.asarray(truth)], True)
        for key in ('matches','candidate_rows','detected','top1','top3','resolved_detected','resolved_top1','resolved_top3'):
            if method[key] != expected[key]:
                raise ValueError('native typed match/count inconsistent: ' + name + ':' + key)
        for key in ('matched_true_spans_px','fitted_spans_px'):
            if len(method[key]) != len(expected[key]):
                raise ValueError('native span array length differs')
            for a, b in zip(method[key], expected[key]):
                if a is None or b is None:
                    if a is not b:
                        raise ValueError('native span missingness differs')
                elif not np.isclose(a, b, rtol=0, atol=1e-12):
                    raise ValueError('native actual-epoch span differs')
        count += len(tracks)
    return count


def native_metadata():
    fields = {}; parents = {}
    for parent, sha in CACHE_SHAS.items():
        path = Path('/tmp/spaceapps-v4-native-cache/main-v2') / (parent + '-both.json.gz')
        if digest(path) != sha:
            raise ValueError('safe development cache bytes changed')
        with gzip.open(path, 'rt') as stream:
            cache = json.load(stream)
        parents[parent] = dict(source_cache=str(path), sha256=sha,
            baseline_unknown_control_rows=len(cache['control']['features']),
            baseline_control_peak_cap=cache['control']['peak_cap_reached'],
            physical_times_hours=cache['times_hours'], input_sha256=[r['sha256'] for r in cache['input_sources']])
        for f in cache['fields']:
            if f.get('truth_kind') == 'moving_injection' and f['direction_id'] == 0 and f['brightness'] in (3,6,12):
                fields[parent, f['trajectory_id'], f['brightness']] = f['expected_xy']
    if len(fields) != 54:
        raise ValueError('exact54 fixed native derivatives required')
    return fields, parents


def compact_fields(fields):
    result = []
    for f in fields:
        row = {k:v for k,v in f.items() if k in ('kind','parent_id','seed','trajectory_id','brightness','speed_px_hour',
            'truth_count','mode','error','wall_seconds','cpu_seconds','rss_mib','latent_sha256')}
        if row.get('error'):
            row['error'] = row['error'].splitlines()[0]
        else:
            row['methods'] = {'baseline':{k:v for k,v in f['baseline'].items() if k in METRICS}}
            row['methods'].update({name:{k:v for k,v in m.items() if k in METRICS} for name,m in f['methods'].items()})
        result.append(row)
    return result


def null_statistics(fields):
    output = {}
    for mode in ('noise_only','artifacts_only'):
        for statistic in ('nuisance_sum','robust_positive','single_epoch_competitor'):
            values = []
            for f in fields:
                if f.get('mode') != mode or f.get('error'):
                    continue
                maxima = [g['maximum_search_statistic'] for s in f['diagnostics']['searches'] if s['statistic'] == statistic
                    for g in s['groups'] if g.get('maximum_search_statistic') is not None]
                if maxima:
                    values.append(max(maxima))
            if values:
                output[mode + ':' + statistic] = dict(independent_fields=len(values),
                    maximum_statistic_quantiles=dict(zip(('p50','p90','p95','max'),np.quantile(values,[.5,.9,.95,1.]).tolist())),
                    interpretation='empirical look-elsewhere diagnostic, not a calibrated tail probability')
    return output


def main():
    expected, parents = native_metadata(); published = []
    for stem, protocol_name in REPORTS.items():
        path = SCRATCH / (stem + '.json'); raw = json.loads(path.read_text())
        protocol = SCRATCH / protocol_name
        if digest(protocol) != raw['protocol_sha256']:
            raise ValueError('raw report protocol binding differs')
        summary_fn = competitor_summary if 'competitor' in stem else summary
        if summary_fn(raw['fields']) != raw['summary']:
            raise ValueError('raw aggregate does not match field rows')
        if any(digest(p) != sha for p,sha in raw['source_sha256'].items()):
            raise ValueError('published raw source closure changed')
        checked = 0; control_rows = {}
        for f in raw['fields']:
            if f['kind'] == 'native' and not f['error']:
                key = (f['parent_id'],f['trajectory_id'],f['brightness'])
                checked += check_geometry(f, expected[key])
                for name, m in f['methods'].items():
                    control_key = f['parent_id'] + ':' + name
                    prior = control_rows.setdefault(control_key, m['unknown_control_rows'])
                    if prior != m['unknown_control_rows']:
                        raise ValueError('same parent unknown control burden changed between derivatives')
        native_parent = {}
        for parent in CACHE_SHAS:
            fs = [f for f in raw['fields'] if f['parent_id'] == parent and not f['error']]
            if fs:
                native_parent[parent] = summary_fn(fs)['native']['methods']
        compact = dict(designation='DEVELOPMENT detector ablation, not a selected/published model',
            raw_report=dict(path=str(path),sha256=digest(path),bytes=path.stat().st_size),
            protocol=dict(path=str(protocol),sha256=digest(protocol)),
            source_sha256=raw['source_sha256'], summary=raw['summary'], fields=compact_fields(raw['fields']),
            null_maxima=null_statistics(raw['fields']), native_per_parent=native_parent,
            native_unknown_control_rows=control_rows, native_geometry_candidate_checks=checked,
            runtime=dict(elapsed_wall_seconds=raw['elapsed_seconds'],worker_peak_rss_mib=max(f['rss_mib'] for f in raw['fields']),
                field_cpu_seconds_sum=sum(f['cpu_seconds'] for f in raw['fields']),
                typed_search_cpu_seconds_sum=sum(f.get('diagnostics',{}).get('cpu_seconds',0.) for f in raw['fields'])),
            limitations=raw['limitations'])
        output = HERE / 'results' / (stem + '-compact.json')
        if output.exists():
            if json.loads(output.read_text()) != compact:
                raise ValueError('existing immutable compact differs')
        else:
            atomic(output, compact)
        published.append(dict(path=str(output),sha256=digest(output),bytes=output.stat().st_size))
        del raw
    gate_path = SCRATCH / 'information-gate-full-v1.json'
    gate = json.loads(gate_path.read_text())
    output = HERE / 'results/information-gate-full-v1-compact.json'
    gate_compact = dict(designation=gate['designation'],source_sha256=gate['source_sha256'],summary=gate['summary'],
        raw_report=dict(path=str(gate_path),sha256=digest(gate_path),bytes=gate_path.stat().st_size),
        protocol=dict(path=str(SCRATCH / 'information-gate-protocol-v1.json'),sha256=digest(SCRATCH / 'information-gate-protocol-v1.json')),
        elapsed_seconds=gate['elapsed_seconds'],native_controls=gate['native_controls'],model_sha256=gate['model_sha256'])
    if output.exists():
        raise ValueError('immutable gate compact already exists')
    atomic(output,gate_compact);published.append(dict(path=str(output),sha256=digest(output),bytes=output.stat().st_size))
    index = dict(designation='Immutable DEVELOPMENT detector evidence index; no final selection/promotion',
        summaries=published,native_sources=parents,
        original_attempt='v1native54representation-guard failures preserved; only synthetic outcomes fromv1 are usable',
        corrected_attempt='v2native-only exactFloat32 observable replay, no physical/truth tolerance change',
        independent_units='synthetic200fields; native54derivatives/twoTRAINparents; informationgate120derivatives/fourOLDTRAINparents',
        conclusion='No detector variant satisfies useful native recovery/review-budget no-regression; no promotion',
        publisher_source_sha256=digest(Path(__file__)))
    output = HERE / 'results/detector-pilot-evidence-index.json'
    if output.exists():
        raise ValueError('immutable evidence index already exists')
    atomic(output,index)
    print(json.dumps(dict(index=str(output),sha256=digest(output),summaries=published)))


if __name__ == '__main__':
    main()
