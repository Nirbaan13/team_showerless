"""Read-only post-inference audit of Ivan responses against frozen published truth.

Run with ~/edu/UtilsAI/.venv/bin/python. No detector, training, network access,
image alteration, ranking, or astrometric fitting occurs here. The old truth's
predicted_xy belongs to a different grid and is deliberately never used.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess

import astropy
from astropy.coordinates import SkyCoord
from astropy.io.fits import Header
from astropy.time import Time
from astropy.wcs import WCS
import astropy.units as u
import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def source_snapshot(root):
    """Bind local source bytes; this is not an assertion about a running image."""
    paths = ['ml/service.py', 'science/motion/prepared.py',
             'science/motion/profiles.py', 'science/motion/detector.py',
             'science/motion/review.py', 'science/motion/ranker.py',
             'pipeline/unification/unwise.py', 'pipeline/unification/resampling.py',
             'pipeline/unification/worker.py', 'pipeline/unification/ml.py',
             'ml/pvusatov/support/historical/verify_real_http.py',
             'ml/pvusatov/support/historical/audit_real_recovery.py']
    files = {p: sha(root / p) for p in paths}
    head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    return dict(git_head=head, files_sha256=files,
                status='Observed local development source; unfrozen local QA, not an executed-image attestation',
                astropy_version=astropy.__version__, numpy_version=np.__version__)


def audit(runtime, truth_path, source_root):
    # Hash the exact completed HTTP bytes before reading the external truth.
    response_path = runtime / 'ivan-review.json'
    response_sha = sha(response_path)
    review = read(response_path)
    proof = read(runtime / 'runtime-proof.json')
    calls = read(runtime / 'http-calls.json')
    selection = read(runtime / 'selection.json')
    downloaded = read(runtime / 'download-completed.json')
    require(proof['review_sha256'] == response_sha, 'Runtime proof response SHA mismatch')
    matching_calls = [c for c in calls if c.get('raw_response') == 'ivan-review.json']
    require(len(matching_calls) == 1, 'Expected one final review HTTP call')
    call = matching_calls[0]
    require(call['method'] == 'POST' and call['path'] == '/api/motion/search' and
            call['status'] == 200 and call['response_sha256'] == response_sha,
            'HTTP response binding mismatch')
    require(call['request'] == dict(unification_id=review['unification_id'],
                                    profile='stellar_proper_motion'),
            'Inference request was not the blind managed-artifact request')
    require(review['id'] == review['unification_id'] == proof['unification_id'],
            'Unification identity mismatch')
    require(selection['synthetic_sources'] is False and
            selection['known_trajectory_sent_to_inference'] is False,
            'Selection is not declared blind natural data')
    require(proof['model_training'] is False and proof['synthetic_source_acceptance'] is False,
            'Unexpected runtime training/synthetic declaration')
    for key in ('target', 'detector', 'simulated_training_fields', 'ephemeris_match_tolerance_px'):
        require(review[key] is None, f'Unexpected {key}')
    require(review['has_ephemeris'] is False, 'Ephemeris was supplied')
    require(review['comparison']['random_forest'] is None and
            all(t['random_forest_rank'] is None for t in review['tracks']),
            'Unexpected random forest ranking')
    require(review['profile'] == 'stellar_proper_motion', 'Wrong profile')
    profile = review['search_profile']
    require(profile['proper_motion_arcsec_per_year'] == dict(min=0.1, max=30.0),
            'Unexpected proper motion bounds')
    require(profile['time_unit'] == 'hours' and profile['speed_unit'] == 'pixels/hour',
            'Wrong time/speed units')
    scale = review['pixel_scale_arcsec']
    require(scale == 2.75 and profile['hours_per_year'] == 24 * 365.25,
            'Unexpected angular or year scale')
    for bound in ('min', 'max'):
        require(math.isclose(profile[bound + '_speed'] * scale * 8766,
                             profile['proper_motion_arcsec_per_year'][bound], rel_tol=1e-12),
                'Profile angular/time conversion mismatch')

    frames = review['frames']
    prep = review['historical_preparation']
    require(prep['artifact_mask_available'] is False and prep['psf_homogenized'] is False,
            'Unexpected preparation qualification')
    mjd = Time([f['time'] for f in frames], format='isot', scale='utc').mjd
    hours = (mjd - mjd[0]) * 24
    require(np.all(np.diff(hours) > 0), 'Frames are not chronological')
    require(13 < (mjd[-1] - mjd[0]) / 365.25 < 15, 'Unexpected historical span')
    require(len(frames) == len(prep['frames']) == len(selection['epochs']) == 8,
            'Expected eight fixed real epochs')
    for frame, p, date, epoch in zip(frames, prep['frames'], mjd, selection['epochs']):
        interval = p['historical_motion_qualification']['time']
        midpoint = (interval['start_mjd'] + interval['end_mjd']) / 2
        require(abs(date - midpoint) < 1e-8 and interval['scale'] == 'utc',
                'Response date differs from real native UTC interval midpoint')
        require(frame['id'] == p['observation_identity'], 'Frame identity mismatch')
        require(p['historical_motion_qualification']['epoch'] == epoch,
                'Native epoch does not match the fixed selection')

    # Only now open the frozen published external astrometry. No cached xy is used.
    truth = read(truth_path)
    ref = truth['reference']
    years = (mjd - ref['mjd']) / 365.25
    ra = ref['ra_degrees'] + years * ref['pm_ra_cosdec_arcsec_per_year'] / (
        3600 * math.cos(math.radians(ref['dec_degrees'])))
    dec = ref['dec_degrees'] + years * ref['pm_dec_arcsec_per_year'] / 3600
    expected = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame='icrs')
    wcs = WCS(Header.fromstring(prep['target_wcs'], sep='\n'))
    expected_xy = wcs.all_world2pix(np.column_stack((ra, dec)), 0)
    require(truth['match_tolerance_px'] == 1.5, 'Frozen match threshold changed')
    tolerance_arcsec = truth['match_tolerance_px'] * scale
    tracks = []
    for track in review['tracks']:
        epochs = np.asarray(track['epochs'], dtype=int)
        require(len(set(epochs.tolist())) == len(epochs) and
                np.all((0 <= epochs) & (epochs < len(frames))), 'Invalid track epochs')
        sky = np.asarray(track['sky_deg'], dtype=float)
        xy = np.asarray(track['positions_xy'], dtype=float)
        require(sky.shape == xy.shape == (len(epochs), 2), 'Track shape mismatch')
        actual = SkyCoord(ra=sky[:, 0] * u.deg, dec=sky[:, 1] * u.deg)
        from_pixels = wcs.all_pix2world(xy, 0)
        wcs_sky = SkyCoord(ra=from_pixels[:, 0] * u.deg, dec=from_pixels[:, 1] * u.deg)
        wcs_errors = actual.separation(wcs_sky).arcsec
        require(np.all(wcs_errors < .001), 'Returned sky_deg does not follow actual target WCS')
        residuals = actual.separation(expected[epochs]).arcsec
        count = int(np.sum(residuals <= tolerance_arcsec))
        pm = track['speed_px_per_time'] * scale * 8766
        require(track['proper_motion_unit'] == 'arcsec/year' and
                math.isclose(pm, track['proper_motion_arcsec_per_year'], rel_tol=1e-10),
                'Reported proper motion conversion mismatch')
        tracks.append(dict(id=track['id'], rank=track['rank'], method=track['method'],
            frame_indices=epochs.tolist(), native_epochs=[selection['epochs'][i] for i in epochs],
            observation_ids=[frames[i]['id'] for i in epochs],
            dates_utc=[frames[i]['time'] for i in epochs],
            positions_xy=xy.tolist(), sky_deg=sky.tolist(),
            angular_residuals_arcsec=residuals.tolist(),
            angular_equivalent_residuals_px=(residuals / scale).tolist(),
            max_angular_residual_arcsec=float(residuals.max()),
            median_angular_residual_arcsec=float(np.median(residuals)),
            matched_frames=count, candidate_frames=len(epochs),
            passes_recovery=bool(len(epochs) >= 3 and count == len(epochs)),
            reported_proper_motion_arcsec_per_year=track['proper_motion_arcsec_per_year'],
            reported_speed_px_per_hour=track['speed_px_per_time'],
            reported_fit_rms_px=track['fit_rms_px'],
            stack_contributing_visit_coadds=track['stack_contributing_exposures'],
            random_forest_rank=track['random_forest_rank'],
            max_sky_vs_target_wcs_error_arcsec=float(wcs_errors.max())))
    inputs = []
    for entry in downloaded['assets']:
        asset = entry['asset']
        require(entry['status'] == 'ready' and len(asset['sha256']) == 64,
                'Raw input asset not qualified/checksummed')
        inputs.append(dict(record_id=entry['record_id'], id=asset['id'],
            role=entry['provenance']['asset_role'], bytes=asset['bytes'], sha256=asset['sha256']))
    require(sum(x['bytes'] for x in inputs) == proof['raw_asset_bytes'], 'Raw byte count mismatch')
    require(len(inputs) == proof['raw_assets'] == 32, 'Expected science plus three real auxiliary assets per epoch')
    science_hashes = {a['sha256'] for a in inputs if a['role'] == '#this'}
    require(science_hashes == {p['source_sha256'] for p in prep['frames']},
            'Prepared science input checksums differ from acquired real assets')
    return dict(case=selection['case'], status='RECOVERED' if any(t['passes_recovery'] for t in tracks) else 'NOT_RECOVERED_AMONG_RETURNED_CANDIDATES',
        audit_scope=dict(returned_candidates=len(tracks),
            comparison=review['comparison'],
            full_candidate_pool_audited=all(
                part['candidates'] <= len(tracks) for part in review['comparison'].values()
                if isinstance(part, dict) and 'candidates' in part),
            scope='Only candidates actually present in the unchanged HTTP response are audited; omitted candidates are not classified.'),
        criterion=dict(minimum_candidate_frames=3, all_candidate_frames_within_threshold=True,
                       threshold_pixels=1.5, threshold_arcsec=tolerance_arcsec),
        response_sha256=response_sha, response_bytes=response_path.stat().st_size,
        external_truth=dict(path=str(truth_path), sha256=sha(truth_path), paper=truth['paper'],
            reference=ref, parallax_not_fitted_arcsec=truth['parallax_not_fitted_arcsec'],
            propagation='Frozen published linear mu_alpha*cos(delta), mu_delta; Julian years of 365.25 days from real UTC MJD. No fitting or parallax correction; old predicted_xy ignored.',
            published_total_proper_motion_arcsec_per_year=math.hypot(ref['pm_ra_cosdec_arcsec_per_year'], ref['pm_dec_arcsec_per_year'])),
        source_snapshot=source_snapshot(source_root),
        runtime_evidence_sha256={p.name: sha(p) for p in sorted(runtime.glob('*.json'))},
        blind_checks=dict(has_ephemeris=False, target=None, detector=None, simulated_training_fields=None,
                          random_forest=None, known_trajectory_in_request=False,
                          synthetic_source_acceptance=False, search_profile=profile),
        frames=[dict(index=i, native_epoch=selection['epochs'][i], observation_id=f['id'],
            date_utc=f['time'], mjd_utc=float(mjd[i]), elapsed_hours=float(hours[i]),
            published_prediction_sky_deg=[float(ra[i]), float(dec[i])],
            published_prediction_target_xy=expected_xy[i].tolist(),
            source_science_sha256=prep['frames'][i]['source_sha256'],
            native_time=prep['frames'][i]['source_time']) for i, f in enumerate(frames)],
        span_julian_years=float((mjd[-1] - mjd[0]) / 365.25),
        candidates_in_original_rank_order=tracks,
        raw_assets=dict(checksums_source='Managed download completed HTTP response; this audit does not reread raw FITS bytes',
                        count=len(inputs), total_bytes=sum(x['bytes'] for x in inputs), assets=inputs),
        limitations=[
            'Known historical objects and fixed preselected fields/epochs; not an unbiased search or population completeness estimate.',
            'The matching threshold is fixed at 1.5 pixels (4.125 arcsec), with at least three points and every returned point required to pass.',
            'Native W2 visit coadds are not individual exposures; actual mission gaps and visit time intervals remain.',
            'Artifact/outlier/bloom masks unavailable; inverse variance and coverage do not establish absence of artifacts.',
            'No per-epoch PSF homogenization or independent stellar centroid refinement; resampling covariance not represented.',
            'Published linear motion used without fitted parallax, perspective acceleration, or new astrometric fitting.',
            'Reported proper motion is the existing Ivan inference value converted with 8766 hours/year; no audit fit is performed.',
            'This is a targeted known-object recovery check, not a new discovery or proof that every returned candidate is astrophysical.'
        ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--truth', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[4])
    args = parser.parse_args()
    result = audit(args.runtime.resolve(), args.truth.resolve(), args.source_root.resolve())
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'recovery-audit.json').write_text(json.dumps(result, indent=2) + '\n')
    matched = [t for t in result['candidates_in_original_rank_order'] if t['passes_recovery']]
    returned = len(result['candidates_in_original_rank_order'])
    outcome = 'RECOVERED' if matched else f'Not recovered among the returned {returned} candidates'
    text = [f"# {result['case']}: independent post-inference astrometry audit", '',
            f"Result: **{outcome}**. {len(matched)} of {returned} returned Ivan candidates passes the frozen criterion.", '',
            f"Eight real W2 visit coadds span {result['frames'][0]['date_utc']} to {result['frames'][-1]['date_utc']} ({result['span_julian_years']:.3f} Julian years).", '']
    if not result['audit_scope']['full_candidate_pool_audited']:
        counts = {name: part['candidates'] for name, part in result['audit_scope']['comparison'].items()
                  if isinstance(part, dict) and 'candidates' in part}
        text += [f"The unchanged response contains a returned subset. Its full comparison counts are {json.dumps(counts, sort_keys=True)}. This audit makes no recovery claim about candidates omitted from the response and does not infer why the object is absent.", '']
    for t in matched:
        text += [f"Rank {t['rank']} matches all {t['matched_frames']} candidate epochs; maximum residual {t['max_angular_residual_arcsec']:.6f} arcsec (threshold 4.125 arcsec). Reported motion: {t['reported_proper_motion_arcsec_per_year']:.9f} arcsec/year; published total: {result['external_truth']['published_total_proper_motion_arcsec_per_year']:.9f} arcsec/year.", '']
    text += [f"Exact HTTP response SHA-256: `{result['response_sha256']}`.", '',
             f"Read-only external truth SHA-256: `{result['external_truth']['sha256']}`; source: {result['external_truth']['paper']}.", '',
             'Truth is used only in this separate audit, after the completed blind response. Actual sky_deg is checked against the returned target WCS and published positions propagated to each real UTC midpoint. No detector, selection, ranking, training, image changes, parallax fit, or motion fit occurs here. Source bytes, actual dates, residuals, and all 32 declared raw-asset checksums are in recovery-audit.json.', '',
             'The source snapshot records observed local development files for unfrozen local QA; it is not an executed-image attestation.', '',
             *[f'- {line}' for line in result['limitations']], '']
    (args.output / 'REVIEW.AI.md').write_text('\n'.join(text))
    print(json.dumps(dict(case=result['case'], status=result['status'],
        matching_ranks=[t['rank'] for t in matched], output=str(args.output))))


if __name__ == '__main__':
    main()
