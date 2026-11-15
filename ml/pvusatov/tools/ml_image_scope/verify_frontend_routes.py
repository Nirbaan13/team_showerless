"""Verify frontend API routing against the advertised Scala capabilities."""
import argparse
import json
import time
import urllib.error
import urllib.request


def request(base, path):
    try:
        response = urllib.request.urlopen(base.rstrip('/') + path, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.load(response)


def probe(base):
    status, capabilities = request(base, '/api/capabilities')
    assert status == 200, ('capabilities', status)
    assert capabilities['revision']
    assert capabilities['pipeline']['available'] is True
    discovery = capabilities['motion_models']
    assert isinstance(discovery, dict) and discovery.get('models'), 'Motion models are not ready'
    motion = capabilities['motion_analysis']
    assert motion['status'] == 'supported'
    assert motion['endpoint'] == '/api/analyses/motion'
    status, models = request(base, '/api/analyses/models')
    assert status == 200 and isinstance(models, dict) and models.get('models'), ('models', status)
    checked = []
    for path, feature in [
        ('/api/motion/verifications', 'legacy_motion_service'),
        ('/api/catalogue/kpis', 'community_catalogue'),
        ('/api/catalogue/candidates', 'community_catalogue'),
    ]:
        advertised = capabilities[feature]['status']
        assert advertised in {'supported', 'unsupported'}, (feature, advertised)
        status, body = request(base, path)
        expected = 501 if advertised == 'unsupported' else 200
        assert status == expected, (path, advertised, status)
        if expected == 501:
            assert body['code'] == 'unsupported_legacy_operation', (path, body)
            assert body['retryable'] is False
            assert body['motion_analysis_url'] == motion['endpoint']
        checked.append(dict(path=path, advertised=advertised, http_status=status))
    return dict(status='PASS', backend_revision=capabilities['revision'],
                installed_models=len(models['models']), routes=checked)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    args = parser.parse_args()
    for attempt in range(30):
        try:
            result = probe(args.base_url)
            print(json.dumps(result, sort_keys=True))
            return
        except (AssertionError, KeyError, ValueError, urllib.error.URLError, TimeoutError):
            if attempt == 29:
                raise
            time.sleep(2)


if __name__ == '__main__':
    main()
