"""Checked V4 evaluation entry point. Invoke this file directly with Python.

Only this small standard-library bootstrap runs before the externally anchored
freeze is read. Neither a timestamp-cached validator nor runner is imported.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys


def bootstrap(path, anchor):
    path = Path(path).resolve(); raw = path.read_bytes()
    if not re.fullmatch('[0-9a-f]{64}', str(anchor)) or hashlib.sha256(raw).hexdigest() != anchor:
        raise ValueError('external freeze anchor differs before validator execution')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('duplicate frozen bootstrap key')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs)
    ref = value['sources']['freeze']; source_path = Path(ref['path'])
    source_path = source_path.resolve() if source_path.is_absolute() else (path.parent / source_path).resolve()
    source = source_path.read_bytes()
    if len(source) > 2 * 1024 * 1024 or hashlib.sha256(source).hexdigest() != ref['sha256']:
        raise ValueError('validator source differs from externally anchored bytes')
    name = 'v4_checked_preflight_' + anchor[:12]
    spec = importlib.util.spec_from_file_location(name, source_path)
    validator = importlib.util.module_from_spec(spec); sys.modules[name] = validator
    exec(compile(source, str(source_path), 'exec'), validator.__dict__)
    validator.__source_sha256__ = ref['sha256']
    frozen = validator.validate_freeze(path, anchor)
    return frozen, validator


def run(kind, path, anchor, output=None, native_manifest=None, synthetic_manifest=None, both_runs_finished=False):
    frozen, validator = bootstrap(path, anchor)
    if frozen['sources']['execute']['sha256'] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError('checked executor differs from the authorized source closure')
    # Checked runner imports resolve to this exact validator in parent and forked
    # children; no normal import can substitute a stale timestamp-pyc validator.
    sys.modules['freeze'] = validator
    key = {'native':'run_native', 'synthetic':'run_synthetic', 'report':'report'}[kind]
    runner = validator.exact_module('v4_checked_' + kind, frozen['sources'][key], Path(path).parent)
    if kind == 'report':
        result = runner.summarize(path, anchor, native_manifest, synthetic_manifest,
                                  both_runs_finished=both_runs_finished)
        destination = Path(output)
        if destination.exists(): raise ValueError('refusing to overwrite frozen report')
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
        return destination
    return runner.run(path, anchor, output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=('native','synthetic','report'), required=True)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--freeze-sha256', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--native-manifest')
    parser.add_argument('--synthetic-manifest')
    parser.add_argument('--both-runs-finished', action='store_true')
    args = parser.parse_args()
    print(run(args.kind, args.freeze, args.freeze_sha256, args.output, args.native_manifest,
              args.synthetic_manifest, args.both_runs_finished))
