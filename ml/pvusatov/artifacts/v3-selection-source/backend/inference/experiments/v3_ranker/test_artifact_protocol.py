import numpy as np
from protocol_artifacts import training_rows

def test_known_stationary_artifacts_provide_native_negatives_without_unknown_rows():
    synthetic=[dict(features=[[3,.2,8,5,.1,.5],[3,.5,4,4,.4,.2]],matches=[0,-1])]
    native=[dict(parent_id='a',features=[[4,.1,12,6,.2,.4]],matches=[0],attribution_eligible=True)]
    artifacts=[dict(parent_id='a',features=[[4,.3,9,5,.3,.5],[4,.4,99,80,.1,.2]],matches=[-1,-2],attribution_eligible=True)]
    x,y,w,origin=training_rows(synthetic,native,1,artifacts,1)
    assert len(x)==4
    assert y.tolist()==[1,0,1,0]
    assert origin==['synthetic','synthetic','native:a','native_artifact:a']
    assert not np.any(x[:,2]==99)
    assert np.isclose(w[y==0].sum(),w[y==1].sum())
    assert np.isclose(w[2],w[3])
