"""Release evidence must identify the frozen model and retain complete audit outputs."""
import gzip
import hashlib
import json
from pathlib import Path

# Historical freeze checks use the immutable, self-contained release. Current
# runtime behavior is exercised separately against the active installation.
ROOT = Path(__file__).resolve().parents[3] / 'releases' / 'v2'
MODELS = ROOT / 'backend' / 'inference' / 'models'


def read(name):
    return json.loads((MODELS / name).read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_release_inventory_is_complete_and_every_hash_matches():
    release = read('release-manifest.json')
    assert release['selected_before_final_test'] is True
    assert release['model_sha256'] == read('metadata.json')['sha256'] == digest(MODELS / 'ranker.onnx')
    for name, expected in release['audit_sha256'].items():
        path = MODELS / name
        assert path.is_file(), name
        assert digest(path) == expected, name
        if name.endswith('.json'):
            json.loads(path.read_text())
    required = {p.relative_to(MODELS).as_posix() for p in MODELS.rglob('*')
                if p.is_file() and 'experiments' not in p.parts
                and p.name not in {'release-manifest.json', '.gitignore',
                                   'field-candidates.json', 'final-field-candidates.json'}}
    assert set(release['audit_sha256']) == required


def test_frozen_source_has_only_the_documented_pretest_accounting_exception():
    freeze = read('freeze.json')
    amendment = read('pretest-accounting-amendment.json')
    assert digest(MODELS / 'freeze.json') == amendment['original_freeze_sha256']
    assert freeze['model_sha256'] == amendment['model_sha256'] == digest(MODELS / 'ranker.onnx')
    assert freeze['training_manifest_sha256'] == digest(MODELS / 'training-manifest.json')
    assert freeze['metadata_sha256'] == digest(MODELS / 'metadata.json')
    assert digest(ROOT / 'backend/inference/training/archive_v2/evaluate_background.py') == amendment['original_evaluator_sha256']
    differences = [name for name, expected in freeze['code_sha256'].items() if digest(ROOT / name) != expected]
    assert differences == ['backend/inference/training/evaluate_background.py']
    for name, expected in amendment['code_sha256'].items():
        assert digest(ROOT / name) == expected, name
    assert freeze['frozen_at_utc'] < amendment['amended_at_utc']
    assert amendment['reserved_real_field_pixels_unopened'] is True


def test_final_synthetic_groups_are_disjoint_from_development_partitions():
    final = read('evaluation.json')
    development = read('training-manifest.json')['partitions']
    fields = json.loads(gzip.decompress((MODELS / 'evaluation.fields.json.gz').read_bytes()))
    assert [row['seed'] for row in fields] == final['parent_field_seeds'] == list(range(500000, 500400))
    assert not set(final['parent_field_seeds']).intersection(seed for rows in development.values() for seed in rows)
    subsets = read('evaluation-subsets.json')
    assert subsets['source_sha256'] == digest(MODELS / subsets['source'])
    assert hashlib.sha256(gzip.decompress((MODELS / subsets['source']).read_bytes())).hexdigest() == subsets['uncompressed_source_sha256']
    for ranker in ['baseline', 'random_forest']:
        assert subsets['groups']['all'][ranker] == final[ranker]
    assert sum(row['truth_count'] for row in fields) == final['baseline']['top1']['injected_tracks']
    assert sum(len(row['features']) for row in fields) == final['baseline']['top1']['candidates']


def test_full_real_outputs_match_summaries_and_record_model_identity():
    for name in ['real-background-evaluation.json', 'm101-development-evaluation.json']:
        summary = read(name)
        compressed = MODELS / summary['trial_details_file']
        assert digest(compressed) == summary['trial_details_sha256']
        full_bytes = gzip.decompress(compressed.read_bytes())
        assert hashlib.sha256(full_bytes).hexdigest() == summary['full_evaluation_sha256']
        full = json.loads(full_bytes)
        assert len(full['trials']) == summary['summary']['injections']
        for key, value in full.items():
            if key != 'trials':
                assert summary[key] == value, (name, key)
        assert full['model_sha256'] == read('metadata.json')['sha256']


def test_final_real_cohorts_can_be_recomputed_without_reopening_images():
    from training.evaluate_background import summarize
    summary = read('real-background-evaluation.json')
    full = json.loads(gzip.decompress((MODELS / summary['trial_details_file']).read_bytes()))
    assert summarize(full['trials'], 3) == summary['summary']
    assert summary['summary']['finite_center_coverage_ge3']['injections'] == 150
    assert summary['independent_parent_fields'] == 1
    assert summary['parent_exposures'] == 4
    assert summary['derivative_trials_are_correlated'] is True
    assert summary['model_fitted_or_changed'] is False
    assert summary['source_code_sha256'] == read('pretest-accounting-amendment.json')['amended_evaluator_sha256']
    assert all(match['model_score'] > 0 for trial in full['trials'] for match in trial['recovery']['matches'])
