"""Root-authorized paired native V4 evaluation; no fitting or network access."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import math
from pathlib import Path
from types import SimpleNamespace

from freeze import validate_freeze, exact_module, digest


def run_parent(task):
    freeze_path, anchor, directory, parent_id = task
    frozen = validate_freeze(freeze_path, anchor)
    scene = exact_module('v4_checked_scene', frozen['sources']['scene'], Path(freeze_path).parent)
    modules = scene.science(frozen)
    import numpy as np
    parent = next(row for row in frozen['native']['parents'] if row['parent_id'] == parent_id)
    parent['_scope'] = frozen['scope']
    center = parent['center_deg']; region = frozen['native']['region']
    observations = parent['_observations']
    request = dict(schema_version=1, analysis_id='v4-frozen-' + parent_id,
                   source=dict(kind='fits', observations=observations,
                               region=dict(right_ascension_deg=center[0], declination_deg=center[1],
                                           width_arcmin=region['width_arcmin'], height_arcmin=region['height_arcmin'])),
                   options=dict(pixel_scale_arcsec=region['pixel_scale_arcsec'], mask_policy='motion'))
    stack = modules.prepare(request)
    expected_shape = [math.ceil(region[key] * 60 / region['pixel_scale_arcsec'])
                      for key in ('height_arcmin', 'width_arcmin')]
    if list(stack.images.shape[1:]) != expected_shape or len(stack.frames) != len(observations):
        raise ValueError('native preparation changed frozen shape or independent epoch count')
    lookup = {row['frame_id']: row for row in observations}
    ordered = [lookup[frame['frame_id']] for frame in stack.frames]
    natives = [modules.native.read_native(row['path'], stack.grid, expected_shape) for row in ordered]
    controls, control = scene.measure(stack.images, stack.times, stack, modules)
    control.update(matches=[-2] * len(controls), labels='UNKNOWN; no precision or negative labels')
    output = Path(directory) / (parent_id + '.json.gz')
    metadata = dict(schema_version=4, kind='native', partition=frozen['scope'], scope=frozen['scope'],
                    freeze_sha256=anchor, parent_id=parent_id, seed=parent['seed'],
                    models={role: model['_metadata'] for role, model in frozen['models'].items()},
                    versions=frozen['versions'], detector_settings=frozen['detector_settings'],
                    source_sha256={name: ref['sha256'] for name, ref in frozen['sources'].items()},
                    feature_names=list(modules.features.FEATURE_NAMES),
                    feature_contract_sha256=modules.features.FEATURE_CONTRACT_SHA256,
                    input_sources=ordered, frames=stack.frames, center_deg=center,
                    times_hours=stack.times.tolist(), registered_shape=list(stack.images.shape),
                    preparation_options=region, downloads_manifest=parent['downloads_manifest'],
                    control=control, control_diagnostics={'peak_cap_reached': control['peak_cap_reached']},
                    comparison='C13 and selected V4 scores on exactly the same measured candidate IDs',
                    limitations=['native ePSF source added after registration', 'fixed flux across passbands',
                                 'no added photon noise or variance update', 'derivatives share one parent',
                                 'spatial recovery is not confirmed motion', 'ranking scores are uncalibrated'])
    writer = modules.latent.AtomicCache(output, metadata)
    injection = SimpleNamespace(project_response=modules.native.project_response,
                                add_injection=modules.native.add_projected_injection)
    try:
        for identity, images, positions, error in modules.latent._native_latents(parent, stack, natives, injection, expected_shape, None):
            if error:
                raise ValueError('frozen injection failed: ' + json.dumps(error))
            tracks, measured = scene.measure(images, stack.times, stack, modules)
            preexisting = any(modules.cache.matches_truth(controls, positions))
            truth = modules.latent._record(tracks, [positions], True)
            record = {**identity, **truth, **measured, 'truth_kind': 'moving_injection',
                      'attribution_eligible': not preexisting, 'preexisting_control_match': preexisting,
                      'geometric_capability': modules.geometry.geometry_capability(positions, stack.times, identity['center_usable_flags'])}
            writer.append(record)
        if writer.summary['planned'] != 270:
            raise ValueError('missing or extra planned native injection')
        # Any source, graph, provenance or native byte mutation invalidates output.
        validate_freeze(freeze_path, anchor)
        writer.finish()
    except BaseException:
        writer.abort()
        raise
    return dict(parent_id=parent_id, path=str(output.resolve()), sha256=digest(output), summary=writer.summary)


def run(freeze_path, anchor, output):
    frozen = validate_freeze(freeze_path, anchor)
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('frozen run destination must be new and empty')
    tasks = [(str(Path(freeze_path).resolve()), anchor, str(output), parent['parent_id']) for parent in frozen['native']['parents']]
    results = []
    with ProcessPoolExecutor(max_workers=frozen['runtime']['workers']) as pool:
        for future in as_completed([pool.submit(run_parent, task) for task in tasks]):
            record = future.result(); results.append(record)
            print(json.dumps(dict(parent_id=record['parent_id'], completed=True, sha256=record['sha256'])), flush=True)
    manifest = dict(schema_version=4, kind='native', scope=frozen['scope'], freeze_sha256=anchor,
                    evaluation_complete=len(results) == len(tasks), versions=frozen['versions'],
                    outputs=sorted(results, key=lambda row: row['parent_id']))
    path = output / 'run-native-manifest.json'
    path.write_text(json.dumps(manifest, indent=2) + '\n')
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--freeze-sha256', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(run(args.freeze, args.freeze_sha256, args.output))
