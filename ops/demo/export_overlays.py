#!/usr/bin/env python3
"""Export service overlays; preserve Docker OCI IDs and normalize Podman legacy links."""
import argparse
import copy
import gzip
import json
import posixpath
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile

from build_variants import clean_environment


def path_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts or '\\' in name:
        raise ValueError('Unsafe image payload path: ' + name)
    return name


def normalize_archive(source, output):
    with tarfile.open(source, 'r:*') as archive:
        members = {}
        for member in archive:
            path_name(member.name)
            if member.name in members:
                raise ValueError('Duplicate image payload: ' + member.name)
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                raise ValueError('Special file in image archive: ' + member.name)
            members[member.name] = member
        if 'manifest.json' not in members:
            raise ValueError('Docker-compatible export manifest is missing')
        if members['manifest.json'].size > 8 * 1024 * 1024:
            raise ValueError('Oversized image export manifest')
        manifest = json.load(archive.extractfile(members['manifest.json']))
        required = {'manifest.json'}
        for record in manifest:
            required.add(record['Config'])
            required.update(record.get('Layers', []))
        required.update(name for name in members if name.startswith('blobs/sha256/'))
        for name in required:
            path_name(name)
            if name not in members:
                raise ValueError('Referenced image payload is missing: ' + name)

        def resolve(name):
            seen = set()
            while name not in seen:
                seen.add(name)
                member = members.get(name)
                if member is None:
                    raise ValueError('Image link target is missing')
                if member.isfile():
                    return member
                if not (member.issym() or member.islnk()):
                    raise ValueError('Referenced image payload is not a regular file')
                target = member.linkname if member.islnk() else posixpath.join(posixpath.dirname(name), member.linkname)
                name = path_name(posixpath.normpath(target))
            raise ValueError('Cyclic image archive link')

        with tarfile.open(output, 'w:gz', compresslevel=1) as target:
            for name, member in members.items():
                if member.isdir():
                    continue
                if not member.isfile() and name not in required:
                    continue
                payload = resolve(name)
                copied = copy.copy(member)
                copied.type = tarfile.REGTYPE
                copied.linkname = ''
                copied.size = payload.size
                target.addfile(copied, archive.extractfile(payload))


def export(inventory_path, output, executable='docker'):
    inventory = json.loads(Path(inventory_path).read_text())
    images = list(dict.fromkeys(item['image'] for item in inventory['services'].values() if item.get('derived_from_deployed_image')))
    if not images:
        raise ValueError('No derived service images to export')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = output.with_name(output.name + '.partial')
    try:
        if executable == 'docker':
            # Keep index.json and every content-addressed blob exactly as Docker
            # exports them; re-exporting via Podman would lose manifest IDs.
            with pending.open('wb') as destination:
                process = subprocess.Popen(['docker', 'image', 'save', *images], stdout=subprocess.PIPE, env=clean_environment())
                try:
                    with gzip.GzipFile(fileobj=destination, mode='wb', compresslevel=1) as compressed:
                        shutil.copyfileobj(process.stdout, compressed, 1024 * 1024)
                finally:
                    process.stdout.close()
                if process.wait() != 0:
                    raise RuntimeError('Docker image export failed')
        else:
            with tempfile.TemporaryDirectory(prefix='spaceapps-overlay-export-') as temporary:
                raw = Path(temporary) / 'podman.tar'
                subprocess.run(['podman', 'save', '--format', 'docker-archive', '--multi-image-archive', '--output', str(raw), *images], check=True, env=clean_environment())
                normalize_archive(raw, pending)
        pending.replace(output)
    finally:
        pending.unlink(missing_ok=True)
    return images


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--engine', choices=['docker', 'podman'], default='docker')
    args = parser.parse_args()
    export(args.inventory, args.output, args.engine)
