"""Guard that detector-specific geometry cannot be inherited across profiles."""
import numpy as np
from ml_inference.detector import Candidate
from experiments.v3_detection import recache_expanded


def test_record_indexes_geometry_to_new_candidate_order():
    truth=np.array([[1.,1.],[2.,1.],[3.,1.]])
    wrong=Candidate((0,1,2),((10,10),(11,10),(12,10)),(5.,6.,7.),1.,0.,1.)
    matched=Candidate((0,1,2),((1,1),(2,1),(3,1)),(5.,6.,7.),1.,0.,1.)
    result=recache_expanded.record([wrong,matched],truth)
    assert 'matched_geometry'in result
    assert result['matches']==[-2,0]
    assert result['matched_geometry'][0]['candidate_index']==1
    assert result['matched_geometry'][0]['true_displacement_px']==2.
    assert result['matched_geometry'][0]['max_offset_px']==0.
