"""Isolated maximum image-shape extraction measurement; no scientific inputs."""
import argparse
from dataclasses import dataclass
import json
import resource
import time
import numpy as np
from ml.pvusatov.experiments.v4.detection.features import extract_features


@dataclass
class Track:
    epochs: tuple
    positions_xy: tuple
    def features(self):return (len(self.epochs),.1,8.,7.,.1,2.)


def run(output):
    images=np.random.default_rng(3800999).normal(0,1,(32,512,512))
    times=np.arange(32.)*.25
    track=Track(tuple(range(32)),tuple((100.+i,200.)for i in range(32)))
    started=time.perf_counter();result=extract_features(images,times,[track])
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    assert result['features_v4'].shape==(1,30)and np.isfinite(result['features_v4']).all()
    allowance=150.;limit=1024.
    proof=dict(shape=list(images.shape),nonempty_tracks=1,matched_epochs=32,peak_rss_mib=rss,
        model_headroom_mib=allowance,limit_mib=limit,passes=rss+allowance<limit,
        elapsed_seconds=time.perf_counter()-started,feature_source_sha256=result['feature_source_sha256'],
        feature_contract_sha256=result['feature_contract_sha256'])
    if output:
        from pathlib import Path
        p=Path(output);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof),flush=True)
    if not proof['passes']:raise SystemExit('maximum-shape extraction lacks 150MiB model headroom under1GiB')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output');a=p.parse_args();run(a.output)
