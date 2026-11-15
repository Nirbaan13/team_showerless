"""Independent native IMAGE overlays for development-only physics validation.

No old evaluator sampler/projector is used to construct these responses. Amplitude
is a discrete native-pixel sum in IMAGE surface-brightness units, not calibrated
point-source flux. No photon noise or variance increment is invented.
"""
from pathlib import Path
import hashlib,math
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates

SOURCE_BIT=1<<21;OUTLIER_BIT=1<<19

def digest(path):
    sha=hashlib.sha256()
    with Path(path).open('rb')as f:
        for block in iter(lambda:f.read(1048576),b''):sha.update(block)
    return sha.hexdigest()

def guard_source(path,allowed_root):
    path=Path(path).resolve();allowed_root=Path(allowed_root).resolve()
    if any(part.lower().startswith(('quarantine','v4-final'))for part in path.parts):raise ValueError('quarantine source access forbidden')
    if not path.is_relative_to(allowed_root):raise ValueError('Source is outside authorized development root')
    return path

def sample_native_epsf(epsf,x,y,shape,oversampling_x,oversampling_y):
    """Sample on the native integer lattice; normalize BEFORE crop/mask losses."""
    epsf=np.asarray(epsf,dtype=np.float64);ox=float(oversampling_x);oy=float(oversampling_y)
    if epsf.ndim!=2 or not np.isfinite(epsf).all()or not all(math.isfinite(v)for v in [x,y,ox,oy])or min(ox,oy)<=0:raise ValueError('Invalid native ePSF/phase')
    cy,cx=(np.array(epsf.shape)-1)/2
    # Infinite-lattice compact support is independent of the image footprint.
    ix=np.arange(math.floor(x-cx/ox),math.ceil(x+cx/ox)+1,dtype=float)
    iy=np.arange(math.floor(y-cy/oy),math.ceil(y+cy/oy)+1,dtype=float)
    lattice_y,lattice_x=np.meshgrid(iy,ix,indexing='ij')
    weights=map_coordinates(epsf,[cy+(lattice_y-y)*oy,cx+(lattice_x-x)*ox],order=1,mode='constant',cval=0.)
    normalization=float(weights.sum())
    if not math.isfinite(normalization)or normalization<=0:raise ValueError('Native ePSF normalization is not positive')
    yy,xx=np.indices(shape,dtype=float)
    response=map_coordinates(epsf,[cy+(yy-y)*oy,cx+(xx-x)*ox],order=1,mode='constant',cval=0.)/normalization
    return response,dict(untruncated_lattice_sum=normalization,native_crop_response_sum=float(response.sum()),native_xy=[float(x),float(y)],fractional_phase_xy=[float(x%1),float(y%1)],oversampling_xy=[ox,oy])

def native_response(path,sky_ra_dec,*,allowed_root):
    path=guard_source(path,allowed_root)
    with fits.open(path,memmap=False)as hdus:
        header=hdus[0].header.copy();header.update(hdus['IMAGE'].header);image=np.asarray(hdus['IMAGE'].data,dtype=np.float64)
        if int(header['DETECTOR'])not in [1,2,3]or hdus['EPSF'].header['DETCOORD']!='sky'or hdus['IMAGE'].header.get('DETCOORD')!='sky':raise ValueError('Unsupported native ePSF frame')
        celestial=WCS(header).celestial;x,y=map(float,celestial.world_to_pixel_values(*sky_ra_dec))
        # Alternate A is the documented linear cutout→parent pixel system; its
        # core WCS transform intentionally excludes celestial SIP corrections.
        alternate=fits.Header()
        for key in ['CTYPE1','CTYPE2','CUNIT1','CUNIT2','CRPIX1','CRPIX2','CRVAL1','CRVAL2','CDELT1','CDELT2','CD1_1','CD1_2','CD2_1','CD2_2','PC1_1','PC1_2','PC2_1','PC2_2']:
            if key+'A'in header:alternate[key]=header[key+'A']
        parent_x,parent_y=map(float,WCS(alternate,naxis=2).wcs_pix2world([[x,y]],0)[0])
        table=hdus['EPSF'].data
        distance=(np.asarray(table['XCENTER'],float)-parent_x)**2+(np.asarray(table['YCENTER'],float)-parent_y)**2
        zone=int(np.argmin(distance));row=table[zone]
        response,meta=sample_native_epsf(np.asarray(row['EPSF'],float),x,y,image.shape,hdus['EPSF'].header['OVSMPX'],hdus['EPSF'].header['OVSMPY'])
        signal=image-np.asarray(hdus['ZODI'].data,float);flags=np.asarray(hdus['FLAGS'].data,np.int64);variance=np.asarray(hdus['VARIANCE'].data,float)
        good=((flags&~(SOURCE_BIT|OUTLIER_BIT))==0)&np.isfinite(signal)&np.isfinite(variance)&(variance>0)
        meta.update(zone=zone,bin_xy=[int(row['BINX']),int(row['BINY'])],wavelength_um=float(row['CWAVE']),source_parent_xy=[parent_x,parent_y],
            sky_ra_dec=list(map(float,sky_ra_dec)),native_motion_good_response_sum=float(response[good].sum()),image_unit=header.get('BUNIT'),variance_unit=hdus['VARIANCE'].header.get('BUNIT'),
            has_sip=celestial.sip is not None,parent_linear_formula_residual_xy=[parent_x-(1+x-header['CRPIX1A']),parent_y-(1+y-header['CRPIX2A'])])
    return response,meta

def _equal_array(a,b):
    if a is None or b is None:return a is b
    if a.shape!=b.shape:return False
    if a.dtype.names:
        return a.dtype.names==b.dtype.names and all(_equal_array(np.asarray(a[name]),np.asarray(b[name]))for name in a.dtype.names)
    if a.dtype.kind=='O':return all(_equal_array(np.asarray(x),np.asarray(y))for x,y in zip(a.flat,b.flat))
    return np.array_equal(a,b,equal_nan=True)if a.dtype.kind in'fc'else np.array_equal(a,b)

def write_derivative(source,target,response,amplitude,*,allowed_root):
    source=guard_source(source,allowed_root);target=Path(target)
    if source==target.resolve()or target.exists():raise ValueError('Refusing to replace source/existing derivative')
    original_sha=digest(source);response=np.asarray(response,dtype=np.float64)
    if not math.isfinite(amplitude)or amplitude<0 or not np.isfinite(response).all():raise ValueError('Invalid deterministic overlay')
    with fits.open(source,memmap=False)as original:
        clone=fits.HDUList([hdu.copy()for hdu in original])
        if response.shape!=original['IMAGE'].data.shape:raise ValueError('Native overlay dimensions differ')
        clone['IMAGE'].data=np.asarray(original['IMAGE'].data,dtype=np.float64)+amplitude*response
        for key in ['BSCALE','BZERO']:clone['IMAGE'].header.remove(key,ignore_missing=True,remove_all=True)
        clone[0].header['V4DERIV']=True
        clone[0].header['V4ORIG']=original_sha
        clone[0].header.add_history('V4 research-only deterministic native ePSF IMAGE overlay; no photon noise.')
        clone[0].header.add_history('VARIANCE, FLAGS, ZODI, EPSF and physical OBSID preserved; see external manifest.')
        for hdu in clone:
            for key in ['CHECKSUM','DATASUM']:hdu.header.remove(key,ignore_missing=True,remove_all=True)
        clone.writeto(target,checksum=True,output_verify='exception');clone.close()
        with fits.open(target,memmap=False,checksum=True)as derived:
            if derived['IMAGE'].header['BITPIX']!=-64:raise ValueError('Derivative IMAGE must be true float64')
            preserved=[]
            for index,(a,b)in enumerate(zip(original,derived)):
                if a.name!=b.name:raise ValueError('Derivative extension layout changed')
                if a.name!='IMAGE':
                    if not _equal_array(a.data,b.data):raise ValueError('Non-IMAGE array changed: '+a.name)
                    preserved.append(a.name)
                if b.verify_checksum()!=1 or b.verify_datasum()!=1:raise ValueError('Derivative FITS checksum failure')
            for key in original['IMAGE'].header:
                if key in ['BITPIX','BSCALE','BZERO','CHECKSUM','DATASUM','COMMENT','HISTORY']:continue
                if original['IMAGE'].header[key]!=derived['IMAGE'].header[key]:raise ValueError('Protected IMAGE/WCS header changed: '+key)
            for key in ['OBSID','DETECTOR','MJD-AVG','DATE-AVG']:
                if key in original[0].header and original[0].header[key]!=derived[0].header[key]:raise ValueError('Physical original identity changed')
    if digest(source)!=original_sha:raise ValueError('Original archive file changed')
    return dict(original_path=str(source),original_sha256=original_sha,derivative_path=str(target),derivative_sha256=digest(target),
        derivative_bytes=target.stat().st_size,image_bitpix=-64,amplitude_native_discrete_sum_MJy_per_sr=float(amplitude),
        preserved_nonimage_hdus=preserved,all_derivative_checksums_valid=True,added_photon_noise=False,variance_updated=False,
        archive_bytes_claimed=False,units='MJy/sr discrete native-pixel sum; not calibrated point-source flux')
