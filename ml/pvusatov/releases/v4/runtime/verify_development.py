"""Inference-only DEVELOPMENT runtime/preset proof; no fitting or final access."""
from __future__ import annotations
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import resource
import tempfile
import time
import numpy as np
from PIL import Image
from ml_inference.pipeline import run

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-dir', action='append', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise ValueError('proof output already exists')
    models = [Path(p).resolve() for p in args.model_dir]
    if any('final' in str(p).lower() or 'quarant' in str(p).lower() for p in models):
        raise ValueError('development artifacts only')
    records = []
    frame_hashes = {}
    with tempfile.TemporaryDirectory(prefix='spaceapps-v4-runtime-proof-') as scratch:
        for i, model in enumerate(models):
            for preset in ['comet-d2','comet-d6','vesta-d3','vesta-d6']:
                started = time.perf_counter()
                destination = Path(scratch) / str(i) / preset
                result = run(dict(schema_version=1,analysis_id='v4-development-proof',
                    source=dict(kind='preset',preset_id=preset),model_dir=str(model)),destination)
                resources = []
                for item in result['resources']:
                    path = destination / item['name']
                    if path.stat().st_size != item['size_bytes']:
                        raise ValueError('resource size differs')
                    with Image.open(path) as image:
                        image.load()
                        resources.append(dict(name=item['name'],sha256=sha(path),size_bytes=path.stat().st_size,
                            dimensions=list(image.size),format=image.format))
                frames = {r['name']:r['sha256'] for r in resources if r['name'].startswith(('frame-','difference-','bloom-'))}
                if preset in frame_hashes and frames != frame_hashes[preset]:
                    raise ValueError('same residual pool produced different frame/evidence pixels across model families')
                frame_hashes[preset] = frames
                # Offline truth opens only after complete inference/scoring/rendering.
                with np.load(ROOT / 'fixtures' / (preset+'.npz'),allow_pickle=False) as archive:
                    expected = archive['expected_xy']
                matches = [c for c in result['candidates'] if len(c['detections']) == len(expected) and
                    np.max(np.linalg.norm(np.asarray([[d['x'],d['y']]for d in c['detections']])-expected,axis=1)) <= 1.5]
                if not matches:
                    raise ValueError('known development target missing: '+preset)
                if preset.startswith('vesta') and any(c['score'] is not None or c['method'] != 'bloom_track' for c in matches):
                    raise ValueError('flagged target incorrectly receives learned score')
                records.append(dict(model_dir=str(model),model=result['model'],preset=preset,fixture_sha256=sha(ROOT/'fixtures'/(preset+'.npz')),
                    observed_pool=result['comparison'],published_candidates=len(result['candidates']),
                    known_target_ranks=[c['rank']for c in matches],known_target_methods=[c['method']for c in matches],
                    known_target_scores=[c['score']for c in matches],
                    residual_score_kinds=sorted({c['score_kind']for c in result['candidates']if c['method']=='residual_track'}),
                    bloom_scores_null=all(c['score'] is None for c in result['candidates']if c['method']=='bloom_track'),
                    settings=result['settings'],resources=resources,wall_seconds=time.perf_counter()-started))
    proof = dict(designation='DEVELOPMENT integration only; not final/promotion authorization',
        runtime_sources={p.name:sha(p)for p in sorted((ROOT/'ml_inference').glob('*.py'))},
        verification_source_sha256=sha(Path(__file__)),
        model_sources={str(p):dict(artifact_sha256=sha(p/'ranker.onnx'),metadata_sha256=sha(p/'metadata.json'))for p in models},
        versions={p:version(p)for p in ['numpy','onnx','onnxruntime','scipy','astropy','Pillow']},
        cases=records,decoded_pngs=sum(len(r['resources'])for r in records),
        same_frame_evidence_pngs_across_models=True,
        peak_process_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        limitation='unconstrained local process measurement, not the separate1CPU/1GiB deployment gate')
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary = output.with_suffix(output.suffix+'.tmp')
    temporary.write_text(json.dumps(proof,indent=2,allow_nan=False)+'\n');temporary.replace(output)
    print(json.dumps(dict(output=str(output),sha256=sha(output),cases=len(records),decoded_pngs=proof['decoded_pngs'])))


if __name__ == '__main__':
    main()
