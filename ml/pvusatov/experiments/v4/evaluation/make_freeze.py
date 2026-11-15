"""Build a reviewable freeze; printing its SHA never authorizes a FINAL run.

The root coordinator must review the selected DEV evidence and independently
authorize use of the resulting external anchor before opening FINAL pixels.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]


def ref(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def build(scope, candidate_dir, selection_record, output, *, workers=4,
          dev_parent='v4-train04', dev_native_seed=3800501,
          dev_synthetic_start=3800600, dev_synthetic_fields=12, source_snapshot=None):
    source = Path(__file__).with_name('freeze.py')
    validator = ModuleType('v4_freeze_builder_schema')
    exec(compile(source.read_bytes(), str(source), 'exec'), validator.__dict__)
    data = ROOT / 'experiments/v4/data'
    acquisition = json.loads((data / 'partition-plan.json').read_text())
    audit = json.loads((data / 'complete-audit.json').read_text())
    development = json.loads((data / 'development-handoff.json').read_text())
    if scope not in ('development', 'final'):
        raise ValueError('scope must be development or final')
    selected_ids = ['v4-final%02d' % i for i in range(1, 13)] if scope == 'final' else [dev_parent]
    groups = {row['parent_id']: row for row in acquisition['groups']}
    parents = {row['parent_id']: row for row in audit['parents']}
    native = [dict(parent_id=identity, seed=3950001 + index if scope == 'final' else dev_native_seed,
                   center_deg=groups[identity]['center'], downloads_manifest=parents[identity]['downloads_manifest'])
              for index, identity in enumerate(selected_ids)]
    if scope == 'development' and any(groups[identity]['split'] == 'final' for identity in selected_ids):
        raise ValueError('development freeze cannot select a quarantined parent')
    exclusions = list(acquisition['excluded_physical_obsids'])
    if scope == 'final':
        exclusions += [identity for group in development['groups'] for identity in group['physical_obsids']]
    baseline = ROOT / 'releases/v3/model'; candidate_dir = Path(candidate_dir).resolve()
    source_root = ROOT
    if source_snapshot is not None:
        source_root = Path(source_snapshot).resolve()
        if '/ml/pvusatov/' not in source_root.as_posix() + '/':
            raise ValueError('source snapshot must remain within the ML namespace')
        if source_root.exists(): raise ValueError('source snapshot must be a new directory')
        source_root.mkdir(parents=True)
        for relative in validator.SOURCES.values():
            target = source_root / relative; target.parent.mkdir(parents=True, exist_ok=True)
            blob = (ROOT / relative).read_bytes(); target.write_bytes(blob)
            if ref(target)['sha256'] != ref(ROOT / relative)['sha256']:
                raise ValueError('source changed during snapshot')
    value = dict(schema_version=4, status='frozen', scope=scope, authorized_final=scope == 'final',
                 source_root=str(source_root), runtime=dict(workers=workers, math_threads=1, max_frames=32, max_grid=512),
                 proposal_policy='c13-sigma08-v1', detector_settings=validator.PROFILE,
                 models={role:dict(artifact=ref(directory / 'ranker.onnx'), metadata=ref(directory / 'metadata.json'))
                         for role, directory in (('baseline', baseline), ('candidate', candidate_dir))},
                 sources={name:ref(source_root / path) for name, path in validator.SOURCES.items()},
                 provenance=dict(protocol=ref(ROOT / 'experiments/v4/protocol.json'),
                                 acquisition_plan=ref(data / 'partition-plan.json'),
                                 data_audit=ref(data / 'complete-audit.json'),
                                 development_handoff=ref(data / 'development-handoff.json'),
                                 selection_record=ref(selection_record)),
                 native=dict(parents=native, excluded_physical_obsids=sorted(set(exclusions)),
                             region=dict(width_arcmin=6., height_arcmin=6., pixel_scale_arcsec=6.15, mask_policy='motion')),
                 synthetic=dict(seeds=list(range(3900000, 3903000)) if scope == 'final'
                                else list(range(dev_synthetic_start, dev_synthetic_start + dev_synthetic_fields)),
                                calibration_bank=ref(ROOT / 'backend/inference/training/calibration/instrument-epsf-bank.npz')),
                 versions=validator.versions())
    validator.validate_plan(value)
    destination = Path(output).resolve()
    if destination.exists(): raise ValueError('refusing to overwrite an evaluation freeze')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    # Opaque preflight does not run a model, simulator or pixel reader.
    validator.validate_freeze(destination, ref(destination)['sha256'])
    return ref(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', required=True, choices=('development', 'final'))
    parser.add_argument('--candidate-dir', required=True)
    parser.add_argument('--selection-record', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--dev-parent', default='v4-train04')
    parser.add_argument('--dev-native-seed', type=int, default=3800501)
    parser.add_argument('--dev-synthetic-start', type=int, default=3800600)
    parser.add_argument('--dev-synthetic-fields', type=int, default=12)
    parser.add_argument('--source-snapshot')
    print(json.dumps(build(**vars(parser.parse_args())), indent=2))
