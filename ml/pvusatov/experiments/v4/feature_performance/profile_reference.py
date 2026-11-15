"""Fixed DEV-only full-pool feature profile; no new latents or labels."""
from pathlib import Path
import cProfile,hashlib,io,json,pstats,resource,time
import numpy as np
from ml_inference.detector import difference_frames,_detect_peaks
from ml.pvusatov.experiments.v4.association_pilot.policies import build_hypotheses
from ml.pvusatov.experiments.v4.detection.features import extract_features
from ml.pvusatov.experiments.v4.operating_points.study import atomic,digest
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'detection/features.py'

def main():
    plan=json.loads((HERE/'protocol.json').read_text());packet=plan['profile_packet']
    if digest(SOURCE)!=plan['reference_feature_sha256']or digest(packet['path'])!=packet['sha256']:raise ValueError('fixed DEV source/input differs')
    with np.load(packet['path'])as f:images=f['images'];times=f['times'];outlier=f['outlier'];bloom=f['bloom'];bloom=None if bloom.size==0 else bloom
    residual=difference_frames(images,leave_one_out=True);peaks=[_detect_peaks(d,np.isfinite(d),.8,4.,100,.8)for d in residual]
    pool,work=build_hypotheses(peaks,times,.5,60.,1.4,3);tracks=[c for _,c in pool]
    call=lambda:extract_features(images,times,tracks,psf_sigma=.8,outlier=outlier,bloom=bloom,residuals=residual)
    start=time.process_time();reference=call();plain_cpu=time.process_time()-start
    profiler=cProfile.Profile();result=profiler.runcall(call)
    np.testing.assert_array_equal(reference['features_v4'],result['features_v4']);assert reference['candidate_ids']==result['candidate_ids'];assert reference['diagnostics']==result['diagnostics']
    text=io.StringIO();stats=pstats.Stats(profiler,stream=text).strip_dirs().sort_stats('cumulative');stats.print_stats(45)
    (HERE/'profile-reference.txt').write_text(text.getvalue())
    functions=[dict(file=k[0],line=k[1],name=k[2],primitive_calls=v[0],calls=v[1],self_seconds=v[2],cumulative_seconds=v[3])for k,v in stats.stats.items()]
    atomic(HERE/'profile-reference.json',dict(protocol_sha256=digest(HERE/'protocol.json'),source_sha256=digest(__file__),reference_feature_sha256=digest(SOURCE),candidate_count=len(tracks),shape=list(images.shape),hypothesis_work=work,plain_cpu_seconds=plain_cpu,profile_cpu_seconds=stats.total_tt,maxrss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,functions=sorted(functions,key=lambda x:-x['cumulative_seconds'])[:80]))
    print(text.getvalue());print('PLAIN',plain_cpu,'ROWS',len(tracks))
if __name__=='__main__':main()
