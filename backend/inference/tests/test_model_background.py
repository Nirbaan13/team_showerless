"""Injection evaluation uses physical cadence, external ePSFs and immutable masks."""
import importlib
import numpy as np


def module():
    return importlib.import_module('training.evaluate_background')


def test_injection_positions_follow_physical_hours():
    path = module().trajectory([10, 20], [2, -1], np.asarray([0, .05, 5]))
    np.testing.assert_allclose(path, [[10,20],[10.1,19.95],[20,15]])


def test_native_epsf_sampling_preserves_unit_flux_and_asymmetry():
    stamp = np.zeros((5,5)); stamp[2,2] = 3; stamp[2,3] = 1
    patch, x0, y0 = module().native_psf_patch(stamp, 1, 1, 10., 12.)
    assert abs(patch.sum()-1) < 1e-12
    assert patch[12-y0,10-x0] == .75
    assert patch[12-y0,11-x0] == .25


def test_injection_preserves_missing_pixels_and_original_background():
    images = np.zeros((3, 4, 4)); images[0,1,1] = np.nan
    responses = np.ones((3,4,4))
    injected = module().add_projected_injection(images, responses, 2)
    assert np.isnan(injected[0,1,1])
    assert injected[1,1,1] == 2
    assert images[1,1,1] == 0


def test_target_matching_does_not_reclassify_unmatched_real_tracks():
    from ml_inference.detector import Candidate
    known = Candidate((0,1,2), ((1,2),(2,2),(3,2)), (6,6,6), 1, 0, 1)
    other = Candidate((0,1,2), ((10,2),(12,2),(13,2)), (7,7,7), 1, 0, 1)
    result = module().injection_recovery([other,known], np.asarray([.1,.8]),
                                       np.asarray([[1,2],[2,2],[3,2]]), top_k=1)
    assert result['recovered_before_ranking'] is True
    assert result['baseline_recovered_at_k'] is False
    assert result['model_recovered_at_k'] is True
    assert result['other_candidates_unlabeled'] == 1
    assert 'false_candidates' not in result


def test_summary_separates_coverage_and_excludes_preexisting_control_matches():
    def trial(covered, matched, preexisting=False):
        matches = [dict(baseline_rank=1, model_rank=1)] if matched else []
        return dict(usable_center_epochs=covered, control_match_before_injection=preexisting,
                    recovery=dict(recovered_before_ranking=matched,
                                  baseline_recovered_at_k=matched, model_recovered_at_k=matched,
                                  matches=matches, candidates=2),
                    detection=dict(peak_cap_reached=False))
    trials = [trial(4, True, True), trial(3, True), trial(2, False), trial(4, False)]
    summary = module().summarize(trials, 3)
    assert summary['injections'] == 4
    assert summary['attribution_eligible_trials'] == 3
    assert summary['preexisting_control_match_trials'] == 1
    assert summary['recovered_before_ranking'] == 1
    assert summary['baseline_recovered_at_1'] == summary['model_recovered_at_1'] == 1
    assert summary['raw_spatial_matches']['recovered_before_ranking'] == 2
    covered = summary['finite_center_coverage_ge3']
    assert covered['injections'] == 3
    assert covered['attribution_eligible_trials'] == 2
    assert covered['recovered_before_ranking'] == 1
    assert covered['preexisting_control_match_trials'] == 1


def test_summary_handles_empty_coverage_subset_without_invented_recovery():
    summary = module().summarize([], 3)
    assert summary['injections'] == summary['attribution_eligible_trials'] == 0
    assert summary['finite_center_coverage_ge3']['recovered_before_ranking'] == 0


def test_rotated_epsf_projection_matches_preparing_a_native_injection(tmp_path):
    from astropy.io import fits
    from astropy.time import Time
    from ml_inference.prepare import make_grid, prepare
    grid = make_grid(210.80227,54.34895,20,20,6.15)
    native = grid.deepcopy(); native.wcs.pc = [[0,-1],[1,0]]
    rows=[]
    stamp=np.zeros((5,5));stamp[2,2]=.75;stamp[2,3]=.25
    for i in range(3):
        header=native.to_header();header['MJD-AVG']=61000+i/24
        header['DATE-AVG']=Time(61000+i/24,format='mjd').isot
        header['DETECTOR']=2;header['BUNIT']='MJy/sr'
        image=np.zeros((20,20),dtype='float32');flags=np.zeros((20,20),dtype='int32')
        flags[11,10]=1  # the adjacent native PSF sample is masked
        columns=[fits.Column(name='XCENTER',format='E',array=[9]),
                 fits.Column(name='YCENTER',format='E',array=[11]),
                 fits.Column(name='BINX',format='J',array=[0]),
                 fits.Column(name='BINY',format='J',array=[0]),
                 fits.Column(name='CWAVE',format='E',array=[1.5]),
                 fits.Column(name='EPSF',format='25D',dim='(5,5)',array=[stamp])]
        epsf=fits.BinTableHDU.from_columns(columns,name='EPSF')
        epsf.header['OVSMPX']=epsf.header['OVSMPY']=1;epsf.header['DETCOORD']='sky'
        hdus=[fits.PrimaryHDU()]
        for name,data in [('IMAGE',image),('FLAGS',flags),('VARIANCE',np.ones_like(image)),('ZODI',image)]:
            hdus.append(fits.ImageHDU(data,header=header,name=name))
        hdus.append(epsf);path=tmp_path/f'native-{i}.fits';fits.HDUList(hdus).writeto(path)
        rows.append(dict(path=str(path),frame_id=str(i),observation_id=str(i)))
    request=dict(schema_version=1,analysis_id='test-epsf',source=dict(kind='fits',observations=rows,
                 region=dict(right_ascension_deg=210.80227,declination_deg=54.34895,
                             width_arcmin=20*6.15/60,height_arcmin=20*6.15/60)))
    original=prepare(request)
    n=module().read_native(tmp_path/'native-0.fits',original.grid,(20,20))
    response,_=module().project_response(n,original.grid,[8,9])
    # Independent native image mutation: a unit asymmetric PSF with total flux 4.
    for row in rows:
        with fits.open(row['path'],mode='update') as hdus:
            hdus['IMAGE'].data[11,9]+=3
            hdus['IMAGE'].data[11,10]+=1
    forward=prepare(request)
    injected=module().add_projected_injection(original.images,np.stack([response]*3),4)
    np.testing.assert_allclose(injected,forward.images,atol=1e-6,equal_nan=True)


def test_counterfactual_diagnostics_preserve_observed_features():
    import importlib
    diagnostic=importlib.import_module('training.diagnose_domain')
    observed=np.array([[3, .2, 50, 30, .3, 6]],dtype=np.float32)
    reference=np.array([[4,.3,7,5,.2,1.8],[6,.4,10,8,.4,2]])
    transformed=diagnostic.counterfactual(observed,'shape_median_and_snr_cap',reference)
    np.testing.assert_allclose(transformed,[[3,.2,10,8,.3,1.9]])
    np.testing.assert_allclose(observed,[[3,.2,50,30,.3,6]])
