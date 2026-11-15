#!/usr/bin/env python3
"""Verify a pinned GitHub Release bundle and publish its installer to GHCR."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

# Import the checked-out verifier; never execute Python supplied by an asset.
SOURCE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('trusted_demo_bundle', SOURCE / 'bundle.py')
bundle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bundle)

REPOSITORY = 'Nirbaan13/team_showerless'
IMAGE = 'ghcr.io/nirbaan13/team-showerless-demo'
PROFILES = {'v1': 'v1-real', 'v2': 'v2-mocked-core'}


def release_request(version, checksum, revision, repository, release_tag=None):
    if version not in PROFILES:
        raise ValueError('version must be v1 or v2')
    if not re.fullmatch(r'[0-9a-f]{64}', checksum):
        raise ValueError('bundle checksum must be 64 lowercase hexadecimal characters')
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('revision must be an exact 40-character Git commit SHA')
    if repository.lower() != REPOSITORY.lower():
        raise ValueError('publication is restricted to ' + REPOSITORY)
    tag = release_tag or 'demo-' + version
    if tag != 'demo-' + version:
        raise ValueError('release tag must match demo-' + version)
    return dict(version=version, checksum=checksum, revision=revision,
                repository=REPOSITORY, release_tag=tag,
                asset='spaceapps-demo-' + version + '.tar.gz',
                tags=[IMAGE + ':' + version + '-' + revision, IMAGE + ':' + version])


def verify_download(request, download, destination):
    archive = download / request['asset']
    checksum_file = download / (request['asset'] + '.sha256')
    if checksum_file.stat().st_size > 4096:
        raise ValueError('oversized release checksum file')
    content = checksum_file.read_text().strip()
    # Accept sha256sum's text/binary formats, or a bare SHA256 digest.
    expected_line = re.fullmatch(r'([0-9a-f]{64})(?: [ *]' + re.escape(request['asset']) + r')?', content)
    if not expected_line or expected_line[1] != request['checksum']:
        raise ValueError('release checksum asset does not match the pinned bundle checksum')
    if bundle.digest_file(archive)['sha256'] != request['checksum']:
        raise ValueError('downloaded bundle checksum differs from the pinned checksum')
    manifest = bundle.unpack_bundle(archive, destination)
    if manifest['profile'] != PROFILES[request['version']]:
        raise ValueError(request['version'] + ' requires bundle profile ' + PROFILES[request['version']])
    overlay = destination / 'overlay-images.tar' if 'overlay-images.tar' in manifest['files'] else None
    bundle.validate_images(destination / 'images.tar', manifest['inventory'], overlay)
    return manifest


def publish(request, runner=subprocess.run, environment=None):
    # Validate again at the side-effect boundary, including programmatic callers.
    request = release_request(request['version'], request['checksum'], request['revision'],
                              request['repository'], request['release_tag'])
    environment = dict(os.environ if environment is None else environment)
    token = environment.get('GH_TOKEN') or environment.get('GITHUB_TOKEN')
    actor = environment.get('GITHUB_ACTOR', '')
    if not token or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*(?:\[bot\])?', actor):
        raise ValueError('a workflow token and GitHub actor are required')
    clean_env = {key: value for key, value in environment.items()
                 if key not in {'GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN'}}
    with tempfile.TemporaryDirectory(prefix='spaceapps-demo-publish-') as directory:
        root = Path(directory)
        docker_config = root / 'docker-config'
        docker_config.mkdir(mode=0o700)
        clean_env['DOCKER_CONFIG'] = str(docker_config)

        def call(argv, **kwargs):
            kwargs.setdefault('env', clean_env)
            kwargs.setdefault('check', True)
            return runner(argv, **kwargs)

        call(['docker', 'login', 'ghcr.io', '--username', actor, '--password-stdin'],
             input=token + '\n', text=True, capture_output=True)
        if request['version'] == 'v2':
            proof = call(['docker', 'manifest', 'inspect', IMAGE + ':v1'],
                         capture_output=True, text=True, check=False)
            if proof.returncode != 0:
                raise ValueError('v2 requires an already published and accessible GHCR v1 image')
        immutable = request['tags'][0]
        existing = call(['docker', 'manifest', 'inspect', immutable],
                        capture_output=True, text=True, check=False)
        if existing.returncode == 0:
            raise ValueError('immutable revision tag already exists: ' + immutable)
        if not any(marker in (existing.stderr or '').lower()
                   for marker in ('manifest unknown', 'no such manifest', 'name unknown')):
            raise ValueError('could not verify that the immutable revision tag is absent')
        download = root / 'download'
        download.mkdir()
        call(['gh', 'release', 'download', request['release_tag'], '--repo', request['repository'],
              '--pattern', request['asset'], '--pattern', request['asset'] + '.sha256',
              '--dir', str(download)], env={**clean_env, 'GH_TOKEN': token})
        manifest = verify_download(request, download, root / 'verified')
        context = root / 'context'
        context.mkdir()
        shutil.copyfile(SOURCE / 'bundle.py', context / 'bundle.py')
        os.link(download / request['asset'], context / 'bundle.tar.gz')
        command = ['docker', 'build', '--file', str(SOURCE / 'Dockerfile'),
                   '--label', 'org.opencontainers.image.source=https://github.com/' + request['repository'],
                   '--label', 'org.opencontainers.image.revision=' + request['revision'],
                   '--label', 'org.opencontainers.image.version=' + request['version'],
                   '--label', 'org.spaceapps.demo.bundle.sha256=' + request['checksum'],
                   '--label', 'org.spaceapps.demo.profile=' + manifest['profile']]
        for tag in request['tags']:
            command += ['--tag', tag]
        call([*command, str(context)])
        # Publish the immutable name first. The convenient version tag follows.
        for tag in request['tags']:
            call(['docker', 'push', tag])
        return dict(image=IMAGE, tags=request['tags'], revision=request['revision'],
                    release_tag=request['release_tag'], bundle_sha256=request['checksum'],
                    profile=manifest['profile'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True, choices=sorted(PROFILES))
    parser.add_argument('--bundle-sha256', required=True)
    parser.add_argument('--release-tag', default='')
    parser.add_argument('--metadata', type=Path)
    args = parser.parse_args()
    request = release_request(args.version, args.bundle_sha256, os.environ.get('GITHUB_SHA', ''),
                              os.environ.get('GITHUB_REPOSITORY', ''), args.release_tag)
    result = publish(request)
    text = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.metadata:
        args.metadata.write_text(text)
    print(text, end='')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as output:
            output.write('Published `' + result['profile'] + '` from release `' + result['release_tag'] + '`.\n\n')
            for tag in result['tags']:
                output.write('- `' + tag + '`\n')
            output.write('\nVerified bundle SHA256: `' + result['bundle_sha256'] + '`\n')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, bundle.tarfile.TarError) as error:
        print('demo publish: ' + str(error), file=sys.stderr)
        sys.exit(1)
