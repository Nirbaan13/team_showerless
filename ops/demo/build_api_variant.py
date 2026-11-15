#!/usr/bin/env python3
"""Compile current HEAD and replace all API runtime/model files over its VPS base."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from bundle import Engine, validate_inventory
from build_variants import base_image, build_image, clean_environment, image_engine, image_record, metadata, runtime_copies, source_revision


def build(inventory_path, source, revision, output, executable='docker'):
    source = Path(source).resolve()
    source_revision(source, revision)
    environment = dict(clean_environment(), APP_REVISION=revision)
    subprocess.run(['./sbtw', 'stage'], cwd=source / 'backend', env=environment, check=True)
    inventory = validate_inventory(json.loads(Path(inventory_path).read_text()))
    current = inventory['services']['api']
    parent_id = current.get('parent_image_id', current['image_id'])
    original = next((item for item in inventory['source_images'] if item['image_id'] == parent_id), None)
    if original is None:
        raise ValueError('API must derive from a captured VPS source image')
    engine = image_engine(executable)
    reference = base_image(engine, original)
    tag = 'localhost/spaceapps-demo-api-real:' + revision
    with tempfile.TemporaryDirectory(prefix='spaceapps-current-api-') as directory:
        stage = Path(directory)
        shutil.copytree(source / 'backend/target/stage', stage / 'stage')
        copies = runtime_copies(source, Path('backend/Dockerfile'), stage)
        dockerfile = metadata(reference, original, revision) + (
            f'USER root\nWORKDIR /app\nENV APP_REVISION={revision} IRSA_CUTOUT_SCRIPT=/app/backend/python/irsa_cutout.py\n'
            'RUN rm -rf /app/classes /app/lib /app/pipeline /app/inference\n'
            'COPY --chown=10001:10001 stage/ /app/\n') + copies + 'USER app\n'
        (stage / 'Dockerfile').write_text(dockerfile)
        build_image(engine, executable, stage, tag)
    actual = engine.json('image', 'inspect', tag)[0]
    record = image_record(actual, tag, original, revision, 'APP_REVISION')
    record['compiled_tree'] = subprocess.check_output(['git', 'rev-parse', revision + '^{tree}'], cwd=source, text=True).strip()
    inventory['services']['api'] = record
    inventory['services']['pipeline'] = copy.deepcopy(record)
    inventory['api_source_revision'] = revision
    Path(output).write_text(json.dumps(inventory, indent=2) + '\n')
    return inventory


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', required=True, type=Path)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--engine', choices=['docker', 'podman'], default='docker')
    args = parser.parse_args()
    build(args.inventory, args.source, args.revision, args.output, args.engine)
