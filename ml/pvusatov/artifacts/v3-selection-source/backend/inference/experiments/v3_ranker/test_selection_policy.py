"""Prospective validation gate must protect both synthetic review budgets."""
from select_cached import qualifies

def metrics(n1,n3,s1,s3):
    return dict(native=dict(macro_parent_recall1=n1,macro_parent_recall3=n3),synthetic=dict(macro_cadence_recall1=s1,macro_cadence_recall3=s3))

def test_native_gain_cannot_offset_a_synthetic_regression_against_v2():
    heuristic=metrics(.05,.08,.05,.08)
    v2=metrics(.1,.15,.1,.15)
    candidate=metrics(.2,.25,.09,.16)
    assert not qualifies(candidate,heuristic,v2)
