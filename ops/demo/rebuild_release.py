#!/usr/bin/env python3
"""Manually rebuild a versioned real v1 release using a pinned public seed bundle."""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile

import bundle
import publish_release
from build_variants import build as build_variants, clean_environment, image_engine, source_revision
from build_api_variant import build as build_api
from export_overlays import export

REPOSITORY = 'Nirbaan13/team_showerless'
SEED_RELEASE = 'demo-v1'
SEED_SHA256 = 'd4999b528a18ee527856b0ca156e1348e989a0fb9a340c1d58702f0ad3c99efe'
ASSET = 'spaceapps-demo-v1.tar.gz'


def check_repository(repository):
    if repository.lower() != REPOSITORY.lower():
        raise ValueError('rebuild repository must be ' + REPOSITORY)


def release_tag(revision):
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('release requires an exact lowercase 40-character source SHA')
    return 'demo-v1-main-' + revision


def verify_download(archive, checksum):
    if not re.fullmatch(r'[0-9a-f]{64}', checksum) or bundle.digest_file(archive)['sha256'] != checksum:
        raise ValueError('downloaded seed SHA256 checksum differs from the reviewed pin')


def original_inventory(inventory):
    originals = {item['image_id']: item for item in inventory.get('source_images', [])}
    recovered = copy.deepcopy(inventory)
    for service, record in inventory['services'].items():
        parent = record.get('parent_image_id', record['image_id'])
        if parent not in originals:
            raise ValueError(service + ': parent is not a captured VPS source image')
        recovered['services'][service] = copy.deepcopy(originals[parent])
    recovered.pop('api_source_revision', None)
    recovered.pop('service_source_revision', None)
    return bundle.validate_inventory(recovered)


def extract_seed(archive_path, destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('seed extraction destination already exists')
    with tarfile.open(archive_path, 'r:*') as archive:
        members = bundle.archive_members(archive)
        for name in members:
            relative = bundle.PurePosixPath(name)
            if relative.parts[0] not in bundle.SEED_ROOTS and not (len(relative.parts) == 1 and relative.suffix == '.json'):
                raise ValueError('seed archive root is outside the science data allowlist')
        destination.mkdir(parents=True)
        for name, member in members.items():
            target = destination.joinpath(*bundle.PurePosixPath(name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
        for root in bundle.SEED_ROOTS:
            (destination / root).mkdir(exist_ok=True)


def rebuild(work_dir, revision, executable='docker', seed_release=SEED_RELEASE, seed_sha256=SEED_SHA256):
    repository = os.environ.get('GITHUB_REPOSITORY', REPOSITORY)
    check_repository(repository)
    if os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise ValueError('manually dispatch this workflow on main')
    if seed_release != SEED_RELEASE or seed_sha256 != SEED_SHA256:
        raise ValueError('seed release and checksum must match the reviewed public v1 pin')
    root = Path(__file__).resolve().parents[2]
    source_revision(root, revision)
    tag = release_tag(revision)
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if not token:
        raise ValueError('a GitHub workflow token is required for release assets')
    gh_environment = dict(clean_environment(), GH_TOKEN=token)

    def gh(*arguments, **kwargs):
        kwargs.setdefault('check', True)
        return subprocess.run(['gh', *arguments], env=gh_environment, **kwargs)

    existing = gh('release', 'view', tag, '--repo', REPOSITORY, capture_output=True, text=True, check=False)
    if existing.returncode == 0:
        raise ValueError('immutable versioned release already exists: ' + tag)
    # Resolve the pin before allocating build storage; no release is overwritten.
    work_dir = Path(work_dir).resolve()
    if work_dir.exists():
        raise ValueError('rebuild work directory must be fresh')
    work_dir.mkdir(parents=True)
    download = work_dir / 'download'
    download.mkdir()
    gh('release', 'download', seed_release, '--repo', REPOSITORY, '--pattern', ASSET,
       '--pattern', ASSET + '.sha256', '--dir', str(download))
    verify_download(download / ASSET, seed_sha256)
    request = publish_release.release_request('v1', seed_sha256, revision, REPOSITORY, seed_release)
    verified = work_dir / 'verified-seed-release'
    manifest = publish_release.verify_download(request, download, verified)
    recovered = original_inventory(manifest['inventory'])
    original = work_dir / 'inventory-original.json'
    original.write_text(json.dumps(recovered, indent=2) + '\n')
    seed = work_dir / 'seed'
    extract_seed(verified / 'seeddata.tar', seed)
    # Reclaim obsolete outer/derived archives after all pinned bytes are verified.
    (download / ASSET).unlink()
    (verified / 'overlay-images.tar').unlink(missing_ok=True)
    (verified / 'seeddata.tar').unlink()
    engine = image_engine(executable)
    engine.call('image', 'load', '--input', str(verified / 'images.tar'))
    services = work_dir / 'inventory-services.json'
    final_inventory = work_dir / 'inventory-current-main.json'
    build_variants(original, services, executable, revision)
    inventory = build_api(services, root, revision, final_inventory, executable)
    if any(item['revision'] != revision for item in inventory['services'].values()):
        raise ValueError('every rebuilt service must use the exact current-main revision')
    overlay = work_dir / 'overlay-images.tar.gz'
    export(final_inventory, overlay, executable)
    output = work_dir / ASSET
    bundle.build_bundle(inventory, verified / 'images.tar', seed, output, overlay_images=overlay)
    checksum = bundle.digest_file(output)['sha256']
    checksum_file = work_dir / (ASSET + '.sha256')
    checksum_file.write_text(checksum + '  ' + ASSET + '\n')
    # Keep only reviewable final artifacts; the publisher runs on a fresh runner.
    overlay.unlink()
    notes = work_dir / 'release-notes.AI.md'
    notes.write_text('Real-data offline demo v1 rebuilt from current main `' + revision + '`.\n\n'
                     'Captured VPS base images and pinned public seed data are retained.\n'
                     'Seed release: `' + seed_release + '`, SHA256 `' + seed_sha256 + '`.\n'
                     'Bundle SHA256: `' + checksum + '`.\n\n'
                     'Application and browser checks are performed manually.\n')
    gh('release', 'create', tag, str(output), str(checksum_file), '--repo', REPOSITORY,
       '--target', revision, '--title', 'Offline real demo v1 — main ' + revision,
       '--notes-file', str(notes))
    result = dict(release_tag=tag, bundle_sha256=checksum, source_revision=revision, seed_release=seed_release, seed_sha256=seed_sha256)
    (work_dir / 'rebuild-result.json').write_text(json.dumps(result, indent=2) + '\n')
    github_output = os.environ.get('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a') as stream:
            stream.write('release_tag=' + tag + '\nbundle_sha256=' + checksum + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--engine', choices=['docker', 'podman'], default='docker')
    parser.add_argument('--seed-release', default=SEED_RELEASE)
    parser.add_argument('--seed-sha256', default=SEED_SHA256)
    args = parser.parse_args()
    print(json.dumps(rebuild(args.work_dir, args.revision, args.engine, args.seed_release, args.seed_sha256), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print('demo rebuild: ' + str(error), file=sys.stderr)
        sys.exit(1)
