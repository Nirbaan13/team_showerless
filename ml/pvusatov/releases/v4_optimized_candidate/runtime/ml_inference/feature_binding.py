"""Fail closed on both actual producer and immutable training/reference source."""
import hashlib
import json
from pathlib import Path

EXPECTED_PRODUCER = {'schema_version': 1, 'status': 'unpromoted_performance_candidate', 'actual_source_file': 'fast_features.py', 'actual_source_sha256': '5ac4716292ba19af8b7ef124aac9c4386d8b501e055d46c898bae70f9a9e2ca6', 'reference_source_file': 'features.py', 'reference_source_sha256': '8433495da9d0eda745903a9d63f430e3fc8b7c283b2ad7aded96511059b91282', 'feature_contract_sha256': '67ad2d61e3f26384860c313f69e916ab6b9ed1c46c6016012af0ae7144d3977b', 'model_metadata_feature_source_role': 'training_and_reference_source', 'implementation': 'grouped-valid-epoch-photometry-v1', 'ported_prototype_sha256': '47e3486cc94e65f520244575fc5dee8517ac5aa2e4f84c3f8a70c477df90102d'}


def verify_feature_producer():
    own = Path(__file__).resolve().parent
    path = own / 'producer-manifest.json'
    if path.stat().st_size > 16384:
        raise ValueError('candidate producer manifest exceeds bound')
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError('duplicate producer manifest key')
            result[key] = value
        return result
    actual = json.loads(path.read_text(), object_pairs_hook=pairs)
    if actual != EXPECTED_PRODUCER:
        raise ValueError('candidate producer manifest differs')
    for prefix in ('actual', 'reference'):
        source = own / EXPECTED_PRODUCER[prefix + '_source_file']
        if hashlib.sha256(source.read_bytes()).hexdigest() != EXPECTED_PRODUCER[prefix + '_source_sha256']:
            raise ValueError('candidate feature source differs')
    return dict(EXPECTED_PRODUCER)


def extract_features(*args, **kwargs):
    # run() verifies before prepare(), so adapter import cannot precede binding.
    from .fast_features import extract_features as produce
    return produce(*args, **kwargs)
