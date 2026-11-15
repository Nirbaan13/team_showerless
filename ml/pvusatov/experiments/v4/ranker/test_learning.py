from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from learning import labeled_rows,group_class_weights,pairwise_rows


def test_unknown_native_rows_never_enter_known_classes():
    fields=[dict(parent_id='p',attribution_eligible=True,features=[[3.,1.],[4.,2.],[5.,3.]],matches=[0,-2,-1])]
    x,y,g=labeled_rows(fields,'native_moving')
    assert x.tolist()==[[3.,1.]] and y.tolist()==[1] and g==['p']
    x,y,g=labeled_rows(fields,'native_stationary')
    assert x.tolist()==[[5.,3.]] and y.tolist()==[0]


def test_group_class_weight_equalizes_independent_groups_per_class():
    y=np.array([0,0,0,1,1,1]);groups=['a','a','b','a','b','b']
    w=group_class_weights(y,groups)
    assert np.isclose(w[y==0].sum(),w[y==1].sum())
    for label in [0,1]:
        assert np.isclose(w[(y==label)&(np.array(groups)=='a')].sum(),w[(y==label)&(np.array(groups)=='b')].sum())


def test_pairwise_uses_only_same_field_known_synthetic_pairs():
    fields=[dict(seed=1,features=[[3.,1.],[4.,2.],[99.,99.]],matches=[0,-1,-2])]
    differences,labels,weights=pairwise_rows(fields,max_negatives=4)
    assert differences.shape==(2,2)
    assert labels.tolist()==[1,0]
    np.testing.assert_array_equal(differences[0],-differences[1])
    assert max(abs(differences.ravel()))<99


def test_resolved_native_training_labels_become_unknown_without_mutating_evaluation():
    from learning import resolved_native_training_view
    field=dict(parent_id='v4-train01',truth_kind='moving_injection',attribution_eligible=True,matches=[0,0,-2],expected_xy=[[0,0],[1,0],[2,0],[4,0]],center_usable_flags=[True,True,True,True],candidate_epochs=[[0,1,2],[0,2,3],[0,1,2]],matched_geometry=[dict(candidate_index=0,truth_index=0,epochs=[0,1,2],true_displacement_px=2.),dict(candidate_index=1,truth_index=0,epochs=[0,2,3],true_displacement_px=4.)])
    transformed,report=resolved_native_training_view([field])
    assert transformed[0]['matches']==[-2,0,-2]
    assert field['matches']==[0,0,-2]
    assert report['known_positive_before']==2 and report['known_positive_after']==1
    assert report['unresolved_became_unknown']==1
    field['center_usable_flags']=[True,True,True,False]
    transformed,report=resolved_native_training_view([field])
    assert transformed[0]['matches']==[-2,-2,-2]
    assert -1 not in transformed[0]['matches']
