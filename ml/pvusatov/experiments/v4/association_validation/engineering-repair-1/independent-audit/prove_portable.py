"""Prepare a fresh copy, extract numeric-cache archive, and run guarded audit.

This preparation process reads original source/cache files to make the copy. The
child audit enables its Python I/O guard only after importing NumPy. The guard
is an instrumentation check, not an OS sandbox. No producer module is imported.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

REL = Path('ml/pvusatov/experiments/v4/association_validation/engineering-repair-1')
ORIGINAL = Path('/home/usatovpavel/.codex/worktrees/spaceapps-zio-backend')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-root', type=Path, required=True)
    p.add_argument('--cache-archive', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = p.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fresh = Path(tempfile.mkdtemp(prefix='association-offline-proof-'))
    repo, cache = fresh/'repo', fresh/'cache'
    repair = args.repo_root/REL
    frozen = json.loads((repair/'freeze.json').read_text())
    preserved = json.loads((repair/'first-attempt-manifest.json').read_text())
    refs = list(frozen['sources'].values())+list(frozen['model'].values())
    refs += [frozen[k] for k in ('protocol', 'selection', 'calibration', 'native_plan', 'native_seed_amendment')]
    copies = []
    for ref in refs:
        rel = Path(ref['path']).relative_to(ORIGINAL)
        source, target = args.repo_root/rel, repo/rel
        assert sha(source) == ref['sha256']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copies.append({'path': str(rel), 'sha256': sha(target)})
    relative_files = [Path('freeze.json'), Path('first-attempt-manifest.json'), Path('independent-audit/check.py')]
    relative_files += [Path(ref['snapshot_path']) for ref in list(preserved['sources'].values())+list(preserved['files'].values())]
    for rel in relative_files:
        source, target = repair/rel, repo/REL/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copies.append({'path': str(REL/rel), 'sha256': sha(target)})
    cache.mkdir()
    with tarfile.open(args.cache_archive, 'r:*') as archive:
        archive.extractall(cache, filter='data')
        members = []
        for member in archive.getmembers():
            if not member.isfile():
                continue
            assert member.name.endswith(('.json', '.json.gz', '.jsonl.gz')), ('unexpected non-numeric-cache member', member.name)
            target = cache/member.name
            members.append(dict(path=member.name, bytes=member.size, sha256=sha(target)))
    member_manifest = args.output_dir/'archive-member-manifest.json'
    member_manifest.write_text(json.dumps(dict(archive_path=str(args.cache_archive.resolve()),
        archive_sha256=sha(args.cache_archive), archive_bytes=args.cache_archive.stat().st_size,
        files=len(members), members=members), indent=2, sort_keys=True)+'\n')
    child_output = fresh/'portable-recount.json'
    command = [sys.executable, str(repo/REL/'independent-audit/check.py'),
               '--repair', str(repo/REL), '--run', str(cache/'synthetic-repair-1/run-manifest.json'),
               '--report', str(cache/'report-repair-1/research-report.json'), '--output', str(child_output),
               '--repo-root', str(repo), '--cache-root', str(cache), '--deny-original-inputs']
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', PYTHONDONTWRITEBYTECODE='1')
    child = subprocess.run(command, env=env, cwd=fresh, text=True, capture_output=True, timeout=900)
    assert child.returncode == 0, (child.returncode, child.stdout, child.stderr)
    result = json.loads(child_output.read_text())
    assert result['status'] == 'PASS' and result['python_io_guard_enabled'] is True
    assert len(result['intentional_original_and_outside_read_probes_rejected']) == 3
    assert result['identity_equality_fields'] == 1000 and result['audited_candidate_rows'] == 271293
    target = args.output_dir/'portable-recount.json'
    shutil.copyfile(child_output, target)
    proof = dict(status='PASS', cache_archive_sha256=sha(args.cache_archive), cache_archive_bytes=args.cache_archive.stat().st_size,
                 preparation_script_sha256=sha(__file__), fresh_copy_directory=str(fresh), child_command=command,
                 child_stdout=child.stdout, child_stderr=child.stderr, child_exit_code=child.returncode,
                 copied_reference_files=copies, portable_recount_sha256=sha(target),
                 archive_member_manifest_sha256=sha(member_manifest), archive_file_members=len(members),
                 guard='Python open/list audit hook after NumPy import; instrumentation only, not an OS sandbox',
                 preparation_reads_original_inputs=True, child_original_inputs_denied=True,
                 intentional_denied_reads=result['intentional_original_and_outside_read_probes_rejected'],
                 model_execution=False, raw_pixels_read=False, scoring_or_simulation=False)
    (args.output_dir/'portable-proof.json').write_text(json.dumps(proof, indent=2, sort_keys=True)+'\n')
    print(json.dumps({k: proof[k] for k in ('status', 'fresh_copy_directory', 'child_exit_code', 'portable_recount_sha256')}))


if __name__ == '__main__':
    main()
