"""Compare original843 with explicitly distinct experimental producer on fixed DEV."""
from pathlib import Path
import hashlib,json,os,resource,time
import numpy as np
from ml_inference.detector import difference_frames,_detect_peaks
from training.simulate_v2 import simulate,load_bank
from ml.pvusatov.experiments.v4.association_pilot.policies import build_hypotheses
from ml.pvusatov.experiments.v4.detection import features as ref
from ml.pvusatov.experiments.v4.detection.runtime_model import load_ranker
from ml.pvusatov.experiments.v4.operating_points.study import atomic,digest,image_hash,INF
from . import prototype
HERE=Path(__file__).resolve().parent

def main():
    cpu=sorted(os.sched_getaffinity(0))[-1];os.sched_setaffinity(0,{cpu})
    plan=json.loads((HERE/'benchmark-plan.json').read_text())
    if any(digest(p)!=s for p,s in plan['source_sha256'].items()):raise ValueError('research producer/source changed')
    model=load_ranker(plan['model_directory']);bank=load_bank(INF/'training/calibration/instrument-epsf-bank.npz')
    if model.metadata['sha256']!=plan['model_sha256']:raise ValueError('fixed scorer changed')
    results=[]
    for case in plan['cases']:
        try:
            if case['kind']=='native_packet':
                if digest(case['path'])!=case['sha256']:raise ValueError('fixed DEV packet changed')
                with np.load(case['path'])as p:images=p['images'];times=p['times'];outlier=p['outlier'];bloom=p['bloom'];bloom=None if bloom.size==0 else bloom
            else:
                if case['seed']not in [3806000,3806001,3806002]:raise ValueError('only preexisting DEV seeds')
                images,times,_,_,_=simulate(case['seed'],bank,extended=case['seed']%3==0,varying_psf=True);outlier=bloom=None
            if image_hash(images)!=case['image_sha256']:raise ValueError('DEV image replay differs from prior pilot')
            residual=difference_frames(images,leave_one_out=True);peaks=[_detect_peaks(d,np.isfinite(d),.8,4.,100,.8)for d in residual]
            pool,work=build_hypotheses(peaks,times,.5,60.,1.4,3);tracks=[c for _,c in pool];kw=dict(psf_sigma=.8,outlier=outlier,bloom=bloom,residuals=residual)
            timings={'reference':[],'prototype':[]};outputs={}
            for repetition in range(3):
                order=('reference','prototype')if repetition%2==0 else('prototype','reference')
                for name in order:
                    start=time.process_time();outputs[name]=(ref.extract_features if name=='reference'else prototype.extract_features)(images,times,tracks,**kw);timings[name].append(time.process_time()-start)
            a=outputs['reference'];b=outputs['prototype'];x=np.asarray(a['features_v4']);y=np.asarray(b['features_v4']);xf=x.astype(np.float32);yf=y.astype(np.float32)
            sx=model.score(xf);sy=model.score(yf);orderx=np.argsort(-sx,kind='stable');ordery=np.argsort(-sy,kind='stable')
            assert a['feature_source_sha256']==plan['reference_feature_sha256']
            assert b['feature_source_sha256']==digest(prototype.__file__)and b['reference_feature_source_sha256']==a['feature_source_sha256']
            bitdiff=xf.view(np.uint32)!=yf.view(np.uint32)
            result=dict(case_id=case['case_id'],kind=case['kind'],image_sha256=image_hash(images),candidate_count=len(tracks),shape=list(images.shape),cpu_seconds=timings,median_cpu_seconds={k:float(np.median(v))for k,v in timings.items()},
                float32_equal=bool(np.array_equal(xf,yf)),float32_bitwise_equal=bool(not np.any(bitdiff)),float32_different_values=int(np.sum(xf!=yf)),float32_different_bits=int(np.sum(bitdiff)),
                per_column_different_bits={name:int(bitdiff[:,i].sum())for i,name in enumerate(ref.FEATURE_NAMES)if bitdiff[:,i].any()},
                float64_equal=bool(np.array_equal(x,y)),float64_different_values=int(np.sum(x!=y)),float64_max_abs_difference=float(np.max(abs(x-y),initial=0.)),
                candidate_ids_equal=a['candidate_ids']==b['candidate_ids'],diagnostics_equal=a['diagnostics']==b['diagnostics'],
                semantic_metadata_equal=all(a[k]==b[k]for k in ['feature_names','feature_version','feature_contract_sha256','template_psf_sigma']),
                C596_scores_equal=bool(np.array_equal(sx,sy)),C596_max_abs_difference=float(np.max(abs(sx-sy),initial=0.)),C596_full_order_equal=bool(np.array_equal(orderx,ordery)),C596_top1_top3_equal=bool(np.array_equal(orderx[:3],ordery[:3])),
                matrix_sha256={k:hashlib.sha256(v.astype('<f4').tobytes()).hexdigest()for k,v in [('reference',xf),('prototype',yf)]},batch=b['batch_performance'],maxrss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
            result['speedup']=result['median_cpu_seconds']['reference']/result['median_cpu_seconds']['prototype'];results.append(result)
            print(case['case_id'],'rows',len(tracks),'speedup',round(result['speedup'],3),'F32bits',result['float32_different_bits'],'scoreorder',result['C596_full_order_equal'],flush=True)
        except Exception as exc:
            results.append(dict(case_id=case['case_id'],error=dict(type=type(exc).__name__,message=str(exc))));print('ERROR',case['case_id'],str(exc),flush=True)
        atomic(HERE/'benchmark-v1.json',dict(plan_sha256=digest(HERE/'benchmark-plan.json'),source_sha256=plan['source_sha256'],cpu_affinity=[cpu],results=results,scope='Bounded DEV performance prototype; no global equivalence or promotion claim'))
    if any(digest(p)!=s for p,s in plan['source_sha256'].items()):raise ValueError('producer/source changed during benchmark')
if __name__=='__main__':main()
