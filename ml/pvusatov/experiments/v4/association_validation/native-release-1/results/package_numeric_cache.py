"""Package a CLOSED native run's numeric evidence without interpreting outcomes.

Usage (only after the publisher has closed run-manifest.json and the report):
    python package_numeric_cache.py --cache-root ORIGINAL --output NEW

ORIGINAL may be a relocated copy of /tmp/spaceapps-association-validation.
References and source bytes stay unchanged. NEW must not exist. Output contains
deterministic uncompressed tar parts (256 MiB maximum) and a hash manifest.
No FITS files, models, source discovery, downloads, or publication are involved.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile


ORIGINAL_CACHE = PurePosixPath('/tmp/spaceapps-association-validation')
RUN = 'native-release-1'
REPORT = 'report-native-release-1'
PART_BYTES = 256 * 1024**2
MAX_CACHE_BYTES = 8 * 1024**3
MAX_MANIFEST_BYTES = 16 * 1024**2
BLOCK_BYTES = 1024**2


def _regular(root, name):
    """Resolve a known relative member without accepting links or special files."""
    path = root
    for component in PurePosixPath(name).parts:
        path = path / component
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            raise ValueError(f'missing numeric evidence: {name}') from exc
        if stat.S_ISLNK(mode):
            raise ValueError(f'symlink forbidden: {name}')
    if not stat.S_ISREG(mode):
        raise ValueError(f'not a regular numeric evidence file: {name}')
    return path


def _open_regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    stream = os.fdopen(fd, 'rb')
    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
        stream.close()
        raise ValueError(f'not a regular file: {path}')
    return stream


def _measure(root, name):
    path = _regular(root, name)
    digest = hashlib.sha256()
    size = 0
    with _open_regular(path) as stream:
        while block := stream.read(BLOCK_BYTES):
            size += len(block)
            if size > MAX_CACHE_BYTES:
                raise ValueError('numeric member exceeds fixed 8 GiB bound')
            digest.update(block)
    return dict(path=name, bytes=size, sha256=digest.hexdigest())


def _reference_name(root, ref, role):
    if not isinstance(ref, dict) or not isinstance(ref.get('path'), str):
        raise ValueError(f'missing {role} reference')
    text = ref['path']
    if '\\' in text or '\x00' in text or any(part in {'.', '..', ''} for part in text.lstrip('/').split('/')):
        raise ValueError('unsafe reference path')
    path = PurePosixPath(text)
    if path.is_absolute():
        for prefix in (ORIGINAL_CACHE, PurePosixPath(root.as_posix())):
            if path.is_relative_to(prefix):
                path = path.relative_to(prefix)
                break
        else:
            raise ValueError('reference escapes cache root')
    if len(path.parts) != 3 or path.parts[:2] != (RUN, role) or not path.name.endswith('.json.gz'):
        raise ValueError(f'unexpected {role} numeric reference path')
    if (type(ref.get('bytes')) is not int or ref['bytes'] < 0
            or not re.fullmatch('[0-9a-f]{64}', str(ref.get('sha256')))):
        raise ValueError('reference requires exact SHA256 and byte size')
    return path.as_posix()


def _numeric_members(root, expected_records):
    """Strictly enumerate both record directories, including orphan full records."""
    names = []
    run = root / RUN
    if not run.is_dir() or run.is_symlink():
        raise ValueError('missing closed run directory')
    for entry in run.iterdir():
        if entry.is_symlink() or entry.name not in {'run-manifest.json', 'compact', 'full'}:
            raise ValueError(f'unexpected native run member: {entry.name}')
    for role in ('compact', 'full'):
        directory = run / role
        if not directory.exists() and role == 'full':
            continue  # A closed run consisting entirely of failures has no full records.
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError(f'missing numeric {role} directory')
        count = 0
        for entry in directory.iterdir():
            if entry.is_symlink() or not entry.is_file() or not entry.name.endswith('.json.gz'):
                raise ValueError(f'unexpected numeric member: {entry.name}')
            count += 1
            if count > expected_records:
                raise ValueError(f'too many {role} numeric records')
            names.append(f'{RUN}/{role}/{entry.name}')
    return names


def _inventory(root, expected_records):
    run_name = f'{RUN}/run-manifest.json'
    manifest_path = _regular(root, run_name)
    if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError('closed run manifest exceeds fixed 16 MiB bound')
    with _open_regular(manifest_path) as stream:
        run = json.load(stream)
    outputs = run.get('outputs') if isinstance(run, dict) else None
    if (not isinstance(run, dict) or run.get('kind') != 'native' or type(run.get('planned')) is not int
            or run['planned'] != expected_records or not isinstance(outputs, list)
            or len(outputs) != expected_records):
        raise ValueError(f'closed manifest requires every one of {expected_records} planned records')
    identities = set()
    refs = {}
    error_records = 0
    for row in outputs:
        if (not isinstance(row, dict) or not isinstance(row.get('case_id'), str)
                or not row['case_id'] or row['case_id'] in identities or 'error' not in row):
            raise ValueError('closed manifest requires distinct record identities and error status')
        identities.add(row['case_id'])
        error_records += row['error'] is not None
        if row['error'] is None and 'full_pool' not in row:
            raise ValueError('successful record is missing full_pool reference')
        for key, role in (('compact', 'compact'), ('full_pool', 'full')):
            if key == 'full_pool' and key not in row:
                continue
            ref = row.get(key)
            name = _reference_name(root, ref, role)
            if name in refs:
                raise ValueError('different output records reuse a numeric reference')
            refs[name] = ref
    if (type(run.get('error_records')) is not int or run['error_records'] != error_records
            or type(run.get('complete')) is not bool or run['complete'] != (error_records == 0)):
        raise ValueError('closed manifest error count or complete flag differs')
    names = _numeric_members(root, expected_records)
    names.extend([run_name, f'{REPORT}/research-report.json', f'{REPORT}/portable-fields.jsonl.gz'])
    members = [_measure(root, name) for name in sorted(names)]
    inventory = {member['path']: member for member in members}
    for name, ref in refs.items():
        member = inventory.get(name)
        if member is None or any(member[key] != ref[key] for key in ('bytes', 'sha256')):
            raise ValueError(f'numeric reference SHA256/bytes differs: {name}')
    if sum(member['bytes'] for member in members) > MAX_CACHE_BYTES:
        raise ValueError('numeric evidence exceeds fixed 8 GiB bound')
    return members, error_records


class _Parts:
    def __init__(self, output, part_bytes):
        self.output = output
        self.part_bytes = part_bytes
        self.parts = []
        self.stream = None
        self.total = 0
        self.whole = hashlib.sha256()

    def _finish(self):
        if self.stream is not None:
            self.stream.close()
            self.parts.append(dict(path=self.name, bytes=self.size, sha256=self.digest.hexdigest()))
            self.stream = None

    def write(self, data):
        self.whole.update(data)
        self.total += len(data)
        remaining = memoryview(data)
        while remaining:
            if self.stream is None:
                self.name = f'native-numeric-cache.tar.part{len(self.parts):03d}'
                self.stream = (self.output / self.name).open('xb')
                self.size, self.digest = 0, hashlib.sha256()
            block = remaining[:self.part_bytes - self.size]
            self.stream.write(block)
            self.digest.update(block)
            self.size += len(block)
            remaining = remaining[len(block):]
            if self.size == self.part_bytes:
                self._finish()
        return len(data)


class _CheckedReader:
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()

    def read(self, size):
        data = self.stream.read(size)
        self.digest.update(data)
        return data


def package_cache(cache_root, output, *, expected_records=1632, part_bytes=PART_BYTES):
    """Validate first, then append new deterministic artifacts; never overwrite.

    The record/part parameters support small analytic tests. The CLI always
    enforces the native release's 1632 records and 256 MiB part limit.
    Memory use is bounded by the small run manifest, inventory, and copy blocks.
    """
    root = Path(cache_root).absolute()
    output = Path(output).absolute()
    if any(path.is_symlink() for path in (root, *root.parents)) or not root.is_dir():
        raise ValueError('cache root must be a real directory')
    if output.exists() or output.is_symlink():
        raise ValueError('output directory must not exist')
    if type(expected_records) is not int or expected_records < 1 or type(part_bytes) is not int or part_bytes < 1:
        raise ValueError('record and part bounds must be positive integers')
    members, errors = _inventory(root, expected_records)
    output.mkdir(parents=True, exist_ok=False)
    writer = _Parts(output, part_bytes)
    try:
        with tarfile.open(fileobj=writer, mode='w|', format=tarfile.USTAR_FORMAT) as archive:
            for member in members:
                path = _regular(root, member['path'])
                info = tarfile.TarInfo(member['path'])
                info.size = member['bytes']
                info.mode = 0o644
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ''
                with _open_regular(path) as stream:
                    checked = _CheckedReader(stream)
                    archive.addfile(info, checked)
                    if stream.read(1) or checked.digest.hexdigest() != member['sha256']:
                        raise ValueError(f'numeric evidence changed while archiving: {member["path"]}')
    finally:
        writer._finish()
    manifest = dict(schema_version=1, format='deterministic-ustar-uncompressed-split',
                    planned_records=expected_records, error_records=errors,
                    archive_bytes=writer.total, archive_sha256=writer.whole.hexdigest(),
                    part_bytes=part_bytes, members=members, parts=writer.parts)
    with (output / 'manifest.json').open('x') as stream:
        json.dump(manifest, stream, sort_keys=True, separators=(',', ':'), allow_nan=False)
        stream.write('\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = package_cache(args.cache_root, args.output)
    except (ValueError, OSError, json.JSONDecodeError, tarfile.TarError) as exc:
        parser.exit(1, f'Packaging rejected: {exc}\n')
    print(json.dumps(dict(archive_sha256=manifest['archive_sha256'],
                          archive_bytes=manifest['archive_bytes'],
                          members=len(manifest['members']), parts=len(manifest['parts']))))


if __name__ == '__main__':
    main()
