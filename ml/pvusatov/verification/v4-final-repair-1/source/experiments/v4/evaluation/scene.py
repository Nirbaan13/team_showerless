"""Execute the source-checked inference closure only after opaque preflight.

Both scores use the same measured proposals, latents and 30-feature extraction.
Training libraries and expected coordinates never enter the feature extractor.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace


def source_module(name, ref):
    path = Path(ref['path']).resolve()
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != ref['sha256']:
        raise ValueError('checked scientific source changed before execution: ' + name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module


def science(frozen):
    for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[key] = '1'
    refs = frozen['sources']
    source_module('ml_inference', refs['legacy_init'])
    legacy = {}
    for name in ('contracts', 'detector', 'model', 'prepare', 'render', 'pipeline'):
        legacy[name] = source_module('ml_inference.' + name, refs['prepare'] if name == 'prepare' else refs['legacy_' + name])
    source_module('training', refs['training_init'])
    native = source_module('training.evaluate_background', refs['native_psf'])
    simulator = source_module('training.simulate_v2', refs['simulate'])
    package_name = 'v4_frozen_physical'
    package = ModuleType(package_name)
    package.__package__ = package_name
    package.__path__ = [str(Path(refs['features']['path']).resolve().parent)]
    sys.modules[package_name] = package
    features = source_module(package_name + '.features', refs['features'])
    package.features = features
    model_loader = source_module(package_name + '.runtime_model', refs['runtime_model'])
    baseline = legacy['model'].load_ranker(frozen['models']['baseline']['_directory'])
    candidate = model_loader.load_ranker(frozen['models']['candidate']['_directory'])
    # All graph/feature/model policy checks above precede any FITS reader call.
    cache = source_module('v4_frozen_native_core', refs['native_cache'])
    latent = source_module('v3_frozen_native_latents', refs['native_latents'])
    injections = source_module('v4_frozen_native_injections', refs['native_injections'])
    geometry = source_module('v4_frozen_geometry', refs['geometry'])
    paired = source_module('v4_frozen_paired_accounting', refs['paired'])
    return SimpleNamespace(prepare=legacy['prepare'].prepare, detector=legacy['detector'],
                           native=native, simulator=simulator, features=features,
                           baseline=baseline, candidate=candidate, cache=cache,
                           latent=latent, injections=injections, geometry=geometry, paired=paired)


def measure(images, times, stack, modules):
    import numpy as np
    tracks, result = modules.cache._record_measurement(
        images, times, stack, modules.features, modules.detector, modules.baseline, modules.latent)
    rich = np.asarray(result['features_v4'], dtype=np.float32).reshape(-1, 30)
    scores = modules.candidate.score(rich)
    if scores.shape != (len(tracks),) or not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1)):
        raise ValueError('candidate returned invalid or unaligned score vector')
    result['scores_v4'] = scores.tolist()
    return tracks, result
