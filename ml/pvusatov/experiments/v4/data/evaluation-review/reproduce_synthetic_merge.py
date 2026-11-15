"""Exercise actual generate() control flow using no-model/no-FITS fake observables."""
from pathlib import Path
import hashlib,json,sys,types
from types import SimpleNamespace
import numpy as np
OWN=Path(__file__).resolve().parent;NAMESPACE=OWN.parents[3];EVALUATION=OWN.parents[1]/'evaluation'
def module(name,path):
    m=types.ModuleType(name);m.__file__=str(path);sys.modules[name]=m;exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m

def main():
    sys.path.insert(0,str(EVALUATION));m=module('review_run_synthetic',EVALUATION/'run_synthetic.py');old=module('review_old_records',NAMESPACE/'backend/inference/experiments/v3_evaluation/run_native.py')
    m.FROZEN=dict(synthetic=dict(seeds=[3800000]),scope='development');m.BANK=None
    def simulate(*args,**kwargs):return np.zeros((3,5,5)),np.array([0.,1.,2.]),[],'noise_only',dict(epoch_count=3)
    def measure(*args):return [],dict(features=[],candidate_epochs=[],candidate_positions_xy=[],features_v4=[],scores_c13=[],scores_v4=[],candidate_ids=[])
    m.MODULES=SimpleNamespace(simulator=SimpleNamespace(simulate=simulate),scene=SimpleNamespace(measure=measure),latent=old)
    report=dict(scope='Actual generate() + actual legacy _record(); fake observable arrays and no detector/model/FITS calls',source_sha256=hashlib.sha256((EVALUATION/'run_synthetic.py').read_bytes()).hexdigest())
    try:
        result=m.generate(3800000);report.update(status='returned',candidate_rows=len(result['matches']))
    except Exception as e:report.update(status='raised',error_type=type(e).__name__,message=str(e))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
