"""Root-only blinded preparation audit; never detect or score real pixels."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ANCHOR = '1896c55288579151576f8e1c7026f3b57959fa8e6c857fed96817a7807c11e57'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    original = ROOT/'verification/v4-final/freeze.json'
    entry = ROOT/'verification/v4-final/source/experiments/v4/evaluation/execute.py'
    spec = importlib.util.spec_from_file_location('blinded_coverage_audit_bootstrap', entry)
    bootstrap = importlib.util.module_from_spec(spec)
    exec(compile(entry.read_bytes(), str(entry), 'exec'), bootstrap.__dict__)
    frozen, validator = bootstrap.bootstrap(original, ANCHOR); sys.modules['freeze'] = validator
    scene = validator.exact_module('blinded_coverage_audit_scene', frozen['sources']['scene'], original.parent)
    modules = scene.science(frozen)  # Graph/feature verification before any pixel reader.
    source = ROOT/'releases/v4/runtime/ml_inference/prepare.py'
    amended = validator.exact_module('ml_inference.prepare', dict(path=str(source), sha256=digest(source)), original.parent)
    binding = validator.exact_module('blinded_coverage_audit_binding', frozen['sources']['data_binding'], original.parent)
    import numpy as np
    results = []
    for parent in frozen['native']['parents']:
        ra, dec = parent['center_deg']; region = frozen['native']['region']
        request = dict(schema_version=1, analysis_id='blinded-coverage-' + parent['parent_id'],
                       source=dict(kind='fits', observations=parent['_observations'],
                                   region=dict(right_ascension_deg=ra, declination_deg=dec,
                                               width_arcmin=region['width_arcmin'], height_arcmin=region['height_arcmin'])),
                       options=dict(pixel_scale_arcsec=region['pixel_scale_arcsec'], mask_policy='motion'))
        stack = amended.prepare(request)
        binding.validate_prepared_frames(frozen['_native_expected'][parent['parent_id']], stack.frames, stack.times)
        counts = np.isfinite(stack.images).sum(axis=(1, 2)).tolist()
        row = dict(parent_id=parent['parent_id'], physical_epochs=len(stack.frames),
                   finite_pixel_counts=counts, usable_epoch_count=sum(count > 0 for count in counts),
                   frame_ids=[frame['frame_id'] for frame in stack.frames],
                   physical_ids=[frame['physical_observation_id'] for frame in stack.frames],
                   raw_sha256=[frame['sha256'] for frame in stack.frames])
        try:
            old = modules.prepare(request)
        except Exception as error:
            if getattr(error, 'code', None) != 'no_coverage': raise
            row.update(original_supported=False, original_error_code='no_coverage')
        else:
            equal = all(getattr(old, key).tobytes() == getattr(stack, key).tobytes()
                        for key in ('images', 'times', 'outlier', 'bloom'))
            equal = equal and old.frames == stack.frames and old.warnings == stack.warnings and old.provenance == stack.provenance
            if not equal: raise ValueError('covered preparation changed: ' + parent['parent_id'])
            row.update(original_supported=True, original_preparation_bitwise_equal=True)
            del old
        results.append(row)
        print(json.dumps(dict(parent_id=parent['parent_id'], finite_pixel_counts=counts,
                              original_supported=row['original_supported'])), flush=True)
        del stack
    result = dict(schema_version=4, scope='root-only coverage diagnostics; no detector calls or pixel-dependent model scores',
                  original_freeze_sha256=ANCHOR, prepare_source_sha256=digest(source),
                  audit_source_sha256=digest(Path(__file__)), results=results)
    output = Path(__file__).with_name('prepare-only-audit.json')
    if output.exists(): raise ValueError('audit output must be new')
    output.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    run()
