"""Controlled FITS only: usable-count thresholds and unchanged bad-input errors."""
from pathlib import Path
import hashlib,importlib.util,json,sys,tempfile
import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
OWN=Path(__file__).resolve().parent;NS=OWN.parents[4];BACKEND=NS/'backend/inference/ml_inference';RUNTIME=NS/'releases/v4/runtime/ml_inference'
def load(name,path,package=False):
 spec=importlib.util.spec_from_file_location(name,path,submodule_search_locations=[str(path.parent)]if package else None);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m

def main():
 modules={}
 for label,directory in [('old',BACKEND),('new',RUNTIME)]:
  load('toy_'+label,directory/'__init__.py',True);load('toy_'+label+'.contracts',directory/'contracts.py');modules[label]=load('toy_'+label+'.prepare',directory/'prepare.py')
 results=[]
 with tempfile.TemporaryDirectory(prefix='v4-coverage-toy-')as d:
  d=Path(d)
  def observation(index,empty=False,bad=None):
   w=WCS(naxis=2);w.wcs.ctype=['RA---TAN','DEC--TAN'];w.wcs.crval=[20.,5.];w.wcs.crpix=[16.5,16.5];w.wcs.cdelt=[-6.15/3600,6.15/3600];h=w.to_header();h['MJD-AVG']=61000+index/24;h['DATE-AVG']=Time(h['MJD-AVG'],format='mjd').isot;h['DETECTOR']=1;h['BUNIT']='MJy/sr';h['OBSID']='toy-'+str(index)
   if bad=='date':h['DATE-AVG']='invalid-date'
   signal=np.random.default_rng(3800910+index).normal(size=(32,32)).astype(np.float32);flags=np.full((32,32),1 if empty else 0,dtype=np.int32);arrays=[('IMAGE',signal),('FLAGS',flags),('VARIANCE',np.ones_like(signal)),('ZODI',np.zeros_like(signal))]
   if bad=='hdu':arrays=[p for p in arrays if p[0]!='VARIANCE']
   if bad=='shape':arrays=[(n,a[:20]if n=='VARIANCE'else a)for n,a in arrays]
   p=d/f'{index}-{empty}-{bad}.fits';fits.HDUList([fits.PrimaryHDU()]+[fits.ImageHDU(a,header=h,name=n)for n,a in arrays]).writeto(p,overwrite=True);return dict(path=str(p),frame_id=p.stem)
  def request(rows,min_epochs=3):return dict(schema_version=1,analysis_id='coverage-toy-validation',source=dict(kind='fits',observations=rows,region=dict(right_ascension_deg=20.,declination_deg=5.,width_arcmin=2.,height_arcmin=2.)),options=dict(min_epochs=min_epochs))
  for usable in range(4):
   rows=[observation(i,empty=i>=usable)for i in range(4)]
   try:
    stack=modules['new'].prepare(request(rows));assert usable==3 and len(stack.frames)==4 and np.isnan(stack.images[3]).all();results.append(dict(case='usable_'+str(usable),accepted=True,physical_epochs=len(stack.frames),usable_epochs=int(np.isfinite(stack.images).any(axis=(1,2)).sum())))
   except Exception as e:
    assert usable<3 and getattr(e,'code',None)=='insufficient_observations';results.append(dict(case='usable_'+str(usable),accepted=False,error_code=e.code))
  for bad in ['hdu','shape','date']:
   rows=[observation(i,bad=bad if i==0 else None)for i in range(4)];codes=[]
   for label in ['old','new']:
    try:modules[label].prepare(request(rows));raise AssertionError('Malformed input accepted')
    except Exception as e:assert getattr(e,'code',None)=='invalid_fits';codes.append(e.code)
   results.append(dict(case='malformed_'+bad,old_and_new_error_codes=codes))
 x=dict(status='PASS',scope='Temporary controlled FITS only; no real/FINAL pixels, detections or models',cases=results,prepare_source_sha256=hashlib.sha256((RUNTIME/'prepare.py').read_bytes()).hexdigest(),scratch_deleted=not d.exists());(OWN/'toy-validation-proof.json').write_text(json.dumps(x,indent=2)+'\n');print(json.dumps(x,indent=2))
if __name__=='__main__':main()
