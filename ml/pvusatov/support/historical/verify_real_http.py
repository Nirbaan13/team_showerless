"""Exercise managed archive→preparation→Ivan HTTP using real historical products.

This client performs no detection, ranking, training or source injection. Known
positions select fields only; separate post-result astrometry audits recovery.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

CASES = {
    'wise0855': dict(center=[133.795125, -7.245139], tile='1342m076'),
    'accident': dict(center=[233.623958, -10.717583], tile='2338m107'),
}
EPOCHS = [0, 1, 4, 8, 12, 15, 21, 22]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:18200')
    parser.add_argument('--case', choices=CASES, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    case = CASES[args.case]
    calls = []

    def request(path, body=None, *, label=None, timeout=180):
        url = args.base_url.rstrip('/') + path
        payload = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=payload,
                                     headers={'Content-Type': 'application/json'})
        try:
            response = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            status = response.status
        if label:
            (args.output / (label + '.json')).write_bytes(raw)
        calls.append(dict(method=req.get_method(), path=path, status=status,
                          response_bytes=len(raw), response_sha256=sha(raw),
                          request=body, raw_response=label + '.json' if label else None))
        (args.output / 'http-calls.json').write_text(json.dumps(calls, indent=2)+'\n')
        assert 200 <= status < 300, (path, status, raw[:1000])
        return json.loads(raw)

    def wait(path, label, timeout=600):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = request(path)
            if result['status'] in {'completed', 'completed_with_errors', 'failed', 'partial'}:
                (args.output / (label+'.json')).write_text(json.dumps(result, indent=2)+'\n')
                assert result['status'] == 'completed', result
                return result
            time.sleep(1)
        raise TimeoutError(path)

    query = urllib.parse.urlencode(dict(right_ascension_deg=case['center'][0],
        declination_deg=case['center'][1], radius_degrees=.01, providers='unwise-neo11',
        product_kinds='image', observed_after='2010-01-01T00:00:00Z',
        observed_before='2025-01-01T00:00:00Z', limit_per_provider=99))
    found = request('/api/observations-search?'+query, label='discovery')
    assert len(found['outcomes']) == 1 and found['outcomes'][0]['status'] == 'success', found['outcomes']
    selected = [r for r in found['observations'] if r.get('native', {}).get('coadd_id') == case['tile']
                and int(r['native']['epoch']) in EPOCHS]
    assert sorted(int(r['native']['epoch']) for r in selected) == EPOCHS, 'Fixed real epochs missing'
    (args.output/'selection.json').write_text(json.dumps(dict(case=args.case, epochs=EPOCHS,
        observations=selected, detector_profile='stellar_proper_motion', synthetic_sources=False,
        known_trajectory_sent_to_inference=False), indent=2)+'\n')
    print(json.dumps(dict(stage='discovered', case=args.case, observations=len(selected))), flush=True)
    accepted = request('/api/observations-download',
        dict(observation_ids=[r['id'] for r in selected], delivery={'mode': 'original'}), label='download-accepted')
    downloaded = wait(accepted['status_url'], 'download-completed')
    assets = downloaded['assets']
    assert len(assets) == 4*len(EPOCHS) and all(a['status'] == 'ready' for a in assets)
    science = [a for a in assets if a['provenance']['asset_role'] == '#this']
    assert len(science) == len(EPOCHS)
    total = sum(a['asset']['bytes'] for a in assets)
    assert total <= 256*1024**2, ('Selected real input exceeds preparation bound', total)
    print(json.dumps(dict(stage='downloaded', assets=len(assets), bytes=total)), flush=True)
    prepared = request('/api/image-unifications', dict(inputs=[dict(kind='archive_asset', id=a['asset']['id'])
        for a in science], grid=dict(kind='sky', width=128, height=128,
        ra_degrees=case['center'][0], dec_degrees=case['center'][1], pixel_scale_arcsec=2.75),
        options=dict(normalization='none', mask_policy='science')), label='unification-accepted')
    completed = wait(prepared['status_url'], 'unification-completed')
    review = request('/api/motion/search', dict(unification_id=completed['id'],
        profile='stellar_proper_motion'), label='ivan-review', timeout=180)
    assert review['has_ephemeris'] is False and review['target'] is None
    assert review['simulated_training_fields'] is None and review['detector'] is None
    assert len(review['frames']) == len(EPOCHS) and review['profile'] == 'stellar_proper_motion'
    assert review['comparison']['outliers_masked'] is None
    dates = sorted(f['time'] for f in review['frames'])
    assert dates[0].startswith('2010-') and dates[-1].startswith('2024-'), dates
    from PIL import Image
    import base64
    images = [f[k] for f in review['frames'] for k in ('aligned', 'residual')]
    images += [t[k] for t in review['tracks'] for k in ('fixed_stack', 'motion_stack')]
    for uri in images:
        assert uri.startswith('data:image/png;base64,')
        with Image.open(io.BytesIO(base64.b64decode(uri.split(',', 1)[1]))) as image:
            image.verify()
    proof = dict(status='HTTP_RUNTIME_COMPLETE', case=args.case, unification_id=completed['id'],
        epochs=EPOCHS, dates_utc=dates, raw_asset_bytes=total, raw_assets=len(assets),
        tracks=len(review['tracks']), decoded_pngs=len(images), natural_object_recovery='separate post-inference audit',
        backend_base=args.base_url, model_training=False, synthetic_source_acceptance=False,
        review_sha256=sha((args.output/'ivan-review.json').read_bytes()))
    (args.output/'runtime-proof.json').write_text(json.dumps(proof, indent=2)+'\n')
    print(json.dumps(proof), flush=True)


if __name__ == '__main__':
    main()
