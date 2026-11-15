import numpy as np


def test_linear_source_is_recovered_without_target_coordinates():
    from ml_inference.detector import find_candidates
    rng = np.random.default_rng(42)
    images = rng.normal(0, 1, (4, 48, 48))
    yy, xx = np.indices((48, 48))
    positions = [(12 + 4*t, 18 + 2*t) for t in range(4)]
    for image, (x, y) in zip(images, positions):
        image += 25*np.exp(-((xx-x)**2+(yy-y)**2)/3)
    candidates = find_candidates(images, np.arange(4.), leave_one_out=True)
    assert any(np.max(np.linalg.norm(np.asarray(c.positions_xy)-positions, axis=1)) <= 1
               for c in candidates if c.epochs == (0, 1, 2, 3))


def test_empty_evidence_has_no_candidates():
    from ml_inference.detector import find_candidates
    assert find_candidates(np.zeros((3, 20, 20))) == []


def test_linker_rejects_excessive_combinatorial_work():
    import pytest
    from ml_inference.detector import link_detections, DetectionLimitError
    peaks=[np.array([[10.+i,10.,10.,1.],[20.+i,20.,10.,1.]]) for i in range(4)]
    with pytest.raises(DetectionLimitError):
        link_detections(peaks,np.arange(4.),.1,10.,1.4,3,max_link_checks=1)
