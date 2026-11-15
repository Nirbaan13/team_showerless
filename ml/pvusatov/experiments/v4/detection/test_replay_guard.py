import unittest
from types import SimpleNamespace
import numpy as np
from ml.pvusatov.experiments.v4.detection.replay_guard import validate_replay

class Replay(unittest.TestCase):
    def test_exact_producer_float32_representation_is_required(self):
        row=[4.,.1437297031872635,114.49530649482813,23.010864850814485,.48385896386669164,4.336854415139254]
        t=SimpleNamespace(epochs=(0,1,2,3),positions_xy=((1,2),(2,3),(3,4),(4,5)),features=lambda:row)
        f=dict(candidate_epochs=[list(t.epochs)],candidate_positions_xy=[list(t.positions_xy)],features=np.asarray([row],np.float32).tolist())
        validate_replay([t],f)
        f['features'][0][2]=float(np.nextafter(np.float32(f['features'][0][2]),np.float32(np.inf)))
        with self.assertRaises(AssertionError):validate_replay([t],f)

    def test_changed_candidate_coordinates_fail_even_when_features_match(self):
        t=SimpleNamespace(epochs=(0,1,2),positions_xy=((1,2),(2,3),(3,4)),features=lambda:[3.,0.,4.,4.,0.,1.])
        f=dict(candidate_epochs=[[0,1,2]],candidate_positions_xy=[[[1,2],[2,3],[3.00001,4]]],features=[[3.,0.,4.,4.,0.,1.]])
        with self.assertRaises(AssertionError):validate_replay([t],f)
