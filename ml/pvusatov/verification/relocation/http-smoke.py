import json
import os
from datetime import datetime, timezone
from pathlib import Path
import time
import urllib.error
import urllib.request

BASE = os.environ.get('PROBE_HTTP', 'http://127.0.0.1:18086')
SHA = 'dde04fc3996be19150c57ca0399a7de52d6e7b62b2b65731133159585a3580a9'


def request(path, body=None, expected=200):
    raw = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=raw, headers={'Content-Type': 'application/json'})
    try:
        response = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        data = response.read()
        assert response.status == expected, (path, response.status, data[:1000])
        return json.loads(data)


def wait(job):
    deadline = time.monotonic() + 120
    while job['status'] not in {'completed', 'failed'}:
        assert time.monotonic() < deadline, job
        time.sleep(.25)
        job = request(job['status_url'])
    return job


assert request('/health')['status'] == 'ok'
version = request('/version')['version']
spec = request('/openapi.json')
assert len(spec['paths']) >= 20
for path in ['/api/observations/meta', '/api/equipment', '/api/observationsDeep', '/api/analyses/motion']:
    assert path in spec['paths'], path
models = request('/api/analyses/models')['models']
assert models[0]['sha256'] == SHA and models[0]['model_id'] == 'spherex-track-rf-v2'
assert len(request('/api/analyses/presets')['presets']) == 4
started = time.monotonic()
positive_request = {'preset': 'comet-d6'}
if os.environ.get('PROBE_MIN_SNR'):
    positive_request['options'] = {'min_snr': float(os.environ['PROBE_MIN_SNR'])}
accepted = request('/api/analyses/motion', positive_request, 202)
with urllib.request.urlopen(BASE + accepted['events_url'], timeout=120) as response:
    events = response.read().decode()
assert 'event:' in events and 'completed' in events, events[-1000:]
job = wait(request(accepted['status_url']))
assert job['status'] == 'completed', job
result = job['result']
assert result['model']['sha256'] == SHA
assert len(result['frames']) == 4 and result['candidates']
assert any(c['score'] is not None for c in result['candidates'])
urls = {f[k] for f in result['frames'] for k in ['image_url', 'difference_url']}
urls.update(c[k] for c in result['candidates'] for k in ['moving_stack_url', 'stationary_stack_url'] if c.get(k))
resource_bytes = 0
for url in urls:
    assert url.startswith(f"/api/analyses/{job['id']}/resources/"), url
    with urllib.request.urlopen(BASE + url, timeout=15) as response:
        image = response.read()
        assert response.status == 200 and response.headers.get_content_type() == 'image/png'
        assert image.startswith(b'\x89PNG\r\n\x1a\n')
        resource_bytes += len(image)
assert request('/api/analyses/motion', positive_request, 202)['id'] == job['id']
empty = wait(request('/api/analyses/motion', {'preset': 'comet-d6', 'options': {'min_snr': 100}}, 202))
assert empty['status'] == 'completed' and not empty['result']['candidates'], empty
missing = request('/api/analyses/motion', {'download_id': 'missing-native-download'}, 404)
assert missing['code'] == 'not_found'
invalid = request('/api/analyses/motion', {'preset': 'comet-d6', 'options': {'max_peaks': 101}}, 422)
assert invalid['code'] == 'invalid_request'
from jsonschema import Draft202012Validator, FormatChecker
schema = {'$ref': '#/components/schemas/AnalysisResult', 'components': spec['components']}
Draft202012Validator(schema, format_checker=FormatChecker()).validate(result)
proof = dict(server_base=BASE, checked_at_utc=datetime.now(timezone.utc).isoformat(), positive_request=positive_request, revision=version, model_sha256=SHA, positive_job=job['id'], empty_job=empty['id'],
             frames=len(result['frames']), candidates=len(result['candidates']),
             verified_png_resources=len(urls), resource_bytes=resource_bytes,
             elapsed_seconds=time.monotonic()-started, sse_completed=True,
             deduplication_verified=True, schema_validated=True, result=result)
Path(os.environ.get('PROBE_OUTPUT',str(Path(__file__).with_name('http-proof.json')))).write_text(json.dumps(proof, indent=2))
print(json.dumps({k:v for k,v in proof.items() if k != 'result'}, indent=2))
