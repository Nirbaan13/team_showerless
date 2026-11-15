"""Verify the public download-to-analysis path for the fixed Ceres diagnostic.

This is an integration check, not a new scientific case or a recovery gate.
It never downloads FITS to this client. Physical observations and processing
versions are bound; current enclosing cutout hashes are recorded separately.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request

from PIL import Image

BASE = os.environ.get('PROBE_HTTP', 'http://144.124.238.101').rstrip('/')
HERE = Path(__file__).resolve().parent
CASE = HERE.parents[1] / 'v4-ceres-diagnostic'
MODEL = 'c596f66fe073d669d7b1b8ae0bd5d5cf710910cf36f34ad04fc08bcd10ecdb35'


def request(path, body=None):
    if not path.startswith('/') or path.startswith('//'):
        raise ValueError('Only same-service relative paths are permitted')
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def wait(job, terminal, seconds):
    deadline = time.monotonic() + seconds
    while job['status'] not in terminal:
        if time.monotonic() >= deadline:
            raise TimeoutError('Bounded public job did not finish')
        time.sleep(1)
        job = request(job['status_url'])
    return job


def main():
    output = Path(os.environ.get('PROBE_OUTPUT', str(HERE / 'native-http-proof.json')))
    if output.exists():
        raise ValueError('A new proof destination is required')
    source = json.loads((CASE / 'request.json').read_text())
    reference = json.loads((CASE / 'cli/result.json').read_text())
    expected_hashes = {row['sha256'] for row in source['source']['observations']}
    expected_ids = {row['observation_id'] for row in source['source']['observations']}
    expected_versions = {row['physical_observation_id']: row['processing_version']
                         for row in reference['frames']}
    handoff_path = HERE.parents[2] / 'experiments/v4/data/known_objects/point-grid-0750/raw-handoff.json'
    handoff = json.loads(handoff_path.read_text())
    assert {row['obs_id'] for row in handoff['images']} == expected_ids
    mjd_origin = datetime(1858, 11, 17, tzinfo=timezone.utc)
    lower = mjd_origin + timedelta(days=min(row['t_min_mjd'] for row in handoff['images']))
    upper = mjd_origin + timedelta(days=max(row['t_max_mjd'] for row in handoff['images']))
    region = source['source']['region']
    query = {**region, 'detector_array': 2,
             'observed_after': lower.isoformat(), 'observed_before': upper.isoformat()}
    proof = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(), http_base=BASE,
                 query=query, selected_case_request_sha256=hashlib.sha256((CASE / 'request.json').read_bytes()).hexdigest(),
                 reference_cutout_sha256=sorted(expected_hashes), expected_processing_versions=expected_versions,
                 time_binding='Original exposure MJD bounds, not the acquisition group name',
                 byte_identity_required=False,
                 cutout_transport='Current API enclosing TAN rectangle plus archive padding; original diagnostic used size=.12deg',
                 status='STARTED',
                 scope='Public native download and fixed-model inference integration; no scientific promotion criterion')
    try:
        assert request('/api/analyses/models')['models'][0]['sha256'] == MODEL
        proof['revision'] = request('/version')['version']
        download = request('/api/observations/default?' + urllib.parse.urlencode(query))
        proof['download_id'] = download['id']
        download = wait(download, {'completed', 'completed_with_errors', 'failed'}, 420)
        proof['download_status'] = download['status']
        assert download['status'] == 'completed', download.get('errors')
        assert len(download['chunks']) == 4 and all(row['status'] == 'ready' for row in download['chunks'])
        analysis = request('/api/analyses/motion', {'download_id': download['id']})
        proof['analysis_id'] = analysis['id']
        analysis = wait(analysis, {'completed', 'failed'}, 180)
        proof['analysis_status'] = analysis['status']
        assert analysis['status'] == 'completed', analysis.get('error')
        result = analysis['result']
        proof['result'] = result
        assert result['model']['sha256'] == MODEL
        current_hashes = {frame['sha256'] for frame in result['frames']}
        assert len(current_hashes) == 4 and all(len(value) == 64 and
            all(char in '0123456789abcdef' for char in value) for value in current_hashes)
        assert {frame['physical_observation_id'] for frame in result['frames']} == expected_ids
        assert all(frame['observation_id'] == frame['physical_observation_id'] + ':D2'
                   for frame in result['frames'])
        assert all(frame['detector'] == 2 and frame['processing_version'] == expected_versions[frame['physical_observation_id']]
                   for frame in result['frames'])
        grid = result['provenance']['grid']
        assert all(abs(value - expected) < 1e-10 for value, expected in zip(
            grid['center_deg'], [region['right_ascension_deg'], region['declination_deg']]))
        assert all((frame['width'], frame['height']) == (59, 59) for frame in result['frames'])
        assert len(result['frames']) == 4
        resources = {frame[key] for frame in result['frames'] for key in ('image_url', 'difference_url')}
        for candidate in result['candidates']:
            resources.update(candidate[key] for key in ('moving_stack_url', 'stationary_stack_url'))
        for frame in result['frames']:
            if frame.get('bloom_url'):
                resources.add(frame['bloom_url'])
        verified = []
        for path in sorted(resources):
            assert path.startswith('/api/analyses/' + analysis['id'] + '/resources/')
            with urllib.request.urlopen(BASE + path, timeout=30) as response:
                assert response.headers.get_content_type() == 'image/png'
                raw = response.read()
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
            verified.append(dict(url=path, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
        proof.update(status='PASS', verified_pngs=verified, physical_observations_and_processing_versions_exact=True,
                     current_cutout_sha256=sorted(current_hashes), same_cutout_bytes_as_reference=current_hashes == expected_hashes,
                     no_motion_confirmation_claim=True)
    except Exception as error:
        proof.update(status='FAIL', error_type=type(error).__name__, message=str(error)[:2000])
        raise
    finally:
        proof['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(proof, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: proof[key] for key in ('status', 'revision', 'download_id', 'analysis_id',
                                                'physical_observations_and_processing_versions_exact')}))


if __name__ == '__main__':
    main()
