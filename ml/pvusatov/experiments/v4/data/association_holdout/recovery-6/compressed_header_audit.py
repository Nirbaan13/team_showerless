"""Manual FITS header-only logical-dimension adapter for standard ZIMAGE tiled compression."""
from pathlib import Path
import argparse,datetime,hashlib,json,types
OWN=Path(__file__).resolve().parent

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def ref(p):return dict(path=str(p.resolve()),sha256=sha(p))
def checked(v):p=Path(v['path']);assert sha(p)==v['sha256'];return p
def exact(name,v):
    p=checked(v);m=types.ModuleType(name);m.__file__=str(p);exec(compile(p.read_bytes(),str(p),'exec'),m.__dict__);return m
def write(p,v):
    if p.exists():raise ValueError('Immutable evidence exists: '+str(p))
    p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')

def inspect(path,expected_obsid,expected_detector,base_ref):
    base=exact('original_header_block_scanner',base_ref);path=Path(path)
    with path.open('rb')as f:hdus=base.scan(f,path.stat().st_size)
    byname={h['name']:h for h in hdus};assert{'IMAGE','FLAGS','VARIANCE','ZODI','EPSF','WCS-WAVE'}.issubset(byname);compressed=[]
    def shape(name):
        h=byname[name]['header']
        if h.get('ZIMAGE')is True:
            assert h['XTENSION']=='BINTABLE'and h['ZNAXIS']==2 and h['ZBITPIX']in[8,16,32,64,-32,-64]
            assert h['ZCMPTYPE']in['RICE_1','GZIP_1','GZIP_2','PLIO_1','HCOMPRESS_1']and int(h['ZNAXIS1'])>0 and int(h['ZNAXIS2'])>0
            result=[int(h['ZNAXIS2']),int(h['ZNAXIS1'])];compressed.append(dict(name=name,physical_table_dimensions=[h['NAXIS2'],h['NAXIS1']],logical_image_dimensions=result,ZIMAGE=True,ZBITPIX=h['ZBITPIX'],ZCMPTYPE=h['ZCMPTYPE'],tile_dimensions=[h.get('ZTILE2',1),h.get('ZTILE1',h['ZNAXIS1'])]));return result
        assert h['NAXIS']==2;return[int(h['NAXIS2']),int(h['NAXIS1'])]
    native_shape=shape('IMAGE')
    for name in ['FLAGS','VARIANCE','ZODI']:assert shape(name)==native_shape,'Logical native image/mask/variance/ZODI dimensions differ'
    combined={**hdus[0]['header'],**byname['IMAGE']['header']};assert combined.get('OBSID')==expected_obsid and int(combined['DETECTOR'])==expected_detector and expected_detector in[1,2,3];assert byname['EPSF']['header'].get('DETCOORD')=='sky'
    assert all(k in combined for k in ['CTYPE1','CTYPE2','CRVAL1','CRVAL2','CRPIX1','CRPIX2','MJD-AVG'])
    return dict(header_only=True,pixels_opened=False,native_orientation_preserved=True,hdu_names=[h['name']for h in hdus],native_shape=native_shape,detector=expected_detector,physical_obsid=combined['OBSID'],midpoint_mjd=combined['MJD-AVG'],epsf_detcoord='sky',epsf_oversampling=[byname['EPSF']['header'].get('OVSMPX'),byname['EPSF']['header'].get('OVSMPY')],header_layout=[{k:h[k]for k in ['name','header_offset','header_bytes','data_bytes','header_sha256']}for h in hdus],wcs={k:combined.get(k)for k in ['CTYPE1','CTYPE2','CRVAL1','CRVAL2','CRPIX1','CRPIX2','CD1_1','CD1_2','CD2_1','CD2_2','CDELT1','CDELT2']},compressed_image_header_evidence=compressed,engineering_interpretation='FITS ZIMAGE logical dimensions from ZNAXISn; physical BINTABLE geometry remains in original block-layout hashes; no decompression')

def declare():
    plan=read(OWN/'transport-plan.json');transfer=read(OWN/'full-mef-transfer.json');item=transfer['product'];assert item['bytes']==59123520 and sha(item['path'])==item['sha256']
    amendment=dict(declared_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='Header-engineering-only adapter for standard tiled-compressed image logical dimensions. No eligibility/scientificruntime/array/decompression/quality change.',source=ref(Path(__file__)),original_header_source=plan['sources']['headers'],historical_failed_header_audit=ref(OWN/'full-mef-transfer.json'),artifact_sha256=item['sha256'],references=['https://fits.gsfc.nasa.gov/registry/tilecompression/tilecompression2.1.pdf'],rule='IfXTENSION=BINTABLE andZIMAGE=T, logicalimagegeometryusesZNAXIS/ZNAXISn/ZBITPIX; validateFLAGSlogicalshapeagainstIMAGE/VARIANCE/ZODI, preservephysicalheaderlayout/hash. ApplyuniformlytobothauthorizedfullMEFs.',pixels_opened=False,inference_authorized=False)
    write(OWN/'compressed-header-engineering-amendment.json',amendment);print(json.dumps(dict(engineering_amendment_sha256=sha(OWN/'compressed-header-engineering-amendment.json'),source_sha256=sha(Path(__file__)))),flush=True)

def verify09():
    amendment=read(OWN/'compressed-header-engineering-amendment.json');checked(amendment['source']);old=read(checked(amendment['historical_failed_header_audit']));item=dict(old['product']);assert sha(item['path'])==item['sha256'];item['header']=inspect(item['path'],item['obs_id'],3,amendment['original_header_source']);mid=item['header']['midpoint_mjd'];assert item['t_min_mjd']-.000002<=mid<=item['t_max_mjd']+.000002
    item.pop('error',None);item.update(status='HEADER_VERIFIED_QUARANTINED',midpoint_mjd=mid,midpoint_utc=datetime.datetime.fromtimestamp((mid-40587)*86400,datetime.timezone.utc).isoformat(),processing_identity_evidence=dict(original_frozen_SIA_artifact_url=item['source_url'],processing_version_path=Path(item['source_url']).parent.parent.name,artifact_basename=Path(item['source_url']).name,header_physical_id_and_detector_verified=True,header_midpoint_verified=True),full_vs_cutout_byte_parity_claim=False)
    write(OWN/'full-mef-logical-header-verification.json',dict(status=item['status'],engineering_amendment_ref=ref(OWN/'compressed-header-engineering-amendment.json'),historical_transfer_ref=amendment['historical_failed_header_audit'],product=item,pixels_opened=False,inference_authorized=False));print(json.dumps(dict(status=item['status'],obs_id=item['obs_id'],shape=item['header']['native_shape'],compressed=item['header']['compressed_image_header_evidence'])),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['declare','verify09']);args=p.parse_args();globals()[args.command]()
