"""Scientific guards for the isolated experimental search."""
import numpy as np
import pytest
from ml_inference.detector import DetectionLimitError
from experiments.v3_detection.digital_tracking import find_joint_candidates


def test_work_cap_never_silently_returns_partial_candidates():
    images=np.random.default_rng(9).normal(size=(4,32,32))
    with pytest.raises(DetectionLimitError,match='partial results withheld'):
        find_joint_candidates(images,np.arange(4.),max_work=10)


def test_duplicate_physical_midpoints_rejected():
    with pytest.raises(ValueError,match='physical-hour'):
        find_joint_candidates(np.zeros((3,16,16)),[0.,0.,1.])


def test_masked_path_does_not_produce_a_candidate():
    tracks,diagnostics=find_joint_candidates(np.full((3,16,16),np.nan),np.arange(3.),max_displacement_px=4)
    assert not tracks
    assert diagnostics['work_pixels_epochs']>0


def test_faint_linear_source_recovered_without_position_input():
    rng=np.random.default_rng(5501);n=8;size=40;images=rng.normal(0,1,(n,size,size));times=np.arange(n,dtype=float)
    yy,xx=np.indices((size,size));positions=np.array([10.,12.])+times[:,None]*np.array([2.,1.])
    for image,(x,y)in zip(images,positions):image+=17/(2*np.pi*1.2**2)*np.exp(-((xx-x)**2+(yy-y)**2)/(2*1.2**2))
    tracks,_=find_joint_candidates(images,times,max_displacement_px=20,threshold=5,statistic='trimmed')
    assert any(np.all(np.linalg.norm(np.asarray(t.positions_xy)-positions,axis=1)<=1.5)for t in tracks)


def test_dense_velocity_grid_rejected_before_streaming_loop():
    images=np.random.default_rng(1).normal(size=(4,16,16))
    with pytest.raises(ValueError,match='velocity grid'):
        find_joint_candidates(images,np.arange(4.),step_px=.01,max_work=10)


def test_library_creates_missing_scratch_before_compilation(tmp_path,monkeypatch):
    from pathlib import Path as RealPath
    from experiments.v3_detection import digital_tracking
    scratch=tmp_path/'new-session'/'digital-tracking'
    def redirected_path(value):
        return scratch if str(value)=='/tmp/spaceapps-v3-detection'else RealPath(value)
    monkeypatch.setattr(digital_tracking,'Path',redirected_path)
    monkeypatch.setattr(digital_tracking,'_lib',None)
    assert not scratch.exists()
    library=digital_tracking.library()
    assert scratch.is_dir()
    assert callable(library.search)
