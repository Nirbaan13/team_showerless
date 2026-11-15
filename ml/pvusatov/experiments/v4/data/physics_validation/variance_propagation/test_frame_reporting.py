"""Full frame-report math on a toy identity operator; no external files."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import numpy as np

SPEC=importlib.util.spec_from_file_location('conditional_study',Path(__file__).with_name('run_study.py'))
study=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(study)

def test_mc_frame_report_preserves_median_nuisance_with_python_list_accumulation(monkeypatch):
    yy,xx=np.indices((7,7));operator=study.bilinear_operator(xx,yy,np.ones((7,7),bool),np.ones((7,7)))
    operator.update(has_sip=False,operator_vs_prepare_max_abs=0.,native_shape=[7,7])
    monkeypatch.setattr(study,'frame_operator',lambda context,index:operator)
    plan=dict(patches=[dict(id='center-phase'),dict(id='registered-left-edge'),dict(id='mixed-support-boundary')],patch_radius_pixels=3,gaussian_template_sigma_pixels=.8,
              realization_count_per_frame=8,batch_size=4,seeds_by_parent={'toy':1000})
    context=dict(group=dict(parent_id='toy',detector=1),stack=SimpleNamespace(images=np.zeros((2,7,7))),rows=[{},dict(obs_id='toy1',sha256='0'*64)])
    result=study.run_frame(plan,context,1)
    assert result['realizations']==8
    assert np.isfinite(result['global_median_shift_abs_max'])
    available=[patch for patch in result['patches'] if patch['available']]
    assert len(available)==2
    assert all(abs(patch['sigma_ratio_exact_to_diagonal']-1.)<1e-12 for patch in available)
    assert max(patch['maximum_affine_amplitude_change_from_median'] for patch in available)<1e-12
