"""Analytic audit-kernel fixtures only; no native evidence or producer imports."""
import unittest
import check


class NumericAuditFixtures(unittest.TestCase):
    def test_spatial_boundary_tie_actual_epoch_span(self):
        truth = [[[0., 0.], [5., 0.], [1., 0.]], [[0., 0.], [5., 0.], [1., 0.]]]
        self.assertEqual(check.spatial_match([0, 1, 2], [[0., 1.5], [5., 1.5], [1., 1.5]], truth), (0, 5.))
        self.assertEqual(check.spatial_match([0, 1, 2], [[0., 1.500001], [5., 1.5], [1., 1.5]], truth), (-2, None))

    def test_pair_exclusion_uses_two_shared_links_and_stable_priority(self):
        rows = [dict(links=[[0, 0], [1, 0], [2, 0]], baseline_score=1., score=.2),
                dict(links=[[0, 0], [1, 0], [3, 1]], baseline_score=1., score=.9),
                dict(links=[[0, 0], [1, 1], [2, 1]], baseline_score=1., score=.1)]
        self.assertEqual(check.pruning(rows, 'legacy')[0], [0, 2])
        self.assertEqual(check.pruning(rows, 'learned_pair')[0], [1, 2])

    def test_unique_truth_resolved_accounting(self):
        rows = [dict(score=.9), dict(score=.8), dict(score=.7)]
        counts = check.recount(rows, [0, 1, 2], [0, 0, 1], [2., 3., 4.])
        self.assertEqual((counts['top1'], counts['top3']), (1, 2))
        self.assertEqual((counts['resolved_top1'], counts['resolved_top3'], counts['unresolved_top3']), (0, 2, 0))

    def test_both_control_policies_determine_common_attribution(self):
        truth = [[[0., 0.], [1., 0.], [2., 0.]]]
        miss = ([0, 1, 2], [[10., 0.], [11., 0.], [12., 0.]])
        hit = ([0, 1, 2], truth[0])
        flags = check.control_attribution(dict(legacy=[miss], learned_pair=[hit]), truth)
        self.assertEqual(flags, dict(legacy=False, learned_pair=True))
        self.assertFalse(not any(flags.values()))

    def test_whole_parent_bootstrap_and_empty_common(self):
        rows = []
        for parent, a, b in [('a', 1, 0), ('b', 0, 1)]:
            rows.append(dict(parent_id=parent, truth_count=1,
                policies={r: dict(candidate_rows=1, top1=x, top3=x) for r, x in [('legacy', a), ('learned_pair', b)]}))
        result = check.summary(rows)
        self.assertEqual(result['macro_delta_top1'], 0.)
        self.assertEqual(result['paired_group_ci95_top1'], [-1., 1.])
        self.assertEqual(result['independent_groups'], 2)
        empty = check.summary([])
        self.assertIsNone(empty['paired_group_ci95_top1'])
        self.assertIsNone(empty['legacy']['micro_recall1'])


if __name__ == '__main__':
    unittest.main()
