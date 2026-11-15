"""Guard truth filtering without reranking or fabricated denominators."""
from companion import eligible_counts, cohort_statistics


def test_ineligible_competitor_stays_in_original_budget():
    result = eligible_counts([1, 0, 0], [.9, .8, .7], {0})
    assert result == {'top1': 0, 'top3': 1, 'detected': 1}


def test_stable_ties_and_duplicate_truths():
    result = eligible_counts([1, 0, 0, -1], [.8, .8, .8, .1], {0})
    assert result['top1'] == 0 and result['top3'] == 1


def test_empty_eligible_fields_have_no_fake_recall():
    result = cohort_statistics([{'original_truths': 2, 'eligible_truths': 0, 'candidate_rows': 8}])
    assert not result['recall_defined'] and result['empty_eligible_fields'] == 1
    assert result['original_candidate_rows_in_empty_eligible_fields'] == 8
    assert 'baseline' not in result
