"""A bounded review must preserve learned budgets and separate unscored evidence."""
from ml_inference import pipeline


def rows(residuals,blooms):
    return ([(f'r{i}',i+1,.5,False) for i in range(residuals)]
            +[(f'b{i}',i+1,None,True) for i in range(blooms)])


def test_new_profile_retains_three_ordered_residuals_and_unscored_bloom():
    entries = rows(112,1)
    select = getattr(pipeline,'select_review_entries',None)
    assert callable(select), 'The bounded mixed-evidence review policy is missing'
    result = select(entries,100,preserve_bloom=True)
    assert result[:3] == entries[:3]
    assert len(result) == 100
    assert result[-1] == ('b0',1,None,True)
    assert result[:-1] == entries[:99]
    assert select(entries,100) == entries[:100]


def test_small_requested_budget_does_not_displace_protected_residual_reviews():
    select = getattr(pipeline,'select_review_entries',None)
    assert callable(select), 'The bounded mixed-evidence review policy is missing'
    entries = rows(10,10)
    for limit in [1,2,3]:
        assert select(entries,limit,preserve_bloom=True) == entries[:limit]
    assert select(rows(0,5),3,preserve_bloom=True) == rows(0,5)[:3]
    assert select(rows(3,112),100,preserve_bloom=True) == rows(3,97)
    assert select(rows(2,1),100,preserve_bloom=True) == rows(2,1)
