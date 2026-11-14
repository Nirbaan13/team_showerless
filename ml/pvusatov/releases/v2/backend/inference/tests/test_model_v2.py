"""Physical simulation prevents v1 brightness/cadence/PSF nuisance shortcuts."""
import importlib
import numpy as np


def simulation():
    return importlib.import_module('training.simulate_v2')


def test_v2_cadences_cover_short_arcs_and_clustered_long_gaps():
    sim=simulation();spans=[];ratios=[]
    for seed in range(100):
        times,family=sim.draw_cadence(np.random.default_rng(seed),4)
        assert len(times)==4 and times[0]==0 and np.all(np.diff(times)>0)
        spans.append(times[-1]);ratios.append(np.max(np.diff(times))/np.min(np.diff(times)))
    assert min(spans)<.2
    assert max(spans)>5
    assert max(ratios)>50


def test_v2_brightness_draw_has_no_truth_label_input():
    sim=simulation();rng=np.random.default_rng(93)
    true_flux=np.asarray([sim.draw_flux(rng,1.)for _ in range(1000)])
    artifact_flux=np.asarray([sim.draw_flux(rng,1.)for _ in range(1000)])
    # The shared physical amplitude law has broad overlapping support, unlike v1.
    assert np.quantile(true_flux,.1)<20 and np.quantile(true_flux,.9)>200
    assert np.quantile(artifact_flux,.1)<20 and np.quantile(artifact_flux,.9)>200
    assert abs(np.median(np.log(true_flux))-np.median(np.log(artifact_flux)))<.2


def test_v2_native_response_keeps_asymmetric_psf_after_registration():
    sim=simulation();image=np.zeros((24,24));stamp=np.zeros((5,5));stamp[2,2]=.75;stamp[2,3]=.25
    sim.render_source(image,[10.,12.],4.,stamp,1,0.,[0.,0.])
    assert abs(image.sum()-4)<1e-10
    np.testing.assert_allclose(image[12,10:12],[3,1],atol=1e-10)


def test_v2_simulator_is_reproducible_and_includes_three_to_eight_epochs():
    sim=simulation();bank=sim.procedural_bank()
    epochs=set()
    for seed in [10002,10003,10004,10005,10006,10007,10008,10009,10012,10013]:
        images,times,truth,mode,metadata=sim.simulate(seed,bank)
        epochs.add(len(times))
        assert images.shape==(len(times),80,80)
        assert np.isfinite(images).any()
        assert all(path.shape==(len(times),2)for path in truth)
        assert metadata['epoch_count']==len(times)
    a=sim.simulate(10002,bank);b=sim.simulate(10002,bank)
    np.testing.assert_array_equal(a[0],b[0])
    assert 3 in epochs and max(epochs)>=6


def test_calibration_subset_covers_detector_geometry_without_field_pixels():
    prepare=importlib.import_module('training.prepare_calibration')
    x=np.tile([0,100,200],3);y=np.repeat([0,100,200],3)
    selected=prepare.spatial_subset(x,y,2)
    assert selected==[0,2,6,8]


def test_v2_split_ranges_exclude_v1_fields_and_each_other():
    trainer=importlib.import_module('training.train_v2')
    seeds=trainer.split_seeds(10,10,10)
    assert seeds['train']==list(range(10000,10010))
    assert seeds['validation']==list(range(300000,300010))
    assert seeds['test']==list(range(500000,500010))


def test_ablation_forest_cannot_use_an_ignored_observed_feature():
    ablation=importlib.import_module('training.ablate_v2')
    rng=np.random.default_rng(5);x=rng.uniform(0,10,(100,6));y=(x[:,0]>5).astype(int)
    forest=ablation.fit_ablation(x,y,dict(n_estimators=10,min_samples_leaf=2,random_state=5),[0])
    probes=x.copy();probes[:,0]+=1000
    np.testing.assert_array_equal(forest.predict_proba(x),forest.predict_proba(probes))


def test_v2_extended_backgrounds_and_epoch_psfs_are_explicit_simulation_families():
    sim=simulation();bank=sim.procedural_bank()
    images,times,truth,mode,metadata=sim.simulate(10002,bank,extended=True,varying_psf=True)
    assert metadata['extended_stationary_sources']>=3
    assert len(metadata['epoch_psf_rows'])==len(times)
    assert len(set(metadata['epoch_psf_rows']))>1
    assert np.isfinite(images).any() and truth


def test_generator_ablation_preserves_latent_injections_and_brightness():
    sim=simulation();bank=sim.procedural_bank()
    original=sim.simulate(10002,bank)
    augmented=sim.simulate(10002,bank,extended=True,varying_psf=True)
    np.testing.assert_array_equal(original[1],augmented[1])
    np.testing.assert_array_equal(original[2],augmented[2])
    assert original[4]['positive_fluxes']==augmented[4]['positive_fluxes']
    assert original[4]['artifact_fluxes']==augmented[4]['artifact_fluxes']


def test_epoch_stratum_weighting_removes_synthetic_class_frequency_shortcut():
    weights=importlib.import_module('training.weights')
    x=np.zeros((14,6));x[:8,0]=3;x[8:10,0]=4;x[10:12,0]=3;x[12:,0]=4
    y=np.array([0]*10+[1]*4)
    actual=weights.epoch_stratum_weights(x,y)
    np.testing.assert_allclose(actual[:8],.625)
    np.testing.assert_allclose(actual[8:10],2.5)
    np.testing.assert_allclose(actual[10:],1.)


def test_reserved_synthetic_evaluation_rejects_any_development_field():
    import pytest
    evaluation=importlib.import_module('training.evaluate_synthetic')
    partitions=dict(train=[10000,10001],validation=[300000],test=[900100])
    with pytest.raises(ValueError,match='overlap'):
        evaluation.check_reserved_seeds(partitions,[499999,900100])
    evaluation.check_reserved_seeds(partitions,[500000,500001])
