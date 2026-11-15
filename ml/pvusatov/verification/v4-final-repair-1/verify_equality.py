"""Root's fixed, blinded entry point after both canonical jobs exit zero."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ANCHOR = '1225e2de97c38381818d9ccb3676c1d132701b02b8bc19dc09e0d1785c3e38e4'


def main():
    path = HERE/'freeze.json'; raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ANCHOR: raise ValueError('canonical freeze changed')
    ref = json.loads(raw)['sources']['execute']; source_path = Path(ref['path']); source = source_path.read_bytes()
    if hashlib.sha256(source).hexdigest() != ref['sha256']: raise ValueError('checked bootstrap changed')
    spec = importlib.util.spec_from_file_location('root_canonical_equality_bootstrap', source_path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(source, str(source_path), 'exec'), module.__dict__)
    frozen, validator = module.bootstrap(path, ANCHOR); sys.modules['freeze'] = validator
    equality = validator.exact_module('root_checked_canonical_equality', frozen['sources']['attempt_equality'], HERE)
    output = HERE/'scientific-equality-proof.json'
    if output.exists(): raise ValueError('equality proof already exists')
    directory = Path('/tmp/spaceapps-v4-evaluation/final-1225')
    proof = equality.verify_attempts(path, ANCHOR, directory/'native/run-native-manifest.json',
                                    directory/'synthetic/run-synthetic-manifest.json', both_runs_finished=True)
    output.write_text(json.dumps(proof, indent=2, allow_nan=False) + '\n')
    print(json.dumps(proof, sort_keys=True))
    if proof['passes'] is not True: raise RuntimeError('Unexpected science difference; remain blinded')


if __name__ == '__main__':
    main()
