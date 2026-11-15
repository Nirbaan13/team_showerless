"""Frozen paired V4 synthetic evaluation; no training or implicit seed discovery."""
from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from freeze import validate_freeze, exact_module, digest

FROZEN = MODULES = BANK = None


def initialize(path, anchor):
    global FROZEN, MODULES, BANK
    FROZEN = validate_freeze(path, anchor)
    scene = exact_module('v4_checked_scene', FROZEN['sources']['scene'], Path(path).parent)
    MODULES = scene.science(FROZEN)
    MODULES.scene = scene
    BANK = MODULES.simulator.load_bank(FROZEN['synthetic']['calibration_bank']['path'])


def generate(seed):
    import numpy as np
    if seed not in FROZEN['synthetic']['seeds']:
        raise ValueError('undeclared frozen synthetic identity')
    images, times, truth, mode, metadata = MODULES.simulator.simulate(
        seed, BANK, extended=seed % 3 == 0, varying_psf=True)
    # These calls receive only observable pixels/times, never truth positions.
    stack = SimpleNamespace(outlier=None, bloom=None)
    tracks, measured = MODULES.scene.measure(images, times, stack, MODULES)
    record = MODULES.latent._record(tracks, truth, False)
    capabilities = []
    h, w = images.shape[1:]
    for path in truth:
        covered = []
        for image, (x, y) in zip(images, np.rint(path).astype(int)):
            covered.append(bool(0 <= x < w and 0 <= y < h and np.isfinite(image[y, x])))
        capabilities.append(MODULES.geometry.geometry_capability(path, times, covered))
    latent = hashlib.sha256()
    for array in (images, times, *truth):
        latent.update(np.asarray(array, dtype='<f8').tobytes())
    return dict(seed=seed, partition=FROZEN['scope'], mode=mode, metadata=metadata,
                expected_xy=[path.tolist() for path in truth], times_hours=times.tolist(),
                registered_shape=list(images.shape), latent_sha256=latent.hexdigest(),
                geometric_capabilities=capabilities, attribution_eligible=True,
                preexisting_control_match=False, **record, **measured)


def bounded_results(pool, seeds, maximum_pending):
    seeds = iter(seeds); pending = deque()
    for _ in range(maximum_pending):
        try: pending.append(pool.submit(generate, next(seeds)))
        except StopIteration: break
    while pending:
        yield pending.popleft().result()
        try: pending.append(pool.submit(generate, next(seeds)))
        except StopIteration: pass


def run(path, anchor, directory):
    frozen = validate_freeze(path, anchor)
    output = Path(directory).resolve(); output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('frozen synthetic destination must be new and empty')
    latent = exact_module('v3_frozen_atomic_writer', frozen['sources']['native_latents'], Path(path).parent)
    metadata = dict(schema_version=4, kind='synthetic', scope=frozen['scope'], partition=frozen['scope'],
                    freeze_sha256=anchor, versions=frozen['versions'],
                    models={role: model['_metadata'] for role, model in frozen['models'].items()},
                    source_sha256={name: ref['sha256'] for name, ref in frozen['sources'].items()},
                    detector_settings=frozen['detector_settings'],
                    feature_names=frozen['models']['candidate']['_metadata']['feature_names'],
                    feature_contract_sha256=frozen['models']['candidate']['_metadata']['feature_contract_sha256'],
                    generator=dict(extended_every_nth_field=3, varying_psf=True),
                    calibration_bank=frozen['synthetic']['calibration_bank'],
                    parent_field_seeds=frozen['synthetic']['seeds'],
                    comparison='C13 and selected V4 scores on exactly the same measured candidate IDs',
                    limitations=['controlled simulator, not survey precision', 'ranking scores are uncalibrated',
                                 'missing mission quality masks represented honestly'])
    destination = output / 'synthetic.json.gz'
    writer = latent.AtomicCache(destination, metadata)
    try:
        with ProcessPoolExecutor(max_workers=frozen['runtime']['workers'], initializer=initialize,
                                 initargs=(str(Path(path).resolve()), anchor)) as pool:
            for index, field in enumerate(bounded_results(pool, frozen['synthetic']['seeds'], 2 * frozen['runtime']['workers']), 1):
                writer.append(field)
                if index % 100 == 0:
                    print(json.dumps(dict(completed=index, planned=len(frozen['synthetic']['seeds']))), flush=True)
        if writer.summary['planned'] != len(frozen['synthetic']['seeds']):
            raise ValueError('missing frozen synthetic field')
        validate_freeze(path, anchor)
        writer.finish()
    except BaseException:
        writer.abort()
        raise
    manifest = dict(schema_version=4, kind='synthetic', scope=frozen['scope'], freeze_sha256=anchor,
                    evaluation_complete=True, versions=frozen['versions'],
                    outputs=[dict(path=str(destination), sha256=digest(destination), summary=writer.summary)])
    result = output / 'run-synthetic-manifest.json'
    result.write_text(json.dumps(manifest, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--freeze-sha256', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(run(args.freeze, args.freeze_sha256, args.output))
