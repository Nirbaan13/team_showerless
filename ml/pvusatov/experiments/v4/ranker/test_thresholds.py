from pathlib import Path
import sys
import numpy as np
from sklearn.ensemble import ExtraTreesClassifier,HistGradientBoostingClassifier
sys.path.insert(0,str(Path(__file__).resolve().parent))
from threshold_probes import threshold_probes


def test_every_split_gets_path_consistent_float32_neighbors():
    x=np.random.default_rng(8).normal(size=(100,2)).astype(np.float32);y=(x[:,0]*x[:,1]>0).astype(int)
    for model in [ExtraTreesClassifier(n_estimators=4,max_depth=4,min_samples_leaf=2,n_jobs=1,random_state=3),HistGradientBoostingClassifier(max_iter=3,max_depth=3,min_samples_leaf=3,early_stopping=False,random_state=3)]:
        model.fit(x,y);base=np.zeros(30,np.float32);base[[4,9]]=x[0];probes,diagnostics=threshold_probes(model,[4,9],base)
        assert probes.shape[1]==30 and np.isfinite(probes).all()
        assert diagnostics['internal_nodes']>0
        assert diagnostics['internal_nodes']==diagnostics['path_reach_assertions']
        assert diagnostics['covered_internal_nodes']==diagnostics['internal_nodes']
        np.testing.assert_array_equal(probes[:,0],np.zeros(len(probes),np.float32))
