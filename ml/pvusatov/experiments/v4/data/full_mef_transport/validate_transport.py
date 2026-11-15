"""Single predeclared old-TRAIN transport check; never runs a detector/model."""
from pathlib import Path
import copy
import hashlib
import json
import os
import resource
import sys
import time
import urllib.request
from urllib.parse import urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
PROTOCOL = ROOT / 'ml/pvusatov/experiments/v4/association_pilot/protocol.json'
RUNTIME = ROOT / 'ml/pvusatov/releases/v4/runtime'
FULL = Path('/tmp/spaceapps-full-mef-transport-old-train01/level2_2026W07_2A_0437_1D1_spx_l2b-v27-2026-226.fits')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def info():
    return json.loads(PROTOCOL.read_text())['native']['v4-train01']


def protected():
    paths = [PROTOCOL, *sorted((RUNTIME / 'ml_inference').glob('*.py'))]
    paths += sorted((ROOT / 'ml/pvusatov/releases/v4/model').glob('*'))
    paths += [Path(r['path']) for r in info()['input_sources']]
    return {str(p): sha(p) for p in paths if p.is_file()}


def freeze():
    p = info()
    r = p['input_sources'][0]
    u = urlsplit(r['url'])
    assert all(sha(row['path']) == row['sha256'] for row in p['input_sources'])
    assert sha(RUNTIME / 'ml_inference/prepare.py') == '27ef087aa19f394eaf16ee19c0801ed6c7557a79a7ea77b3410445363f4624ec'
    plan = dict(
        purpose='Scientific engineering transport validation only; no labels, scoring, fitting, new-native or holdout reads',
        case='v4-train01 preexisting first input_sources entry; selection independent of values/results',
        selected_source=r, packet_sources=p['input_sources'], center_deg=p['center_deg'],
        full_url=urlunsplit((u.scheme, u.netloc, u.path, '', '')),
        full_local_path=str(FULL), options=p['preparation_options'],
        roi_arcmin=[6., 6.], packet_size=8,
        intervention='Replace only first path/access_url/SHA with same full artifact; physical/frame identity unchanged',
        limits=dict(max_full_bytes=64*1024*1024, max_total_received_body_bytes=70*1024*1024,
                    max_get_attempts=2, timeout_seconds_per_attempt=90, backoff_seconds=5,
                    max_cpu_threads=2, max_address_space_bytes=2*1024**3, max_wall_seconds=1200),
        criteria='Report every actual numerical difference and finite/NaN/quality-mask difference; input size/SHA differences expected, excluded from parity criteria',
        expected_times_hours=p['times_hours'], expected_shape=p['registered_shape'],
        protected_sha256=protected(), validator_sha256=sha(__file__))
    save('frozen-plan.json', plan)
    print(sha(HERE / 'frozen-plan.json'))


def download(plan):
    ledger = dict(plan_sha256=sha(HERE / 'frozen-plan.json'), head=None, attempts=[], received_bytes=0)
    save('download-ledger.json', ledger)
    request = urllib.request.Request(plan['full_url'], method='HEAD')
    with urllib.request.urlopen(request, timeout=30) as response:
        ledger['head'] = dict(status=response.status, url=response.url, headers=dict(response.headers))
    size = int(ledger['head']['headers'].get('Content-Length', ledger['head']['headers'].get('content-length', 0)))
    ledger['head_size_bytes'] = size
    save('download-ledger.json', ledger)
    if not 0 < size <= plan['limits']['max_full_bytes']:
        ledger['status'] = 'blocked_head_size_missing_or_exceeds_64MiB'
        save('download-ledger.json', ledger)
        raise RuntimeError(ledger['status'])
    FULL.parent.mkdir(parents=True, exist_ok=True)
    if FULL.exists():
        raise RuntimeError('Refuse to reuse unrecorded preexisting full artifact')
    for attempt in range(2):
        item = dict(attempt=attempt+1, bytes=0)
        ledger['attempts'].append(item)
        start = time.monotonic()
        try:
            with urllib.request.urlopen(plan['full_url'], timeout=90) as response, FULL.open('wb') as f:
                item.update(status=response.status, url=response.url, headers=dict(response.headers))
                while True:
                    if time.monotonic() - start > 90:
                        raise TimeoutError('90-second attempt wall limit')
                    budget_left = plan['limits']['max_total_received_body_bytes'] - ledger['received_bytes']
                    if budget_left <= 0:
                        raise RuntimeError('70MiB total traffic budget reached')
                    chunk = response.read(min(1024*1024, budget_left))
                    if not chunk:
                        break
                    ledger['received_bytes'] += len(chunk)
                    item['bytes'] += len(chunk)
                    if item['bytes'] > plan['limits']['max_full_bytes']:
                        raise RuntimeError('64MiB object cap exceeded')
                    f.write(chunk)
            if item['bytes'] != size:
                raise RuntimeError('GET size differs from HEAD')
            item['sha256'] = sha(FULL)
            ledger['status'] = 'download_complete'
            save('download-ledger.json', ledger)
            return ledger
        except Exception as exc:
            item['error'] = str(exc)
            item['seconds'] = time.monotonic() - start
            save('download-ledger.json', ledger)
            if attempt == 1 or ledger['received_bytes'] + size > plan['limits']['max_total_received_body_bytes']:
                raise
            time.sleep(5)


def compare(a, b):
    import numpy as np
    a, b = np.asarray(a), np.asarray(b)
    finite = np.isfinite(a) & np.isfinite(b)
    delta = np.abs(a[finite].astype(float) - b[finite].astype(float))
    denom = np.maximum(np.abs(a[finite].astype(float)), np.abs(b[finite].astype(float)))
    rel = np.divide(delta, denom, out=np.zeros_like(delta), where=denom > 0)
    return dict(shape=list(a.shape), dtype_a=str(a.dtype), dtype_b=str(b.dtype),
                bitwise_equal=a.dtype == b.dtype and a.tobytes() == b.tobytes(),
                equal_nan=bool(np.array_equal(a, b, equal_nan=True)),
                finite_a=int(np.isfinite(a).sum()), finite_b=int(np.isfinite(b).sum()),
                finite_mask_different=int(np.count_nonzero(np.isfinite(a) != np.isfinite(b))),
                nan_mask_different=int(np.count_nonzero(np.isnan(a) != np.isnan(b))),
                finite_values_different=int(np.count_nonzero(delta)),
                max_abs=float(delta.max(initial=0)), max_relative=float(rel.max(initial=0)))


def validate(plan, ledger):
    import numpy as np
    from astropy.io import fits
    from astropy.wcs import WCS
    from scipy.ndimage import map_coordinates
    sys.path.insert(0, str(RUNTIME))
    from ml_inference.prepare import prepare, SOURCE_BIT, OUTLIER_BIT

    def request(rows):
        ra, dec = plan['center_deg']
        return dict(schema_version=1, analysis_id='old-train01-transport',
                    source=dict(kind='fits', observations=rows, region=dict(
                        right_ascension_deg=ra, declination_deg=dec, width_arcmin=6., height_arcmin=6.)),
                    options=plan['options'])

    rows = copy.deepcopy(plan['packet_sources'])
    a = prepare(request(rows))
    replacement = copy.deepcopy(rows)
    replacement[0].update(path=str(FULL), access_url=plan['full_url'], sha256=sha(FULL))
    b = prepare(request(replacement))
    result = dict(plan_sha256=sha(HERE/'frozen-plan.json'), download=ledger,
                  comparisons={k:compare(getattr(a,k), getattr(b,k)) for k in ['images','times','outlier','bloom']},
                  per_frame_images=[compare(x,y) for x,y in zip(a.images,b.images)],
                  grid_header_equal=a.grid.to_header_string()==b.grid.to_header_string(),
                  grid_header=a.grid.to_header_string(), pixel_scale_equal=a.pixel_scale==b.pixel_scale,
                  warnings_a=a.warnings, warnings_b=b.warnings,
                  frames_a=a.frames, frames_b=b.frames,
                  expected_shape_equal=list(a.images.shape)==plan['expected_shape'],
                  expected_times=compare(a.times,plan['expected_times_hours']))
    excluded = {'sha256','input_size_bytes','access_url'}
    result['physical_frame_metadata_equal'] = ([{k:v for k,v in f.items() if k not in excluded} for f in a.frames] ==
                                              [{k:v for k,v in f.items() if k not in excluded} for f in b.frames])
    yy,xx = np.indices(a.images.shape[1:]); sky = a.grid.pixel_to_world_values(xx,yy)
    variants = []
    for path in [Path(rows[0]['path']),FULL]:
        with fits.open(path,memmap=False,lazy_load_hdus=True) as hs:
            h=hs[0].header.copy();h.update(hs['IMAGE'].header)
            w=WCS(h).celestial
            x,y=w.world_to_pixel_values(*sky)
            flags=hs['FLAGS'].data.astype(np.int64)
            signal=np.asarray(hs['IMAGE'].data,dtype=float)-hs['ZODI'].data
            var=hs['VARIANCE'].data
            good=((flags & ~(SOURCE_BIT|OUTLIER_BIT))==0)&np.isfinite(signal)&np.isfinite(var)&(var>0)
            support=map_coordinates(good.astype(float),[y,x],order=1,cval=0)
            variants.append(dict(header={k:h.get(k) for k in ['OBSID','DETECTOR','MJD-AVG','DATE-AVG','VERSION','BUNIT','CRPIX1','CRPIX2','CRVAL1','CRVAL2','CTYPE1','CTYPE2','CDELT1','CDELT2','PC1_1','PC1_2','PC2_1','PC2_2','A_ORDER','B_ORDER']},
                hdus=[dict(name=t.name, axes=[t.header.get('NAXIS1'),t.header.get('NAXIS2')], bitpix=t.header.get('BITPIX')) for t in hs],
                x=x,y=y,support=support, image=np.array(hs['IMAGE'].data), flags=np.array(hs['FLAGS'].data),
                variance=np.array(var),zodi=np.array(hs['ZODI'].data),wcs=w))
    ca,fu=variants
    c_y,c_x=np.indices(ca['image'].shape)
    f_x,f_y=fu['wcs'].world_to_pixel_values(*ca['wcs'].pixel_to_world_values(c_x,c_y))
    ix,iy=np.rint(f_x).astype(int),np.rint(f_y).astype(int)
    raw={k:compare(ca[k],fu[k][iy,ix]) for k in ['image','flags','variance','zodi']}
    offset=np.array([np.median(fu['x']-ca['x']),np.median(fu['y']-ca['y'])])
    result['native_diagnostics']=dict(
        cutout={k:ca[k] for k in ['header','hdus']},full={k:fu[k] for k in ['header','hdus']},
        full_minus_cutout_coordinate_offset_pixels=offset.tolist(),
        registration_x_after_offset=compare(ca['x'],fu['x']-offset[0]),
        registration_y_after_offset=compare(ca['y'],fu['y']-offset[1]),
        raw_cutout_at_wcs_corresponding_full_pixels=raw,
        full_index_rounding_max_abs_pixels=float(max(np.max(np.abs(f_x-ix)),np.max(np.abs(f_y-iy)))),
        support=compare(ca['support'],fu['support']),
        support_threshold_mask=compare(ca['support']>=.995,fu['support']>=.995))
    result['protected_sha256_after']=protected()
    result['protected_all_unchanged']=result['protected_sha256_after']==plan['protected_sha256']
    result['peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    save('results.json',result)
    print(json.dumps(dict(protected_unchanged=result['protected_all_unchanged'],comparisons=result['comparisons'],native=result['native_diagnostics']['raw_cutout_at_wcs_corresponding_full_pixels'])))


if __name__ == '__main__':
    os.environ.update(OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',MKL_NUM_THREADS='2')
    resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    if sys.argv[1:] == ['freeze']:
        freeze()
    elif sys.argv[1:] == ['execute']:
        plan=json.loads((HERE/'frozen-plan.json').read_text())
        assert protected()==plan['protected_sha256']
        assert sha(__file__)==plan['validator_sha256']
        validate(plan,download(plan))
    else:
        raise SystemExit('Use freeze or execute')
