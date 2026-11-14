"""Protocol regressions: native unknowns must never become training negatives."""
import numpy as np
from protocol import training_rows, recovery_report

def test_native_unknown_candidates_are_excluded_from_fit():
    synthetic=[dict(features=[[3,.2,8,5,.1,.5],[3,.5,4,4,.4,.2]],matches=[0,-1])]
    native=[dict(parent_id='p',features=[[4,.1,12,6,.2,.4],[4,.5,20,8,.4,.8]],matches=[0,-2],attribution_eligible=True,truth_count=1,baseline=[2,3])]
    x,y,w,origin=training_rows(synthetic,native,native_positive_mass=1)
    assert len(x)==3
    assert y.tolist()==[1,0,1]
    assert origin==['synthetic','synthetic','native:p']
    assert not any(np.array_equal(row,native[0]['features'][1]) for row in x)

def test_preexisting_control_match_is_not_attributed_to_injection():
    native=[dict(parent_id='p',features=[[3,.1,5,4,.2,.4]],matches=[0],attribution_eligible=False,truth_count=1,baseline=[1]),dict(parent_id='p',features=[[3,.1,5,4,.2,.4],[3,.3,10,5,.2,.4]],matches=[0,-2],attribution_eligible=True,truth_count=1,baseline=[1,2])]
    report=recovery_report(native,lambda f:np.asarray(f['baseline']))
    assert report['planned_injections']==2
    assert report['eligible_injections']==1
    assert report['detected']==1
    assert report['top1']==0
    assert report['top3']==1
    assert 'false_tracks' not in report
