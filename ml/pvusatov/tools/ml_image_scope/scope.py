"""Check and stage the ML Dockerfile's explicit runtime files without Docker.

This intentionally accepts only simple file COPY instructions used by this
Dockerfile; it is not a general Docker build/context/layer simulator.
"""
import argparse
import ast
import json
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[4]
ASSETS = {
    'ml/requirements.txt', 'ml/service.py', 'ml/smoke_deployment.py',
    'ml/candidate-example.json', 'ml/spherex-result.png', 'ml/spherex_3i_atlas.npz',
    'ops/ml/compose.yaml',
    'science/motion/cases/december-d2.npz', 'science/motion/cases/december-d6.npz',
    'science/motion/cases/vesta-d3.npz', 'science/motion/cases/vesta-d6.npz',
    'science/motion/cases/observations.csv', 'science/motion/cases/vesta-horizons.csv',
}
MODULES = {'ml/service.py', 'ml/detector.py', 'ml/catalogue_db.py', 'ml/smoke_deployment.py',
           'science/archive_gateway.py',
           'science/motion/live.py', 'science/motion/prepare_fits.py', 'science/motion/review.py',
           'science/motion/detector.py', 'science/motion/ranker.py',
           'science/motion/prepared.py', 'science/motion/profiles.py', 'pipeline/unification/ml.py'}


def copy_files(root, *, dockerfile=None):
    """Map each exact COPY source file to its image path relative to /app."""
    text = (dockerfile or root / 'ml/Dockerfile').read_text().replace('\\\n', ' ')
    result = {}
    for line in text.splitlines():
        fields = shlex.split(line, comments=True)
        if not fields or fields[0].upper() != 'COPY':
            continue
        args = [field for field in fields[1:] if field == '--chown=app:app' or not field.startswith('--')]
        args = [field for field in args if field != '--chown=app:app']
        if len(args) < 2 or any(field.startswith('--') for field in fields[1:] if field != '--chown=app:app'):
            raise ValueError('unsupported COPY syntax')
        destination = PurePosixPath(args[-1])
        for source in args[:-1]:
            path = PurePosixPath(source)
            if (path.is_absolute() or '..' in path.parts or any(c in source for c in '*?[]')
                    or not (root / source).is_file() or (root / source).is_symlink()
                    or 'pvusatov' in path.parts or path.name.startswith('test')):
                raise ValueError(f'COPY must name an explicit runtime file: {source}')
            if source not in ASSETS | MODULES:
                raise ValueError(f'unexpected runtime source: {source}')
            target = destination / path.name if args[-1].endswith('/') else destination
            if target.is_absolute() or '..' in target.parts:
                raise ValueError('runtime destination escapes /app')
            if source in result or target.as_posix() in result.values():
                raise ValueError('duplicate COPY source/destination')
            result[source] = target.as_posix()
    return result


def validate_runtime(root, sources):
    """Require exercised runtime assets and the repository-local import closure."""
    missing = ASSETS - sources.keys()
    if missing:
        raise ValueError(f'missing runtime assets: {sorted(missing)}')
    for source, destination in sources.items():
        if not source.endswith('.py'):
            continue
        package = PurePosixPath(destination).parts[:-1]
        for node in ast.walk(ast.parse((root / source).read_text(), filename=source)):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                prefix = package[:len(package) - node.level + 1] if node.level else ()
                names = ['.'.join((*prefix, node.module or '')).rstrip('.')]
            else:
                continue
            for name in names:
                relative = name.replace('.', '/') + '.py'
                for candidate in (relative, 'ml/' + relative):
                    if (root / candidate).is_file() and candidate not in sources:
                        raise ValueError(f'missing local import {candidate} needed by {source}')


def validate_ignore(root, sources, *, ignore=None):
    """Only exact copied files may be excepted; parent rules admit descendants."""
    rules = [line.strip() for line in (ignore or root / 'ml/Dockerfile.dockerignore').read_text().splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    if not rules or rules[0] != '**' or any(not rule.startswith('!') for rule in rules[1:]):
        raise ValueError('context must deny everything before exact exceptions')
    if set(rule[1:] for rule in rules[1:]) != set(sources):
        raise ValueError('ignore exceptions must exactly match runtime files')


def stage_runtime(root, output):
    sources = copy_files(root)
    validate_runtime(root, sources)
    validate_ignore(root, sources)
    output.mkdir(parents=True, exist_ok=False)
    for source, destination in sources.items():
        target = output / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / source, target)
    return sources


def tracked_counts(root, sources, baseline):
    """Object metadata counts, not Docker context, compressed layer or image sizes."""
    tree = subprocess.check_output(['git', 'ls-tree', '-rl', baseline, '--', 'ml', 'science/motion',
                                    'ops/ml/compose.yaml'], cwd=root, text=True)
    sizes = {}
    for line in tree.splitlines():
        metadata, path = line.split('\t', 1)
        sizes[path] = int(metadata.split()[3])
    if any(source not in sizes for source in sources):
        raise ValueError('runtime COPY source was not tracked at the baseline revision')
    return dict(baseline=baseline, before_ml_tree_tracked_bytes=sum(size for path, size in sizes.items() if path.startswith('ml/')),
                after_ml_copy_tracked_bytes=sum(sizes[path] for path in sources if path.startswith('ml/')),
                before_all_copy_tracked_bytes=sum(sizes.values()),
                after_all_copy_tracked_bytes=sum(sizes[path] for path in sources), copied_files=len(sources))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, help='Create a new isolated /app directory')
    parser.add_argument('--baseline', default='HEAD', help='Git revision for tracked byte accounting')
    args = parser.parse_args()
    sources = stage_runtime(ROOT, args.stage) if args.stage else copy_files(ROOT)
    validate_runtime(ROOT, sources)
    validate_ignore(ROOT, sources)
    print(json.dumps(tracked_counts(ROOT, sources, args.baseline), sort_keys=True))


if __name__ == '__main__':
    main()
