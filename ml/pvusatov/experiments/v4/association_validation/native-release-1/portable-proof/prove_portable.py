"""Prepare a fresh numeric-only copy, then run the exact native checker guarded.

Preparation copies verified opaque references. Only the child reads numeric
outcomes. Invoke against a sealed archive after root's report-complete handoff.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
ORIGINAL_REPO = Path('/home/usatovpavel/.codex/worktrees/spaceapps-zio-backend')
REL = Path('ml/pvusatov/experiments/v4/association_validation')
RELEASE = REL / 'native-release-1'
FREEZE_SHA = 'ae981b56f43c8a14cd6dee9ce61c48853ea7c90b63eca8ddcf586e0a3e3dbbdd'
HANDOFF_SHA = '6005fd136cdab828cac9c786c18fce2c4977289924f7ff94df3a3ddf92671abb'
CHECKER_SHA = '5b6105c10bfbdca1ea5e6ba4218d8cc357e3c9d10be2fc52cb527c20bd9bb8ca'
MAX_FILES = 3267  # 1632 full + 1632 compact + run + report + portable fields.
MAX_CACHE_BYTES = 8 * 1024**3


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


def member_path(member):
    name = member.name
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or not path.parts:
        raise ValueError('unsafe archive path: '+name)
    if name.rstrip('/') != path.as_posix():
        raise ValueError('noncanonical archive path: '+name)
    directories = {
        'native-release-1', 'native-release-1/full', 'native-release-1/compact',
        'report-native-release-1',
    }
    if member.isdir():
        if path.as_posix() not in directories:
            raise ValueError('unexpected archive directory: '+name)
    elif member.isfile():
        fixed = {
            'native-release-1/run-manifest.json',
            'report-native-release-1/research-report.json',
            'report-native-release-1/portable-fields.jsonl.gz',
        }
        numeric = (len(path.parts) == 3 and path.parts[0] == 'native-release-1'
            and path.parts[1] in ('full', 'compact') and path.name.endswith('.json.gz'))
        if path.as_posix() not in fixed and not numeric:
            raise ValueError('unexpected non-numeric archive member: '+name)
    else:
        raise ValueError('archive links and special files are forbidden: '+name)
    return path


def safe_extract(archive_path, destination, *, max_bytes=MAX_CACHE_BYTES, max_files=MAX_FILES):
    """Validate every member before writing; never delegate paths to extractall."""
    destination = Path(destination)
    if destination.is_symlink() or (destination.exists() and any(destination.iterdir())):
        raise ValueError('cache extraction requires a fresh empty directory')
    destination.mkdir(parents=True, exist_ok=True)
    result = []
    with tarfile.open(archive_path, 'r:*') as archive:
        members, seen, total, files = [], set(), 0, 0
        for member in archive:
            path = member_path(member)
            if path.as_posix() in seen:
                raise ValueError('duplicate archive member: '+member.name)
            seen.add(path.as_posix())
            if member.size < 0:
                raise ValueError('negative archive member size')
            if member.isfile():
                files += 1
                total += member.size
            if files > max_files or len(seen) > max_files+4 or total > max_bytes:
                raise ValueError('numeric archive exceeds declared extraction bounds')
            members.append((member, path))
        for member, relative in members:
            target = destination.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            digest, written = hashlib.sha256(), 0
            with archive.extractfile(member) as source, target.open('xb') as out:
                for block in iter(lambda: source.read(1024*1024), b''):
                    written += len(block)
                    digest.update(block)
                    out.write(block)
            if written != member.size:
                raise ValueError('truncated numeric archive member: '+member.name)
            result.append(dict(path=relative.as_posix(), bytes=written, sha256=digest.hexdigest()))
    return sorted(result, key=lambda value: value['path'])


def copy_verified(reference, source_repo, fresh_repo, original_repo=ORIGINAL_REPO):
    """Map a historical repository reference without changing its frozen bytes."""
    path = Path(reference['path'])
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('frozen reference is not an absolute repository path')
    try:
        relative = path.relative_to(original_repo)
    except ValueError:
        raise ValueError('frozen reference is outside the declared repository') from None
    source = Path(source_repo) / relative
    target = Path(fresh_repo) / relative
    if sha(source) != reference['sha256']:
        raise ValueError('reference hash differs: '+str(relative))
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open('rb') as original, target.open('xb') as copy:
        shutil.copyfileobj(original, copy, length=1024*1024)
    if sha(target) != reference['sha256']:
        raise ValueError('reference changed while copying: '+str(relative))
    return dict(path=relative.as_posix(), bytes=target.stat().st_size, sha256=reference['sha256'])


def prepare_references(source_repo, fresh_repo):
    freeze_relative = REL / 'engineering-repair-1/freeze.json'
    source = source_repo / freeze_relative
    if sha(source) != FREEZE_SHA:
        raise ValueError('external frozen R2 anchor differs')
    frozen = json.loads(source.read_text())
    if len(frozen['sources']) != 18:
        raise ValueError('frozen source closure is not the declared eighteen files')
    refs = list(frozen['sources'].values()) + list(frozen['model'].values())
    refs += [frozen[key] for key in ('protocol', 'selection', 'calibration', 'native_plan', 'native_seed_amendment')]
    refs += [dict(path=str(ORIGINAL_REPO/freeze_relative), sha256=FREEZE_SHA),
        dict(path=str(ORIGINAL_REPO/RELEASE/'handoff.json'), sha256=HANDOFF_SHA),
        dict(path=str(ORIGINAL_REPO/RELEASE/'independent-audit/check.py'), sha256=CHECKER_SHA)]
    copied = []
    for ref in refs:
        copied.append(copy_verified(ref, source_repo, fresh_repo))
    return copied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', required=True, type=Path)
    parser.add_argument('--cache-archive', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    args.repo_root = args.repo_root.resolve()
    args.cache_archive = args.cache_archive.resolve()
    args.output_dir = args.output_dir.resolve()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise ValueError('proof output directory must be new or empty')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    archive_sha = sha(args.cache_archive)
    fresh = Path(tempfile.mkdtemp(prefix='association-native-offline-proof-'))
    repo, cache, child_output = fresh/'repo', fresh/'cache', fresh/'proof'
    repo.mkdir()
    child_output.mkdir()
    copied = prepare_references(args.repo_root, repo)
    child = repo/RELEASE/'portable-proof/guarded_child.py'
    child.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE/'guarded_child.py', child)
    members = safe_extract(args.cache_archive, cache)
    if sha(args.cache_archive) != archive_sha:
        raise ValueError('archive changed while preparing the proof')
    required = {'native-release-1/run-manifest.json', 'report-native-release-1/research-report.json',
                'report-native-release-1/portable-fields.jsonl.gz'}
    if not required.issubset({item['path'] for item in members}):
        raise ValueError('numeric archive lacks the closed run/report/portable manifests')
    manifest = dict(archive_sha256=archive_sha, archive_bytes=args.cache_archive.stat().st_size,
                    files=len(members), extracted_bytes=sum(item['bytes'] for item in members), members=members)
    member_path = args.output_dir/'archive-member-manifest.json'
    write_new(member_path, manifest)
    audit = child_output/'native-recount.json'
    child_proof = child_output/'guarded-child.json'
    command = [sys.executable, str(child), '--checker', str(repo/RELEASE/'independent-audit/check.py'),
        '--freeze', str(repo/REL/'engineering-repair-1/freeze.json'), '--handoff', str(repo/RELEASE/'handoff.json'),
        '--run', str(cache/'native-release-1/run-manifest.json'),
        '--report', str(cache/'report-native-release-1/research-report.json'), '--output', str(audit),
        '--proof-output', str(child_proof), '--repo-root', str(repo), '--cache-root', str(cache)]
    try:
        completed = subprocess.run(command, cwd=fresh, text=True, capture_output=True, timeout=900)
        returncode, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
    except subprocess.TimeoutExpired:
        returncode, stdout, stderr = None, '', 'guarded child exceeded the fixed 900-second timeout'
    child_result = json.loads(child_proof.read_text()) if child_proof.exists() else None
    success = returncode == 0 and child_result is not None and child_result['status'] == 'PASS'
    for source in (audit, child_proof):
        if source.exists():
            shutil.copyfile(source, args.output_dir/source.name)
    proof = dict(status='PASS' if success else 'FAIL', fresh_copy_directory=str(fresh),
        cache_archive_sha256=archive_sha, cache_archive_bytes=args.cache_archive.stat().st_size,
        archive_member_manifest_sha256=sha(member_path), archive_file_members=len(members),
        preparation_script_sha256=sha(Path(__file__)), child_wrapper_sha256=sha(child),
        checker_sha256=CHECKER_SHA, frozen_r2_sha256=FREEZE_SHA, released_handoff_sha256=HANDOFF_SHA,
        copied_reference_files=copied, child_command=command, child_exit_code=returncode,
        child_stdout=stdout, child_stderr=stderr, child_timeout_seconds=900,
        child_proof_sha256=sha(child_proof) if child_proof.exists() else None,
        native_recount_sha256=sha(audit) if audit.exists() else None,
        intentional_denied_reads=child_result.get('intentional_denied_reads', []) if child_result else [],
        child_original_inputs_denied=bool(success and child_result['python_io_guard_enabled']),
        preparation_reads_original_reference_inputs=True,
        guard='Python open/list audit hook after dependency import; instrumentation only, not an OS sandbox',
        raw_fits_opened=False, model_execution=False, scoring_or_simulation=False)
    write_new(args.output_dir/'portable-proof.json', proof)
    print(json.dumps({key: proof[key] for key in ('status', 'child_exit_code', 'native_recount_sha256', 'fresh_copy_directory')}))
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
