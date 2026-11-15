"""Compile the unchanged native checker and explicitly enable its I/O guard."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import types

CHECKER_SHA = '5b6105c10bfbdca1ea5e6ba4218d8cc357e3c9d10be2fc52cb527c20bd9bb8ca'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('checker', 'freeze', 'handoff', 'run', 'report', 'output', 'proof-output', 'repo-root', 'cache-root'):
        parser.add_argument('--'+key, required=True, type=Path)
    args = parser.parse_args()
    wrapper_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    blocked, probes, enabled, audit = [], [], False, None
    result = dict(status='FAIL', checker_sha256=CHECKER_SHA, wrapper_source_sha256=wrapper_sha,
        python_io_guard_enabled=False, intentional_denied_reads=[], all_denied_reads=[],
        raw_fits_opened=False, producer_functions_imported=False, model_execution=False,
        scoring_or_simulation=False,
        guard='Python open/list audit hook after dependency import; not an OS sandbox')
    try:
        for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
            os.environ[name] = '1'
        # Initialize dependencies before the checker installs the open/list hook.
        import numpy  # noqa: F401
        source = args.checker.read_bytes()
        if hashlib.sha256(source).hexdigest() != CHECKER_SHA:
            raise ValueError('independent checker source differs from its external anchor')
        checker = types.ModuleType('guarded_independent_native_checker')
        checker.__file__ = str(args.checker)
        sys.modules[checker.__name__] = checker
        exec(compile(source, str(args.checker), 'exec'), checker.__dict__)
        blocked = checker.install_io_guard(args)
        enabled = True
        probes = list(blocked)
        expected = [str(checker.ORIGINAL_REPO/'ml/pvusatov/experiments/v4/association_validation/protocol.json'),
            str(checker.ORIGINAL_CACHE/'synthetic-repair-1/run-manifest.json'), '/etc/passwd']
        if probes != expected:
            raise ValueError('the three intentional forbidden-read probes did not close')
        sys.argv = [str(args.checker)]
        for key in ('freeze', 'handoff', 'run', 'report', 'output', 'repo_root', 'cache_root'):
            sys.argv.extend(['--'+key.replace('_', '-'), str(getattr(args, key))])
        # Only now may main() read the copied closure and extracted numeric data.
        checker.main()
        audit = json.loads(args.output.read_text())
        if audit.get('numeric_evidence_checks_passed') is not True or blocked != probes:
            raise ValueError('numeric recount failed or attempted an additional forbidden read')
        result.update(status='PASS', audit_status=audit['status'],
            audit_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest())
    except BaseException as error:
        result.update(error_type=type(error).__name__, error=str(error))
    result.update(python_io_guard_enabled=enabled, intentional_denied_reads=probes,
                  all_denied_reads=list(blocked))
    with args.proof_output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
