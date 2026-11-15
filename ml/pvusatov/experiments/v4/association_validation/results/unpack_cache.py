"""Verify and extract the exact published numeric audit cache, without models."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent / 'numeric-cache'
EXPECTED = '928f1f8824fa8575c11087d74aa3b3901b9f5f5a1bb1d1172f89f0f873b8131c'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination.exists():
        raise ValueError('A new extraction directory is required')
    manifest = json.loads((HERE / 'manifest.json').read_text())
    assert manifest['archive_sha256'] == EXPECTED and manifest['archive_bytes'] == 107970560
    with tempfile.TemporaryDirectory(prefix='association-published-cache-') as temp:
        joined = Path(temp) / 'cache.tar'
        whole = hashlib.sha256()
        with joined.open('wb') as output:
            for index, part in enumerate(manifest['parts']):
                assert part['path'] == f'cache.tar.part{index:03d}'
                path = HERE / part['path']
                assert path.is_file() and not path.is_symlink() and path.stat().st_size == part['bytes']
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    while block := stream.read(1024**2):
                        whole.update(block); digest.update(block); output.write(block)
                assert digest.hexdigest() == part['sha256'], 'Published part changed'
        assert whole.hexdigest() == EXPECTED and joined.stat().st_size == manifest['archive_bytes']
        with tarfile.open(joined, 'r:') as archive:
            members = archive.getmembers()
            assert sum(row.isfile() for row in members) == 3156
            for row in members:
                name = PurePosixPath(row.name)
                assert not name.is_absolute() and '..' not in name.parts
                assert name.parts[0] in {'synthetic', 'synthetic-repair-1', 'report-repair-1'}
                assert row.isfile() or row.isdir(), 'Links and special archive entries are forbidden'
            destination.mkdir(parents=True)
            archive.extractall(destination, filter='data')
    print(json.dumps(dict(output=str(destination), archive_sha256=EXPECTED, file_members=3156)))


if __name__ == '__main__':
    main()
