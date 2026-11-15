"""Create a root research release from the independently reviewed acquisition.

Only bytes/JSON/source are read here; no native pixels, injections or scorer.
"""
from datetime import datetime, timezone
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
SOURCE = BASE.parent / 'data/association_holdout/recovery-6/guarded-resource-handoff.json'
SOURCE_SHA = 'd79f08a5d56216a111ccfd549beb67c48b7d71f326f42d13e8a425145bc8da37'
FREEZE_SHA = 'ae981b56f43c8a14cd6dee9ce61c48853ea7c90b63eca8ddcf586e0a3e3dbbdd'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()


def main():
    output = HERE / 'handoff.json'
    if output.exists():
        raise ValueError('Root release already exists')
    assert digest(SOURCE) == SOURCE_SHA
    source = json.loads(SOURCE.read_text())
    assert source['evaluation_ready'] and not source['inference_authorized']
    assert not source['pixels_opened'] and not source['models_called']
    verified = {}
    def refs(value):
        if isinstance(value, dict):
            if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
                path, expected = Path(value['path']), value['sha256']
                key = str(path.resolve())
                if key in verified:
                    assert verified[key] == expected
                else:
                    assert digest(path) == expected, key
                    verified[key] = expected
            for item in value.values(): refs(item)
        elif isinstance(value, list):
            for item in value: refs(item)
    refs(source)
    guard = json.loads(Path(source['strict_guard_ref']['path']).read_text())
    assert guard['strict_native_ready'] and guard['status'] == 'PASS_READY_QUARANTINE'
    assert len(source['groups']) == 12
    images = [row for group in source['groups'] for row in group['images']]
    assert len(images) == len({row['obs_id'] for row in images}) == 96
    assert sum(row['bytes'] for row in images) == 499412160
    assert not {row['obs_id'] for row in images} & set(source['excluded_physical_obsids'])
    full = [row for row in images if row['bytes'] > 5200000]
    assert len(full) == 2 and all(row['bytes'] <= 64 * 1024**2 for row in full)
    released = copy.deepcopy(source)
    for group in released['groups']:
        for row in group['images']:
            transfer = row['source_url']
            url = urlsplit(transfer)
            assert url.scheme == 'https' and url.hostname == 'irsa.ipac.caltech.edu' and not url.username
            assert url.path.startswith('/ibe/data/spherex/dr1/level2/') and not url.fragment
            version = re.search(r'/(l2b(?:_retry)?-v[0-9]+-[0-9]{4}-[0-9]{3})/', url.path)
            assert version
            row['transfer_url'] = transfer
            row['access_url'] = urlunsplit((url.scheme, url.netloc, url.path, '', ''))
            row['release'] = 'dr1'
            row['processing_version'] = version.group(1)
            row['input_transport'] = 'full_mef' if row['bytes'] > 5200000 else 'server_cutout'
    frozen_path = BASE / 'engineering-repair-1/freeze.json'
    assert digest(frozen_path) == FREEZE_SHA
    spec = importlib.util.spec_from_file_location('root_native_freeze', BASE / 'freeze.py')
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    frozen = validator.validate(frozen_path, FREEZE_SHA)
    runner = validator.exact('root_native_release_preflight', frozen['sources']['runner'])
    groups = runner.released_groups(frozen, released, validator)
    assert len(groups) == 12
    released.update(created_utc=datetime.now(timezone.utc).isoformat(), status='ROOT_RELEASED_FIXED_RESEARCH',
                    inference_authorized=True, injections_authorized=True)
    released['root_authorization'] = dict(source_receipt=dict(path=str(SOURCE.resolve()), sha256=SOURCE_SHA),
        freeze_sha256=FREEZE_SHA, authorizer='root', production_promotion_authorized=False,
        policy='Fixed learned_pair versus legacy; both frozen C596; no refit or threshold change',
        independent_review='Read-only explorer checked247references,96actual hashes,originalcohort/seeds/exclusions andall12metadata selections',
        native_pixels_or_scores_opened_before_release=False,
        amendments_disclosed='Geometry-prefilter ordering and finite-time validity after synthetic unblinding but before native scientific reads',
        mixed_transport='94servercutouts+2same-artifactfullMEFs; no exact preparation parity claim; bothpolicies shareallinputs',
        requires_before_inference='Commit and push handoff, source and authorization, then explicit --authorize-native')
    output.write_text(json.dumps(released, indent=2, allow_nan=False) + '\n')
    proof = dict(created_utc=released['created_utc'], source_sha256=digest(__file__),
        acquisition_receipt_sha256=SOURCE_SHA, handoff_sha256=digest(output), freeze_sha256=FREEZE_SHA,
        independently_rehashed_reference_paths=len(verified), parents=12, exposures=96, bytes=499412160,
        frozen_released_groups_preflight_passed=True, native_prepare_or_model_executed=False)
    (HERE / 'authorization.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()
