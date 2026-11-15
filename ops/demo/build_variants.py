#!/usr/bin/env python3
"""Build current-source real-only frontend/ML images over captured VPS bases."""
import argparse
import copy
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import tempfile

from bundle import Engine, normalize_image_id, validate_inventory, verify_loaded_image


def clean_environment(environment=None):
    return {key: value for key, value in (os.environ if environment is None else environment).items()
            if key not in {'GH_TOKEN', 'GITHUB_TOKEN', 'GH_ENTERPRISE_TOKEN', 'GITHUB_ENTERPRISE_TOKEN'}}


def image_engine(executable):
    def run(arguments, **kwargs):
        kwargs.setdefault('env', clean_environment())
        return subprocess.run(arguments, **kwargs)
    return Engine(executable, runner=run)


def source_revision(root, expected=None):
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('A full Git revision is required')
    expected = expected or os.environ.get('GITHUB_SHA')
    if expected and revision != expected:
        raise ValueError('Clean HEAD must equal the requested GitHub source revision')
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=root, text=True)
    if dirty.strip():
        raise ValueError('Commit source changes before building versioned demo images')
    return revision


def validate_built_revision(image, revision, environment_name):
    config = image.get('Config') or {}
    label = (config.get('Labels') or {}).get('org.opencontainers.image.revision')
    environment = dict(item.split('=', 1) for item in config.get('Env') or [] if '=' in item)
    if label != revision or environment.get(environment_name) != revision:
        raise ValueError(f'Built image revision mismatch: expected {revision}; label={label!r}, {environment_name}={environment.get(environment_name)!r}')


def runtime_copies(root, dockerfile, destination):
    """Copy every final-stage COPY input, preserving its Dockerfile instruction."""
    text = (root / dockerfile).read_text().replace('\\\n', ' ')
    lines = text.splitlines()
    final_stage = max(index for index, line in enumerate(lines) if re.match(r'^FROM\s', line, re.I))
    instructions = []
    for line in lines[final_stage + 1:]:
        if not re.match(r'^COPY\s', line, re.I) or '--from=' in line:
            continue
        tokens = shlex.split(line)
        sources = [token for token in tokens[1:-1] if not token.startswith('--')]
        if not sources:
            raise ValueError('Unsupported COPY instruction: ' + line)
        for relative in sources:
            path = PurePosixPath(relative)
            if path.is_absolute() or '..' in path.parts or any(character in relative for character in '*?['):
                raise ValueError('Unsafe or unsupported Dockerfile COPY input: ' + relative)
            source = root.joinpath(*path.parts)
            target = destination.joinpath(*path.parts)
            if source.is_symlink() or not (source.is_file() or source.is_dir()):
                raise ValueError('COPY input must be a regular source file/directory: ' + relative)
            if source.is_dir():
                # These paths come from the repository's reviewed Dockerfiles.
                if any(item.is_symlink() for item in source.rglob('*')):
                    raise ValueError('Symlinks are forbidden in runtime source: ' + relative)
                shutil.copytree(source, target, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.pytest_cache'))
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        instructions.append(line)
    if not instructions:
        raise ValueError('Dockerfile has no final-stage runtime COPY inputs')
    return '\n'.join(instructions) + '\n'


def base_image(engine, original):
    actual = engine.json('image', 'inspect', original['image'])[0]
    verify_loaded_image(engine, original, actual)
    reference = original['image']
    if not re.fullmatch(r'[A-Za-z0-9_./:@-]+', reference):
        raise ValueError('Unsafe captured source image reference')
    return reference


def metadata(base, original, revision):
    return (f'FROM {base}\n'
            f'LABEL org.opencontainers.image.revision="{revision}" '
            'org.opencontainers.image.source="https://github.com/Nirbaan13/team_showerless" '
            'org.spaceapps.demo.profile="v1-real" '
            f'org.spaceapps.demo.parent_image="{original["image_id"]}"\n')


def build_image(engine, executable, stage, tag):
    arguments = ['build', '--pull=never', '--format', 'docker'] if executable == 'podman' else ['build', '--pull=false']
    engine.call(*arguments, '--file', str(stage / 'Dockerfile'), '--tag', tag, str(stage))


def image_record(image, tag, original, revision, environment_name):
    validate_built_revision(image, revision, environment_name)
    record = dict(image=tag, image_id=normalize_image_id(image['Id']), revision=revision,
                  os=image['Os'], architecture=image['Architecture'], parent_image_id=original['image_id'],
                  demo_profile='v1-real', derived_from_deployed_image=True)
    if image.get('Variant'):
        record['variant'] = image['Variant']
    return record


def build(inventory_path, output, executable='docker', expected_revision=None):
    root = Path(__file__).resolve().parents[2]
    inventory = validate_inventory(json.loads(Path(inventory_path).read_text()))
    revision = source_revision(root, expected_revision)
    engine = image_engine(executable)
    result = copy.deepcopy(inventory)
    result['demo_profile'] = 'v1-real'
    result['service_source_revision'] = revision
    environment = dict(clean_environment(), VITE_DEMO_REAL_ONLY='true', VITE_BACKEND_URL='/backend')
    subprocess.run(['npm', 'run', 'build'], cwd=root / 'frontend', env=environment, check=True)
    for name, kind in [('frontend', 'frontend'), ('ml-inference', 'ml')]:
        original = inventory['services'][name]
        reference = base_image(engine, original)
        tag = 'localhost/spaceapps-demo-' + kind + '-real:' + revision
        with tempfile.TemporaryDirectory(prefix='spaceapps-current-source-') as directory:
            stage = Path(directory)
            common = metadata(reference, original, revision)
            if kind == 'frontend':
                shutil.copytree(root / 'frontend/dist', stage / 'dist')
                (stage / 'dist/demo-mode.json').write_text(json.dumps(dict(profile='v1-real', real_only=True, revision=revision, parent_image_id=original['image_id'])) + '\n')
                (stage / 'dist/frontend-version.json').write_text(json.dumps({'version': revision}) + '\n')
                dockerfile = common + f'ENV FRONTEND_REVISION={revision}\nUSER root\nRUN rm -rf /usr/share/nginx/html/*\nCOPY dist/ /usr/share/nginx/html/\n'
            else:
                copies = runtime_copies(root, Path('ml/Dockerfile'), stage)
                dockerfile = common + f'USER root\nWORKDIR /app\nENV APP_REVISION={revision} DEMO_REAL_ONLY=1\n' + copies + 'USER app\n'
            (stage / 'Dockerfile').write_text(dockerfile)
            build_image(engine, executable, stage, tag)
        built = engine.json('image', 'inspect', tag)[0]
        result['services'][name] = image_record(built, tag, original, revision, 'FRONTEND_REVISION' if kind == 'frontend' else 'APP_REVISION')
    Path(output).write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--revision')
    parser.add_argument('--engine', choices=['docker', 'podman'], default='docker')
    args = parser.parse_args()
    build(args.inventory, args.output, args.engine, args.revision)
