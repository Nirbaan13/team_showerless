"""Verify native Scala processing, the separate ML registry, and retired image guards."""
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
    # Native capabilities describe the Scala service, while Nginx routes the
    # persisted registry/discussions to the separately deployed ML HTTP service.
    for path, expected_type, required_key in [
        ('/api/motion/verifications', list, None),
        ('/api/catalogue/kpis', dict, 'total_candidates'),
        ('/api/catalogue/candidates', dict, 'candidates'),
    ]:
        status, body = request(base, path)
        assert status == 200 and isinstance(body, expected_type), (path, status, body)
        if required_key is not None:
            assert required_key in body, (path, body)
        checked.append(dict(path=path, service='persistent_ml_registry', http_status=status))
    # Reconnecting registry operations must never reactivate generated images.
    for path in ['/api/motion/coadd/PX-000001/motion.png', '/api/motion/cutout/render']:
        status, body = request(base, path)
        assert status == 501 and body['code'] == 'unsupported_legacy_operation', (path, status, body)
        assert body['retryable'] is False
        assert body['motion_analysis_url'] == motion['endpoint']
        checked.append(dict(path=path, service='retired_image_operation', http_status=status))
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
