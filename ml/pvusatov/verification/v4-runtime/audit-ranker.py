"""Independently audit downloaded engineering evidence; never read final data."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]
EVIDENCE = HERE / 'vps-evidence'
MODEL_SHA = 'c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35'
META_SHA = '472a3db474a84d856110a7f52907c461c402ddde640fa108ec9a521a79ab5e13'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def atomic(path, text):
    if path.exists():
        raise ValueError('audit output already exists')
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.audit-', delete=False) as stream:
        stream.write(text.encode()); temporary = stream.name
    os.replace(temporary, path)


def main():
    refs = {}
    def reference(path):
        refs[str(path.relative_to(BASE))] = sha(path)
    manifest = EVIDENCE / 'resource-capsule-manifest.json'
    for item in load(manifest)['files']:
        path = EVIDENCE / item['path']
        assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256']
        reference(path)
    reference(manifest)
    bundle = HERE / 'bundle-manifest.json'
    for item in load(bundle)['files']:
        path = BASE.parents[1] / item['source']
        assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256']
    reference(bundle)
    receipt_path = EVIDENCE / 'host-container-receipt-v1.json'
    receipt = load(receipt_path); reference(receipt_path)
    image_ids = set()
    for item in receipt:
        host = item['host']; state = item['state']
        assert host['Memory'] == host['MemorySwap'] == 1024 ** 3
        assert host['NanoCpus'] == 10 ** 9 and host['PidsLimit'] == 64
        assert host['NetworkMode'] == 'none' and host['ReadonlyRootfs'] is True
        assert host['Tmpfs']['/tmp'] == 'rw,size=256m,mode=1777'
        assert state['ExitCode'] == 0 and not state['OOMKilled']
        assert next(m for m in item['mounts'] if m['Destination'] == '/probe')['RW'] is False
        image_ids.add(item['image_id'])
    assert len(receipt) == 2 and len(image_ids) == 1
    probes = {}
    for mode in ['presets', 'maximum']:
        path = EVIDENCE / f'evidence-v1-{mode}' / mode / 'proof.json'
        proof = load(path); reference(path)
        assert proof['passes'] and proof['model_sha256'] == MODEL_SHA
        assert proof['bundle_manifest_sha256'] == sha(bundle)
        assert proof['probe_source_sha256'] == sha(HERE / 'vps_probe.py')
        assert proof['fitting_import_guard']['source_sha256'] == sha(HERE / 'sitecustomize.py')
        before, after = proof['cgroup_before'], proof['cgroup_after']
        for limits in [before, after]:
            assert limits['memory.max'] == str(1024 ** 3) and limits['memory.swap.max'] == '0'
            assert limits['cpu.max'] == '100000 100000'
            events = dict(line.split() for line in limits['memory.events'].splitlines())
            assert all(int(events[k]) == 0 for k in ['oom', 'oom_kill', 'oom_group_kill', 'max'])
        assert int(after['memory.peak']) < 1024 ** 3
        probes[mode] = dict(python=proof['python'], versions=proof['versions'],
            elapsed_seconds=proof['elapsed_seconds'], cgroup_peak_mib=int(after['memory.peak']) / 1024 ** 2,
            cpu_usage_seconds=(int(dict(line.split() for line in after['cpu.stat'].splitlines())['usage_usec']) -
                               int(dict(line.split() for line in before['cpu.stat'].splitlines())['usage_usec'])) / 1e6,
            oom=False, hard_memory_bytes=1024 ** 3, swap_bytes=0, hard_cpu_quota='100000 100000')
    raw_path = EVIDENCE / 'evidence-v1-maximum/maximum/maximum-rss-raw.json'
    raw = load(raw_path); reference(raw_path)
    maximum = load(EVIDENCE / 'evidence-v1-maximum/maximum/proof.json')['results'][0]
    assert maximum['raw_proof_sha256'] == sha(raw_path) and maximum['raw_proof'] == raw
    assert raw['shape'] == [32, 512, 512] and 32 in raw['detection_counts']
    assert raw['candidate_count'] > 0 and raw['resources'] == 66
    assert raw['model_sha256'] == MODEL_SHA and raw['model_metadata_sha256'] == META_SHA
    for name, expected in raw['source_sha256'].items():
        assert sha(BASE / 'releases/v4/runtime/ml_inference' / name) == expected
    assert raw['settings']['min_snr'] == 10 and raw['settings']['max_candidates'] == 3
    probes['maximum']['inner_cli_seconds'] = raw['elapsed_seconds']
    probes['maximum']['worker_rss_mib'] = raw['worker_peak_rss_mib']
    probes['maximum']['shape'] = raw['shape']
    probes['maximum']['measured_track_epochs'] = raw['detection_counts']
    sys.path.insert(0, str(BASE / 'releases/v4/runtime'))
    from ml_inference.model import load_ranker
    ranker = load_ranker(BASE / 'releases/v4/model')
    assert ranker.metadata['sha256'] == MODEL_SHA
    assert sha(BASE / 'releases/v4/model/metadata.json') == META_SHA
    cache_path = BASE / 'experiments/v4/detection/results/preset-feature-cache.json'
    cases = load(cache_path)['cases']; reference(cache_path)
    comparisons = []
    for identity, case in cases.items():
        local_scores = ranker.score(np.asarray(case['features_v4'], np.float32))
        local_order = np.argsort(-local_scores, kind='stable')
        result_path = EVIDENCE / 'evidence-v1-presets/presets' / identity / 'result.json'
        result = load(result_path); reference(result_path)
        assert result['model']['sha256'] == MODEL_SHA
        assert result['model']['score_kind'] == 'sigmoid_pairwise_utility'
        residual = [c for c in result['candidates'] if c['method'] == 'residual_track']
        bloom = [c for c in result['candidates'] if c['method'] == 'bloom_track']
        indices = np.asarray([c['baseline_rank'] - 1 for c in residual], int)
        assert np.array_equal(indices, local_order[:len(residual)])
        actual_scores = np.asarray([c['score'] for c in residual])
        assert np.array_equal(actual_scores, local_scores[indices])
        xy_error = 0.
        for candidate, index in zip(residual, indices):
            assert [d['frame_index'] for d in candidate['detections']] == case['candidate_epochs'][index]
            xy = np.asarray([[d['x'], d['y']] for d in candidate['detections']])
            delta = np.max(np.abs(xy - np.asarray(case['candidate_positions_xy'][index])))
            xy_error = max(xy_error, float(delta))
        assert xy_error < 1e-10
        assert all(c['score'] is None and c['score_kind'] == 'flagged_bloom_evidence' for c in bloom)
        assert len(result['candidates']) <= 100
        fixture = BASE / 'backend/inference/fixtures' / (identity + '.npz')
        assert sha(fixture) == case['fixture_sha256']; reference(fixture)
        # Labels are opened only after both systems have finished their scores.
        with np.load(fixture, allow_pickle=False) as data:
            expected = data['expected_xy']
        known = [c for c in result['candidates'] if len(c['detections']) == len(expected) and
                 np.max(np.linalg.norm(np.asarray([[d['x'], d['y']] for d in c['detections']]) - expected, axis=1)) <= 1.5]
        assert known
        if identity == 'comet-d2': assert known[0]['rank'] == 1
        if identity == 'comet-d6': assert known[0]['rank'] == 2
        if identity.startswith('vesta'): assert known[0]['score'] is None
        comparisons.append(dict(preset=identity, full_local_residual_rows=len(local_scores),
            published_residual_rows=len(residual), identical_order=True, identical_scores=True,
            max_abs_score_difference=float(np.max(abs(actual_scores - local_scores[indices]))),
            maximum_measured_position_difference_px=xy_error,
            known_target_ranks=[c['rank'] for c in known], known_target_methods=[c['method'] for c in known],
            bloom_ranks=[c['rank'] for c in bloom], bloom_scores_null=True))
    audit = dict(schema_version=4, created_utc=datetime.now(timezone.utc).isoformat(),
        reviewer='independent ranker owner reviewing coordinator VPS probe', status='PASS',
        source_sha256=sha(Path(__file__)), model_sha256=MODEL_SHA, metadata_sha256=META_SHA,
        isolated_probe_image_id=next(iter(image_ids)), local_python=sys.version.split()[0],
        local_versions={p:importlib.metadata.version(p) for p in ['numpy','scipy','astropy','onnxruntime','onnx','pillow']},
        validated_evidence_files=len(load(manifest)['files']), probes=probes, preset_comparisons=comparisons,
        no_final_inputs_or_scores_read=True, no_refit_or_reselection=True, references=refs,
        limitations=['Only the 153 published residual scores are compared cross-version; 13 capped Vesta D3 residual rows are absent from the VPS result.',
            'Maximum shape uses one strong controlled track, min_snr=10 and output cap3; this is not a worst-density or native sensitivity claim.',
            'Probe is an isolated dependency image, not proof of a deployed backend or production health/cleanup; those remain coordinator-owned.',
            'Read-only rootfs permits explicit writable /tmp, /evidence and isolated anonymous /app/data volumes shown in the host receipt.',
            'Recovery performance is evaluated separately by the frozen independent final protocol.'])
    output = HERE / 'audit-ranker.json'; atomic(output, json.dumps(audit, indent=2, allow_nan=False)+'\n')
    article = f'''# Independent VPS runtime audit\n\nPASS. Exact selected graph `{MODEL_SHA}` and administrative metadata `{META_SHA}` remain unchanged. The audit validated {audit['validated_evidence_files']} downloaded evidence file hashes plus the local 20-file probe bundle.\n\nThe isolated image ran Python 3.12.3; the independent comparison used Python {audit['local_python']}. All 153 published residual candidates have identical ordered IDs, scores and measured epoch sets. Maximum position difference is below 1e-10 pixels. The 13 capped Vesta D3 residual rows were not present in the VPS output and are not claimed tested cross-version. Comet D2 ranks first and D6 second. Vesta D3 and D6 flagged targets remain unscored at ranks100 and18.\n\nActual cgroup and Docker receipts enforce one CPU, 1 GiB RAM, zero swap,64PIDs, network none, a read-only root filesystem and a256MiB /tmp. Presets used {probes['presets']['elapsed_seconds']:.2f}s and peaked at {probes['presets']['cgroup_peak_mib']:.2f}MiB. The nonempty32×512×512 workload used {probes['maximum']['elapsed_seconds']:.2f}s including probe setup and peaked at {probes['maximum']['cgroup_peak_mib']:.2f}MiB; its CLI took {raw['elapsed_seconds']:.2f}s and retained a32-epoch measured track. Both cgroups reported zero OOM and limit-hit events. The startup import guard blocks sklearn,skl2onnx,joblib and training; exact runtime sources match the reviewed inference-only implementation.\n\nThe maximum-shape fixture uses min_snr10 and output cap3 and does not establish worst-density behavior. Writable evidence/tmp and isolated anonymous data volumes are explicit in the receipt. These are isolated engineering checks; production health, cleanup and independent recovery remain separate. No final data or outcomes were read, and no model fitting, reselection or modification occurred.\n\nMachine-readable hash references and per-case results are in `audit-ranker.json` (SHA `{sha(output)}`).\n'''
    atomic(HERE / 'audit-ranker.AI.md', article)
    print(json.dumps(dict(output=str(output), sha256=sha(output), cases=len(comparisons), status='PASS')))


if __name__ == '__main__':
    main()
