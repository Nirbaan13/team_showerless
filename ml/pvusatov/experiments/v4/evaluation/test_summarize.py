import copy
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('v4_summarize', Path(__file__).with_name('summarize.py'))
summary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(summary)


def field():
    six = [[3., 0., 8., 8., 0., 1.], [3., 0., 5., 5., 0., 1.]]
    return dict(seed=3800002, truth_count=1, expected_xy=[[[1., 1.], [2., 1.], [3., 1.]]],
                times_hours=[0., 1., 2.], registered_shape=[3, 80, 80],
                attribution_eligible=True, preexisting_control_match=False,
                mode='injected', metadata=dict(epoch_count=3, cadence_family=0, positive_fluxes=[10.], artifact_fluxes=[10.]*24,
                    label_nuisance_policy='shared flux law, field PSF and overlapping variability for source/artifact identities',
                    detector=1, psf_family='calibration', psf_bank_row=0, epoch_psf_rows=[0]*3,
                    registration_jitter_xy=[[0., 0.]]*3, extended_stationary_sources=0),
                origin_xy=[1., 1.], velocity_xy_hour=[1., 0.], speed_px_hour=1., injected_flux=10.,
                usable_center_epochs=3, center_usable_flags=[True]*3, coverage_known=True,
                features=six, features_v4=[row + [0.] * 24 for row in six],
                candidate_ids=['one', 'two'], candidate_epochs=[[0, 1, 2], [0, 1, 2]],
                candidate_positions_xy=[[[1., 1.], [2., 1.], [3., 1.]], [[8., 8.]] * 3],
                matches=[0, -1], scores_c13=[.2, .8], scores_v4=[.9, .1], error=None,
                matched_geometry=[dict(candidate_index=0, truth_index=0, epochs=[0, 1, 2],
                                       true_displacement_px=2., measured_displacement_px=2., max_offset_px=0.)])


def test_valid_synthetic_rows_are_not_mutated():
    value = field(); original = copy.deepcopy(value)
    summary.validate_field(value, 'synthetic')
    assert value == original


@pytest.mark.parametrize('column,value', [('scores_v4', [.9]), ('scores_c13', [float('nan'), .8]),
                                         ('candidate_ids', ['same', 'same']), ('matches', [-1, -1])])
def test_unaligned_scores_missing_labels_and_duplicate_ids_reject(column, value):
    sample = field(); sample[column] = value
    with pytest.raises(ValueError): summary.validate_field(sample, 'synthetic')


def test_native_unknown_competitor_cannot_become_known_negative():
    sample = field(); sample['expected_xy'] = sample['expected_xy'][0]
    with pytest.raises(ValueError):
        summary.validate_field(sample, 'native', times=[0., 1., 2.], shape=[3, 10, 10])
    sample['matches'][1] = -2
    summary.validate_field(sample, 'native', times=[0., 1., 2.], shape=[3, 10, 10])


def test_missing_or_false_positive_geometry_rejects():
    for mutate in ('missing', 'span', 'epoch'):
        sample = field()
        if mutate == 'missing': sample['matched_geometry'] = []
        elif mutate == 'span': sample['matched_geometry'][0]['true_displacement_px'] = 100.
        else: sample['candidate_epochs'][0][0] = 3
        with pytest.raises(ValueError): summary.validate_field(sample, 'synthetic')


def test_silently_erased_spatial_recovery_is_rejected_even_when_geometry_is_also_erased():
    sample = field(); sample['matches'] = [-1, -1]; sample['matched_geometry'] = []
    with pytest.raises(ValueError, match='match'):
        summary.validate_field(sample, 'synthetic')


@pytest.mark.parametrize('column,value', [('attribution_eligible', False), ('truth_count_known', False),
                                         ('mode', 'invented'), ('metadata', {})])
def test_false_attribution_unknown_truth_or_invented_generator_reject(column, value):
    sample = field(); sample[column] = value
    with pytest.raises(ValueError): summary.validate_field(sample, 'synthetic')


def test_false_native_velocity_or_preexisting_control_attribution_rejects():
    sample = field(); sample['expected_xy'] = sample['expected_xy'][0]; sample['matches'][1] = -2
    sample['velocity_xy_hour'] = [999., 999.]
    with pytest.raises(ValueError):
        summary.validate_field(sample, 'native', times=[0., 1., 2.], shape=[3, 80, 80])


def test_truncated_unknown_control_cannot_erase_attribution_competitors():
    sample = field(); sample['expected_xy'] = sample['expected_xy'][0]; sample['matches'][1] = -2
    control = field(); control['matches'] = [-2, -2]
    control['candidate_epochs'] = []; control['candidate_positions_xy'] = []
    with pytest.raises(ValueError, match='control|geometry'):
        summary.validate_field(sample, 'native', times=[0., 1., 2.], shape=[3, 80, 80], control=control)


def test_summary_refuses_incomplete_pair_before_reading_outputs(tmp_path):
    with pytest.raises(ValueError, match='both'):
        summary.summarize('missing', '0' * 64, 'missing', 'missing', both_runs_finished=False)
