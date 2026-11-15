"""Temp-only bootstrap source/PYC alignment probe; no science or FITS calls."""
from pathlib import Path
import hashlib,json,os,py_compile,subprocess,sys,tempfile
OWN=Path(__file__).resolve().parent;EVALUATION=OWN.parents[1]/'evaluation'
def main():
    frozen_source=(EVALUATION/'freeze.py').read_text();old=frozen_source.replace('psf_sigma=.8','psf_sigma=.7',1)
    if old==frozen_source:raise ValueError('Current source changed; inspect bootstrap repro fixture')
    rows=[]
    for runner in ['run_native','run_synthetic']:
        with tempfile.TemporaryDirectory(prefix='v4-review-bootstrap-')as d:
            directory=Path(d);p=directory/'freeze.py';p.write_text(old);os.utime(p,(1700000000,1700000000));py_compile.compile(str(p),doraise=True);p.write_text(frozen_source);os.utime(p,(1700000000,1700000000));(directory/(runner+'.py')).write_bytes((EVALUATION/(runner+'.py')).read_bytes())
            code=f"import json,sys,{runner} as r; print(json.dumps(dict(executed_profile_sigma=r.validate_freeze.__globals__['PROFILE']['psf_sigma'],pixel_modules_imported=any(n in sys.modules for n in ['astropy.io.fits','ml_inference.prepare']))))"
            result=subprocess.run([sys.executable,'-B','-c',code],cwd=directory,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,check=True)
            record=json.loads(result.stdout);record.update(runner=runner,runner_source_sha256=hashlib.sha256((EVALUATION/(runner+'.py')).read_bytes()).hexdigest(),current_freeze_source_sha256=hashlib.sha256(frozen_source.encode()).hexdigest(),current_source_profile_sigma=.8,source_and_execution_agree=record['executed_profile_sigma']==.8);rows.append(record)
    x=dict(scope='TEMP COPIES ONLY; no actual root sources modified, no FITS/pixels/models/final data',python=sys.version,results=rows);print(json.dumps(x,indent=2))
    (OWN/'bootstrap-repro.json').write_text(json.dumps(x,indent=2)+'\n')
if __name__=='__main__':main()
