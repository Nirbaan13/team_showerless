from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from frontier import configurations,resolved_configurations


def test_resolved_training_amendment_is_four_distinct_controlled_configs():
    original=configurations();resolved=resolved_configurations()
    assert len(original)==32 and len(resolved)==4
    assert len({c['id']for c in original+resolved})==36
    assert {(c['family'],c['subset'])for c in resolved}=={('extra','legacy6'),('extra','noquality27'),('hist','legacy6'),('hist','noquality27')}
    assert all(c['native_mass']==2 and c['training_label_policy']=='resolved_matched_3px' for c in resolved)
