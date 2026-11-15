#!/usr/bin/env python3
"""Build and install a checksummed, offline snapshot using the host container engine."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

SERVICES = {'frontend', 'api', 'pipeline', 'ml-inference'}
PAYLOADS = {'bundle.py', 'run.sh', 'compose.yaml', 'nginx.conf', 'images.tar', 'seeddata.tar'}
OPTIONAL_PAYLOADS = {'overlay-images.tar'}
SEED_ROOTS = {'api-data', 'ml-data'}


def digest_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'sha256': digest.hexdigest(), 'size': Path(path).stat().st_size}


def safe_member(member):
    path = PurePosixPath(member.name)
    if path.is_absolute() or '..' in path.parts or not path.parts or '\\' in member.name:
        raise ValueError('unsafe archive path: ' + member.name)
    if not (member.isfile() or member.isdir()):
        raise ValueError('archive links and special files are forbidden: ' + member.name)
    return path


def archive_members(archive):
    result = {}
    for member in archive:
        safe_member(member)
        if member.name in result:
            raise ValueError('duplicate archive path: ' + member.name)
        result[member.name] = member
    return result


def small_json(archive, member):
    if member.size > 8 * 1024 * 1024:
        raise ValueError('oversized JSON manifest')
    return json.load(archive.extractfile(member))


def validate_inventory(inventory):
    services = inventory.get('services', {})
    if set(services) != SERVICES:
        raise ValueError('inventory requires exactly frontend, api, pipeline, ml-inference; missing: ' + ', '.join(sorted(SERVICES - set(services))))
    sources = inventory.get('source_images', [])
    if not isinstance(sources, list) or not all(isinstance(item, dict) for item in sources):
        raise ValueError('source_images must be an array of source image records')
    for name, image in [*services.items(), *[('source image ' + str(n), item) for n, item in enumerate(sources)]]:
        for key in ('image', 'image_id', 'revision', 'os', 'architecture'):
            if not isinstance(image.get(key), str) or not image[key]:
                raise ValueError(name + ': missing ' + key)
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', image['image_id']):
            raise ValueError(name + ': expected exact sha256 image ID')
        if not re.fullmatch(r'[0-9a-f]{40}', image['revision']):
            raise ValueError(name + ': expected exact 40-character source revision')
        if image['os'] != 'linux' or not re.fullmatch(r'[a-z0-9_]+', image['architecture']):
            raise ValueError(name + ': unsupported image platform')
    if services['api']['image_id'] != services['pipeline']['image_id']:
        raise ValueError('pipeline must use the exact deployed API image')
    return inventory


def normalize_image_id(value):
    if re.fullmatch(r'[0-9a-f]{64}', value):
        value = 'sha256:' + value
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', value):
        raise ValueError('invalid immutable image ID: ' + value)
    return value


def canonical_tag(value):
    if value.startswith('docker.io/library/'):
        return value[len('docker.io/library/'):]
    if value.startswith('docker.io/'):
        return value[len('docker.io/'):]
    return value


def validate_images(path, inventory, overlay_path=None):
    """Verify classic Docker-save IDs or OCI manifest -> config hash chains.

    Scan once, including compressed exports, hashing all payloads without keeping
    layers in memory. Docker 29 may report the manifest ID; Podman reports the
    linked config ID. Both remain recorded and individually verified.
    """
    members, documents, hashes = {}, {}, {}
    legacy_records, oci_descriptors = [], []
    for archive_path in [path] + ([overlay_path] if overlay_path is not None else []):
        seen = set()
        with tarfile.open(archive_path, 'r|*') as archive:
            for member in archive:
                safe_member(member)
                if member.name in seen:
                    raise ValueError('duplicate image archive path: ' + member.name)
                seen.add(member.name)
                if not member.isfile():
                    members.setdefault(member.name, member)
                    continue
                digest = hashlib.sha256()
                capture = member.size <= 8 * 1024 * 1024
                chunks = []
                with archive.extractfile(member) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(chunk)
                        if capture:
                            chunks.append(chunk)
                identity = 'sha256:' + digest.hexdigest()
                metadata = member.name in {'manifest.json', 'index.json', 'oci-layout', 'repositories'}
                if member.name in hashes and hashes[member.name] != identity and not metadata:
                    raise ValueError('conflicting image payload across archives: ' + member.name)
                hashes[member.name] = identity
                members[member.name] = member
                if member.name.startswith('blobs/sha256/') and identity != 'sha256:' + member.name.split('/')[-1]:
                    raise ValueError('OCI blob digest mismatch: ' + member.name)
                if capture:
                    try:
                        document = json.loads(b''.join(chunks))
                        documents[member.name] = document
                        if member.name == 'manifest.json':
                            legacy_records.extend(document)
                        elif member.name == 'index.json':
                            oci_descriptors.extend(document.get('manifests', []))
                    except (ValueError, UnicodeDecodeError):
                        pass

    def descriptor_document(descriptor):
        identity = normalize_image_id(descriptor['digest'])
        name = 'blobs/sha256/' + identity.split(':')[1]
        if name not in documents or hashes[name] != identity or members[name].size != descriptor['size']:
            raise ValueError('OCI descriptor digest/size/config link mismatch: ' + name)
        return documents[name], identity, name

    configs, config_tags = {}, {}
    for record in legacy_records:
        name = record['Config']
        if name not in documents:
            raise ValueError('missing saved image config: ' + name)
        identity = hashes[name]
        configs[identity] = documents[name]
        config_tags.setdefault(identity, set()).update(canonical_tag(tag) for tag in record.get('RepoTags') or [])
        for layer in record.get('Layers', []):
            if layer not in members:
                raise ValueError('missing saved image layer: ' + layer)

    oci_manifests = {}
    for descriptor in oci_descriptors:
        document, identity, _ = descriptor_document(descriptor)
        if 'config' not in document:
            raise ValueError('OCI image indexes nested inside an export are unsupported; export the deployed platform')
        config, config_id, _ = descriptor_document(document['config'])
        configs[config_id] = config
        annotations = descriptor.get('annotations') or {}
        tag = annotations.get('io.containerd.image.name') or annotations.get('org.opencontainers.image.ref.name', '')
        tags = {canonical_tag(tag)}
        for layer in document.get('layers', []):
            layer_id = normalize_image_id(layer['digest'])
            name = 'blobs/sha256/' + layer_id.split(':')[1]
            if name not in members or hashes.get(name) != layer_id or members[name].size != layer['size']:
                raise ValueError('OCI manifest layer digest/size mismatch: ' + name)
        oci_manifests[identity] = (config_id, tags)
        config_tags.setdefault(config_id, set()).update(tags)

    tag_bindings = {}
    for config_id, tags in config_tags.items():
        for tag in tags:
            if tag in tag_bindings and tag_bindings[tag] != config_id:
                raise ValueError('image tag conflicts across source and overlay archives: ' + tag)
            tag_bindings[tag] = config_id

    expected_images = [*inventory['services'].items(), *[('source image ' + str(n), item) for n, item in enumerate(inventory.get('source_images', []))]]
    for name, expected in expected_images:
        identity = expected['image_id']
        if identity in oci_manifests:
            config_id, tags = oci_manifests[identity]
            if canonical_tag(expected['image']) not in tags:
                raise ValueError(name + ': source OCI manifest is linked to a different image tag')
        elif identity in configs:
            config_id = identity
        else:
            raise ValueError(name + ': exact image digest is missing from images archive')
        if canonical_tag(expected['image']) not in config_tags.get(config_id, set()):
            raise ValueError(name + ': deployed image tag is missing from images archive')
        config = configs[config_id]
        if config.get('architecture') != expected['architecture'] or config.get('os') != expected['os']:
            raise ValueError(name + ': saved image platform differs from source inventory')
        revision = (config.get('config', {}).get('Labels') or {}).get('org.opencontainers.image.revision')
        if revision != expected['revision']:
            raise ValueError(name + ': saved image revision differs from source inventory')
        expected['archive_config_id'] = config_id
        expected['archive_rootfs'] = config.get('rootfs', {}).get('diff_ids', [])
    return inventory


def validate_loaded_image(expected, actual):
    identity = normalize_image_id(actual['Id'])
    if identity not in {expected['image_id'], expected['archive_config_id']}:
        raise ValueError('loaded image ID differs from source manifest and verified config digest')
    if actual['Architecture'] != expected['architecture'] or actual['Os'] != expected['os']:
        raise ValueError('loaded image platform differs from release inventory')
    revision = (actual.get('Config', {}).get('Labels') or {}).get('org.opencontainers.image.revision')
    if revision != expected['revision']:
        raise ValueError('loaded image revision differs from release inventory')
    layers = actual.get('RootFS', {}).get('Layers', [])
    if layers != expected['archive_rootfs']:
        raise ValueError('loaded image root filesystem layers differ from verified image config')
    return identity


def build_bundle(inventory, images, seed_data, output, overlay_images=None):
    inventory = validate_inventory(inventory)
    images, seed_data, output = Path(images), Path(seed_data), Path(output)
    validate_images(images, inventory, overlay_images)
    entries = sorted(seed_data.rglob('*'))
    for entry in entries:
        relative = entry.relative_to(seed_data)
        if entry.name == '.env' or entry.name.startswith('.env.') or entry.suffix in {'.key', '.pem', '.p12'} or entry.name in {'id_rsa', 'id_ed25519'}:
            raise ValueError('secret/environment files are forbidden in seed: ' + str(relative))
        if relative.parts[0] not in SEED_ROOTS and not (len(relative.parts) == 1 and entry.suffix == '.json' and entry.name != '.env.json'):
            raise ValueError('seed root is outside allowlist: ' + str(relative))
        if entry.is_symlink() or not (entry.is_file() or entry.is_dir()):
            raise ValueError('seed links and special files are forbidden: ' + str(relative))
    if not all((seed_data / root).is_dir() for root in SEED_ROOTS):
        raise ValueError('seed requires api-data/ and ml-data/ directories')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='spaceapps-bundle-') as directory:
        stage = Path(directory)
        with tarfile.open(stage / 'seeddata.tar', 'w') as archive:
            for entry in entries:
                archive.add(entry, arcname=entry.relative_to(seed_data).as_posix(), recursive=False)
        source = Path(__file__).resolve().parent
        files = {name: source / name for name in PAYLOADS - {'images.tar', 'seeddata.tar'}}
        files.update({'images.tar': images, 'seeddata.tar': stage / 'seeddata.tar'})
        if overlay_images is not None:
            files['overlay-images.tar'] = Path(overlay_images)
        manifest = {'schema_version': 1, 'profile': 'v1-real', 'inventory': inventory,
                    'files': {name: digest_file(path) for name, path in sorted(files.items())}}
        manifest_path = stage / 'manifest.json'
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        pending = output.with_name(output.name + '.partial')
        try:
            with tarfile.open(pending, 'w:gz', compresslevel=1) if str(output).endswith(('.gz', '.tgz')) else tarfile.open(pending, 'w') as archive:
                for name, path in sorted(files.items()):
                    archive.add(path, arcname=name, recursive=False)
                archive.add(manifest_path, arcname='manifest.json', recursive=False)
            pending.replace(output)
        finally:
            pending.unlink(missing_ok=True)
    return manifest


def verify_directory(directory):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text())
    validate_manifest(manifest)
    for name, expected in manifest['files'].items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or digest_file(path) != expected:
            raise ValueError('checksum or size mismatch: ' + name)
    return manifest


def validate_manifest(manifest):
    if manifest.get('schema_version') != 1 or manifest.get('profile') != 'v1-real':
        raise ValueError('unsupported demo manifest version/profile')
    if set(manifest.get('files', {})) not in [PAYLOADS, PAYLOADS | OPTIONAL_PAYLOADS]:
        raise ValueError('incomplete bundle file manifest')
    validate_inventory(manifest['inventory'])


def unpack_bundle(path, destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError('extraction destination already exists')
    with tarfile.open(path, 'r:*') as archive:
        members = archive_members(archive)
        if set(members) not in [PAYLOADS | {'manifest.json'}, PAYLOADS | OPTIONAL_PAYLOADS | {'manifest.json'}] or any(not m.isfile() for m in members.values()):
            raise ValueError('archive must contain exactly the release payload files and manifest.json')
        manifest = small_json(archive, members['manifest.json'])
        validate_manifest(manifest)
        if set(members) != set(manifest['files']) | {'manifest.json'}:
            raise ValueError('archive payloads do not match the checksummed manifest')
        for name, expected in manifest['files'].items():
            digest = hashlib.sha256()
            with archive.extractfile(members[name]) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            if digest.hexdigest() != expected['sha256'] or members[name].size != expected['size']:
                raise ValueError('checksum or size mismatch: ' + name)
        destination.mkdir(parents=True)
        for name, member in members.items():
            with archive.extractfile(member) as source, (destination / name).open('wb') as target:
                shutil.copyfileobj(source, target)
        (destination / 'run.sh').chmod(0o755)
    return manifest


def seed_directory(archive_path, target, prefix, identity, chown=True):
    """Hydrate a fresh isolated volume; repeat runs never replace user changes."""
    target = Path(target)
    marker = target / '.spaceapps-demo-seed'
    if marker.exists():
        if marker.read_text().strip() != identity:
            raise ValueError('existing volume contains a different demo seed; choose a new --project')
        return
    if any(target.iterdir()):
        raise ValueError('refusing to seed an existing nonempty volume')
    with tarfile.open(archive_path, 'r:*') as archive:
        members = archive_members(archive)
        for name, member in members.items():
            relative = PurePosixPath(name)
            if relative.parts[0] != prefix or len(relative.parts) == 1:
                continue
            output = target.joinpath(*relative.parts[1:])
            if member.isdir():
                output.mkdir(parents=True, exist_ok=True)
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, output.open('wb') as dest:
                    shutil.copyfileobj(source, dest)
    marker.write_text(identity + '\n')
    if chown:
        for path in [target, *target.rglob('*')]:
            os.chown(path, 10001, 10001)


class Engine:
    def __init__(self, executable, runner=subprocess.run):
        self.executable, self.runner = executable, runner

    def call(self, *arguments, **kwargs):
        kwargs.setdefault('check', True)
        return self.runner([self.executable, *arguments], **kwargs)

    def json(self, *arguments):
        return json.loads(self.call(*arguments, capture_output=True, text=True).stdout)


def choose_engine(name=None):
    names = [name] if name else ['docker', 'podman']
    for candidate in names:
        if shutil.which(candidate):
            engine = Engine(candidate)
            try:
                engine.call('info', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                engine.call('compose', 'version', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return engine
            except subprocess.CalledProcessError:
                pass
    raise ValueError('no accessible Docker/Podman engine with Compose; set DOCKER_HOST or --engine')


def validate_project(project):
    if not re.fullmatch(r'spaceapps-demo(?:-[a-z0-9][a-z0-9_-]*)?', project):
        raise ValueError('project must be spaceapps-demo or start with spaceapps-demo-')
    return project


def ensure_volume(engine, name, project):
    result = engine.call('volume', 'inspect', name, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        info = json.loads(result.stdout)[0]
        if (info.get('Labels') or {}).get('org.spaceapps.demo.project') != project:
            raise ValueError('existing volume is not owned by this demo project: ' + name)
    else:
        engine.call('volume', 'create', '--label', 'org.spaceapps.demo.project=' + project, name)


def seed_volume(engine, name, project, image, archive_path, prefix, identity):
    ensure_volume(engine, name, project)
    # The helper executes in the existing API image, with no network and no host paths.
    script = Path(__file__).read_text() + '\nimport tempfile\nwith tempfile.NamedTemporaryFile() as f:\n shutil.copyfileobj(sys.stdin.buffer, f); f.flush(); seed_directory(f.name, Path("/target"), sys.argv[1], sys.argv[2])\n'
    # Avoid the CLI main block when reusing the verified module in the helper.
    script = script.replace("if __name__ == '__main__':", "if False:")
    with open(archive_path, 'rb') as source:
        engine.call('run', '--rm', '-i', '--network', 'none', '--user', '0:0', '--entrypoint', 'python3',
                    '--volume', name + ':/target', image, '-c', script, prefix, identity, stdin=source)


def install(directory, engine, project, port, action='up', timeout=240):
    project = validate_project(project)
    if not 1024 <= port <= 65535:
        raise ValueError('port must be an unprivileged port between 1024 and 65535')
    directory = Path(directory)
    manifest = verify_directory(directory)
    inventory = manifest['inventory']['services']
    environment = os.environ.copy()
    environment.update({'DEMO_PROJECT': project, 'DEMO_PORT': str(port)})
    for service, variable in [('frontend', 'FRONTEND'), ('api', 'API'), ('ml-inference', 'ML')]:
        image = inventory[service]
        environment[variable + '_IMAGE'] = image.get('archive_config_id', image['image_id'])
        environment[variable + '_PLATFORM'] = image['os'] + '/' + image['architecture'] + ('/' + image['variant'] if image.get('variant') else '')
    command = ['compose', '--project-name', project, '--file', str(directory / 'compose.yaml')]
    if action == 'down':
        engine.call(*command, 'down', env=environment)
        print('Demo stopped; seed and user changes remain in its project volumes.')
        return
    engine.call('image', 'load', '--input', str(directory / 'images.tar'))
    if 'overlay-images.tar' in manifest['files']:
        engine.call('image', 'load', '--input', str(directory / 'overlay-images.tar'))
    runtime_ids = {}
    for expected in [*inventory.values(), *manifest['inventory'].get('source_images', [])]:
        actual = engine.json('image', 'inspect', expected['image'])[0]
        runtime_ids[expected['image']] = validate_loaded_image(expected, actual)
    for service, variable in [('frontend', 'FRONTEND'), ('api', 'API'), ('ml-inference', 'ML')]:
        environment[variable + '_IMAGE'] = runtime_ids[inventory[service]['image']]
    identity = manifest['files']['seeddata.tar']['sha256']
    for prefix in sorted(SEED_ROOTS):
        seed_volume(engine, project + '_' + prefix, project, runtime_ids[inventory['api']['image']], directory / 'seeddata.tar', prefix, identity)
    # A named config volume also works when this CLI is inside an installer image.
    with tempfile.NamedTemporaryFile(suffix='.tar') as runtime:
        with tarfile.open(fileobj=runtime, mode='w') as archive:
            archive.add(directory / 'nginx.conf', arcname='runtime-config/default.conf')
        runtime.flush()
        config_hash = manifest['files']['nginx.conf']['sha256']
        seed_volume(engine, project + '_runtime-config', project, runtime_ids[inventory['api']['image']], runtime.name, 'runtime-config', config_hash)
    engine.call(*command, 'up', '--detach', '--no-build', '--pull', 'never', '--wait', '--wait-timeout', str(timeout), env=environment)
    print('Demo ready: http://localhost:' + str(port) + '/')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build')
    build.add_argument('--inventory', type=Path, required=True)
    build.add_argument('--images', type=Path, required=True, help='Original Docker-save tar or compressed tar; copied unchanged to images.tar')
    build.add_argument('--overlay-images', type=Path, help='Optional Docker-save archive of derived demo images; source export stays unchanged')
    build.add_argument('--seed-data', type=Path, required=True)
    build.add_argument('--output', type=Path, required=True)
    extract = commands.add_parser('extract')
    extract.add_argument('--bundle', type=Path, required=True)
    extract.add_argument('--destination', type=Path, required=True)
    launch = commands.add_parser('install')
    launch.add_argument('--bundle', type=Path)
    launch.add_argument('--directory', type=Path, default=Path(__file__).resolve().parent)
    launch.add_argument('--engine', choices=['docker', 'podman'])
    launch.add_argument('--project', default='spaceapps-demo')
    launch.add_argument('--port', type=int, default=8080)
    launch.add_argument('--timeout', type=int, default=240)
    launch.add_argument('action', nargs='?', choices=['up', 'down'], default='up')
    args = parser.parse_args()
    if args.command == 'build':
        manifest = build_bundle(json.loads(args.inventory.read_text()), args.images, args.seed_data, args.output, overlay_images=args.overlay_images)
        print(json.dumps({'bundle': str(args.output), **digest_file(args.output), 'profile': manifest['profile']}))
    elif args.command == 'extract':
        unpack_bundle(args.bundle, args.destination)
    else:
        engine = choose_engine(args.engine)
        if args.bundle:
            with tempfile.TemporaryDirectory(prefix='spaceapps-demo-install-') as stage:
                directory = Path(stage) / 'release'
                unpack_bundle(args.bundle, directory)
                install(directory, engine, args.project, args.port, args.action, args.timeout)
        else:
            install(args.directory, engine, args.project, args.port, args.action, args.timeout)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, tarfile.TarError) as error:
        print('demo: ' + str(error), file=sys.stderr)
        sys.exit(1)
