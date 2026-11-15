"""Recorded-geometry guards use hand-checked fixtures; no science execution."""
import copy
import unittest

from summary_geometry import validate_matched_geometry


def fixture(native=True):
    # Only epochs 1 and 3 were measured: the matched truth span is 4, not 6.
    path = [[0., 0.], [2., 0.], [4., 0.], [6., 0.]]
    return dict(truth_count=1, expected_xy=path if native else [path],
                matches=[0, -2 if native else -1], candidate_epochs=[[1, 3], [0, 2]],
                candidate_positions_xy=[[[2., .5], [6., .5]], [[9., 9.], [9., 9.]]],
                matched_geometry=[dict(candidate_index=0, truth_index=0, epochs=[1, 3],
                                       true_displacement_px=4., measured_displacement_px=4., max_offset_px=.5)])


class GeometryGuards(unittest.TestCase):
    def validate(self, field, native=True):
        return validate_matched_geometry(field, [0., 1., 2., 3.], native=native)

    def test_valid_native_and_synthetic_are_not_mutated(self):
        for native in (True, False):
            field = fixture(native); before = copy.deepcopy(field)
            self.assertIsNone(self.validate(field, native)); self.assertEqual(field, before)

    def test_positive_match_requires_geometry(self):
        field = fixture(); field['matched_geometry'] = []
        with self.assertRaises(ValueError): self.validate(field)

    def test_duplicate_or_extra_geometry_is_rejected(self):
        for index in (0, 1):
            field = fixture(); extra = copy.deepcopy(field['matched_geometry'][0]); extra['candidate_index'] = index
            field['matched_geometry'].append(extra)
            with self.subTest(index=index), self.assertRaises(ValueError): self.validate(field)

    def test_wrong_truth_epoch_span_and_offset_are_rejected(self):
        for key, value in [('truth_index', 1), ('epochs', [0, 3]), ('true_displacement_px', 6.),
                           ('measured_displacement_px', 3.), ('max_offset_px', .4)]:
            field = fixture(); field['matched_geometry'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate(field)

    def test_offset_above_matching_radius_is_rejected(self):
        field = fixture(); field['candidate_positions_xy'][0] = [[2., 1.6], [6., 1.6]]
        field['matched_geometry'][0]['max_offset_px'] = 1.6
        with self.assertRaises(ValueError): self.validate(field)

    def test_nonfinite_and_bad_epoch_or_xy_shapes_are_rejected(self):
        for epochs, xy in [([1, 4], [[2., .5], [6., .5]]), ([3, 1], [[2., .5], [6., .5]]),
                           ([1, 3], [[2., float('nan')], [6., .5]]), ([1, 3], [[2.], [6., .5]])]:
            field = fixture(); field['candidate_epochs'][0] = epochs; field['candidate_positions_xy'][0] = xy
            with self.subTest(epochs=epochs, xy=xy), self.assertRaises(ValueError): self.validate(field)

    def test_empty_detections_and_nonmatches_need_no_fake_geometry(self):
        field = fixture(); field['matches'] = [-2, -2]; field['matched_geometry'] = []; self.validate(field)
        field.update(matches=[], candidate_epochs=[], candidate_positions_xy=[]); self.validate(field)

    def test_measured_span_uses_all_observed_positions(self):
        field = fixture(); field['candidate_epochs'][0] = [1, 2, 3]
        field['candidate_positions_xy'][0] = [[2., 0.], [5.4, 0.], [4.6, 0.]]
        field['matched_geometry'][0].update(epochs=[1, 2, 3], measured_displacement_px=3.4, max_offset_px=1.4)
        self.validate(field)

    def test_float64_roundoff_is_allowed_but_wrong_stored_span_is_not(self):
        field = fixture(); field['matched_geometry'][0]['true_displacement_px'] += 1e-10; self.validate(field)
        field['matched_geometry'][0]['true_displacement_px'] += 1e-6
        with self.assertRaises(ValueError): self.validate(field)

    def test_times_and_truth_shapes_must_align(self):
        field = fixture()
        with self.assertRaises(ValueError): validate_matched_geometry(field, [0., 1.], native=True)
        field['expected_xy'][0] = [float('inf'), 0.]
        with self.assertRaises(ValueError): self.validate(field)


if __name__ == '__main__': unittest.main()
