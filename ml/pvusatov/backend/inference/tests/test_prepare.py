from pathlib import Path
import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS


def write_fits(path, midpoint, *, omit=None, detector=6):
    w = WCS(naxis=2)
    w.wcs.ctype = ['RA---TAN', 'DEC--TAN']
    w.wcs.crval = [359.999, 5.]
    w.wcs.crpix = [16.5, 16.5]
    w.wcs.cdelt = [-6.15/3600, 6.15/3600]
    h = w.to_header()
    h['MJD-AVG'] = midpoint
    h['DATE-AVG'] = '2025-12-14T00:00:00'  # overridden below from physical time
    from astropy.time import Time
    h['DATE-AVG'] = Time(midpoint,format='mjd').isot
    h['DETECTOR'] = detector
    h['BUNIT'] = 'MJy/sr'
    image = np.ones((32,32), dtype='float32')
    flags = np.zeros((32,32),dtype='int32')
    flags[15,15] = 1 << 19
    hdus = [fits.PrimaryHDU()]
    for name,data in [('IMAGE',image),('FLAGS',flags),('VARIANCE',image),('ZODI',image*0)]:
        if name != omit:
            hdus.append(fits.ImageHDU(data,header=h,name=name))
    fits.HDUList(hdus).writeto(path)
    return {'frame_id':path.stem,'observation_id':path.stem,'path':str(path)}


def request(rows, policy='science'):
    return {'schema_version':1,'analysis_id':'test','source':{'kind':'fits','observations':rows,
            'region':{'right_ascension_deg':359.999,'declination_deg':5.,'width_arcmin':2,'height_arcmin':2}},
            'options':{'mask_policy':policy}}


def test_new_grid_is_north_up_and_ra_wraps():
    from ml_inference.prepare import make_grid
    grid = make_grid(359.999,5.,32,32,6.15)
    ra0,dec0 = grid.pixel_to_world_values(15.5,15.5)
    ra1,dec1 = grid.pixel_to_world_values(14.5,16.5)
    assert abs(ra0-359.999)<1e-8 and abs(dec0-5)<1e-8
    assert 0 <= ra1 < .01 and dec1 > dec0


def test_fits_sorted_deduplicated_and_masked(tmp_path):
    from ml_inference.prepare import prepare
    rows=[write_fits(tmp_path/f'f{i}.fits',61000+i/24) for i in [2,0,1]]
    stack=prepare(request(rows+[rows[0]]))
    assert [f['frame_id'] for f in stack.frames] == ['f0','f1','f2']
    assert np.allclose(stack.times,[0,1,2])
    assert np.isnan(stack.images[:,9:11,9:11]).any()
    motion=prepare(request(rows, 'motion'))
    assert np.isfinite(motion.images).sum()>np.isfinite(stack.images).sum()
    assert motion.outlier.any()


def test_missing_required_hdu_is_safe_error(tmp_path):
    from ml_inference.prepare import prepare
    from ml_inference.contracts import InferenceError
    rows=[write_fits(tmp_path/f'f{i}.fits',61000+i/24,omit='VARIANCE' if i==1 else None) for i in range(3)]
    with pytest.raises(InferenceError,match='required'):
        prepare(request(rows))


def test_detector_mismatch_rejected(tmp_path):
    from ml_inference.prepare import prepare
    from ml_inference.contracts import InferenceError
    rows=[write_fits(tmp_path/f'f{i}.fits',61000+i/24,detector=3 if i==1 else 6) for i in range(3)]
    with pytest.raises(InferenceError,match='detector'):
        prepare(request(rows))


def test_npz_oversized_and_pickle_rejected(tmp_path):
    from ml_inference.prepare import prepare
    from ml_inference.contracts import InferenceError
    path=tmp_path/'oversized.npz'
    np.savez_compressed(path, images=np.zeros((33,3,3)))
    req={'schema_version':1,'analysis_id':'test','source':{'kind':'preset','preset_id':'comet-d6','path':str(path)}}
    with pytest.raises(InferenceError): prepare(req)
    np.savez_compressed(path, images=np.array([object()],dtype=object))
    with pytest.raises(InferenceError): prepare(req)


def test_legacy_fixture_keeps_recorded_south_up_grid():
    from ml_inference.prepare import prepare
    stack=prepare({'schema_version':1,'analysis_id':'x','source':{'kind':'preset','preset_id':'comet-d6'}})
    _,a=stack.grid.pixel_to_world_values(120,60)
    _,b=stack.grid.pixel_to_world_values(120,61)
    assert b<a
    assert stack.images.shape==(4,144,256)


def test_distinct_ids_at_same_midpoint_do_not_count_as_independent(tmp_path):
    from ml_inference.prepare import prepare
    from ml_inference.contracts import InferenceError
    rows=[write_fits(tmp_path/f'f{i}.fits',61000+(i//2)/24) for i in range(3)]
    with pytest.raises(InferenceError,match='independent'):
        prepare(request(rows))


def test_inconsistent_midpoint_metadata_rejected(tmp_path):
    from ml_inference.prepare import prepare
    from ml_inference.contracts import InferenceError
    rows=[write_fits(tmp_path/f'f{i}.fits',61000+i/24) for i in range(3)]
    with fits.open(rows[0]['path'],mode='update') as hdus:
        hdus['IMAGE'].header['DATE-AVG']='2025-01-01T00:00:00'
    with pytest.raises(InferenceError,match='midpoint'):
        prepare(request(rows))


def test_expanded_archive_is_bounded_before_arrays_load(tmp_path):
    from ml_inference.prepare import prepare
    from ml_inference.contracts import InferenceError
    import zipfile
    path=tmp_path/'bomb.npz'
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        with archive.open('ignored.npy','w') as entry:
            for _ in range(161): entry.write(bytes(1024*1024))
    req={'schema_version':1,'analysis_id':'test','source':{'kind':'preset','preset_id':'comet-d6','path':str(path)}}
    with pytest.raises(InferenceError,match='Expanded'):
        prepare(req)


def test_unsigned_fits_flags_do_not_fail_memory_mapping(tmp_path):
    from ml_inference.prepare import prepare
    rows=[write_fits(tmp_path/f'f{i}.fits',61000+i/24) for i in range(3)]
    for row in rows:
        with fits.open(row['path']) as hdus:
            copies=fits.HDUList([h.copy() for h in hdus])
        copies['FLAGS'].data=copies['FLAGS'].data.astype(np.uint32)
        copies.writeto(row['path'],overwrite=True)
    stack=prepare(request(rows))
    assert len(stack.frames)==3


def test_fits_physical_observation_id_deduplicates_processing_versions(tmp_path):
    from ml_inference.prepare import prepare
    rows=[write_fits(tmp_path/f'cached-hash-{i}.fits',61000+i/24) for i in range(3)]
    for i,row in enumerate(rows):
        with fits.open(row['path'],mode='update') as hdus:
            hdus['IMAGE'].header['OBSID']=f'physical-observation-{i}'
        row['observation_id']=f'untrusted-cache-identity-{i}'
    duplicate=write_fits(tmp_path/'different-processing-hash.fits',61000)
    with fits.open(duplicate['path'],mode='update') as hdus:
        hdus['IMAGE'].header['OBSID']='physical-observation-0'
    duplicate['observation_id']='different-cache-identity'
    stack=prepare(request([rows[2],rows[0],duplicate,rows[1]]))
    assert len(stack.frames)==3
    assert [f['frame_id'] for f in stack.frames]==['cached-hash-0','cached-hash-1','cached-hash-2']
    assert [f['observation_id'] for f in stack.frames]==['physical-observation-0:D6','physical-observation-1:D6','physical-observation-2:D6']
    assert all(f['observation_id_source']=='fits:OBSID' for f in stack.frames)
    assert 'duplicate_observations_deduplicated' in stack.warnings


def test_manifest_archive_provenance_is_separate_from_software_version(tmp_path):
    import hashlib
    import json
    from ml_inference.prepare import prepare
    rows=[write_fits(tmp_path/f'cached-frame-{i}.fits',61000+i/24) for i in range(3)]
    for i,row in enumerate(rows):
        with fits.open(row['path'],mode='update') as hdus:
            hdus[0].header['VERSION']='7.0.5'
            hdus['IMAGE'].header['OBS_ID']=f'2025W19_2B_0346_{i+1}'
        row.update(release='DR1',processing_version='l2b-v27-2026-198',
                   access_url=f'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/native-{i}.fits')
    stack=prepare(request(rows))
    frame=stack.frames[0]
    assert frame['release']=='DR1'
    assert frame['processing_version']=='l2b-v27-2026-198'
    assert frame['software_version']=='7.0.5'
    assert frame['access_url']==rows[0]['access_url']
    assert frame['sha256']==hashlib.sha256(Path(rows[0]['path']).read_bytes()).hexdigest()
    assert frame['observation_id_source']=='fits:OBS_ID'
    assert str(tmp_path) not in json.dumps(stack.frames)+json.dumps(stack.provenance)


def test_software_version_cannot_become_product_version(tmp_path):
    from ml_inference.prepare import prepare
    rows=[write_fits(tmp_path/f'frame-{i}.fits',61000+i/24) for i in range(3)]
    for row in rows:
        with fits.open(row['path'],mode='update') as hdus: hdus[0].header['VERSION']='7.0.5'
    frame=prepare(request(rows)).frames[0]
    assert frame['software_version']=='7.0.5'
    assert frame['processing_version']=='unknown'
    assert frame['observation_id_source']=='manifest:observation_id'


def test_original_filename_can_supply_archive_processing_version(tmp_path):
    from ml_inference.prepare import prepare
    rows=[write_fits(tmp_path/f'level2_2025W19_2B_0346_{i+1}D6_spx_l2b-v27-2026-198.fits',61000+i/24) for i in range(3)]
    frame=prepare(request(rows)).frames[0]
    assert frame['processing_version']=='l2b-v27-2026-198'


def test_trusted_checksum_is_checked_against_input_bytes(tmp_path):
    from ml_inference.prepare import prepare
    from ml_inference.contracts import InferenceError
    rows=[write_fits(tmp_path/f'frame-{i}.fits',61000+i/24) for i in range(3)]
    rows[0]['sha256']='0'*64
    with pytest.raises(InferenceError,match='checksum'):
        prepare(request(rows))


def test_native_rotated_translated_sip_wcs_preserves_injected_sky_motion(tmp_path):
    """Ignoring any frame WCS must break recovery of the same physical sky track."""
    from astropy.time import Time
    from astropy.wcs import Sip
    from ml_inference.pipeline import run
    target=WCS(naxis=2)
    target.wcs.ctype=['RA---TAN','DEC--TAN']
    target.wcs.crval=[359.999,5.]
    target.wcs.crpix=[10.5,10.5]
    target.wcs.cdelt=[-6.15/3600,6.15/3600]
    yy,xx=np.indices((96,96)); rng=np.random.default_rng(90817)
    expected=np.array([[5.,6.],[8.,8.],[11.,10.],[14.,12.]])
    rows=[]
    for i,angle in enumerate([0.,19.,-28.,37.]):
        native=WCS(naxis=2)
        native.wcs.ctype=['RA---TAN-SIP','DEC--TAN-SIP']
        native.wcs.crval=[359.999,5.]
        native.wcs.crpix=[48.5+2*i,48.5-i]
        theta=np.deg2rad(angle)
        native.wcs.cd=np.array([[-np.cos(theta),np.sin(theta)],[np.sin(theta),np.cos(theta)]])*6.15/3600
        a=np.zeros((3,3));b=np.zeros((3,3))
        a[2,0]=2e-5; a[1,1]=-1e-5; b[0,2]=-1.5e-5; b[1,1]=1e-5
        native.sip=Sip(a,b,None,None,native.wcs.crpix)
        ra,dec=target.pixel_to_world_values(*expected[i])
        x,y=native.world_to_pixel_values(ra,dec)
        image=rng.normal(0,.25,(96,96))+35*np.exp(-((xx-x)**2+(yy-y)**2)/(2*1.2**2))
        header=native.to_header(relax=True)
        header['MJD-AVG']=61000+i/24;header['DATE-AVG']=Time(61000+i/24,format='mjd').isot
        header['OBSID']=f'native-sip-observation-{i}';header['DETECTOR']=6;header['BUNIT']='MJy/sr'
        path=tmp_path/f'frame-{i}.fits'
        fits.HDUList([fits.PrimaryHDU(),fits.ImageHDU(image.astype('float32'),header=header,name='IMAGE'),
                      fits.ImageHDU(np.zeros((96,96),dtype='uint32'),name='FLAGS'),
                      fits.ImageHDU(np.ones((96,96),dtype='float32'),name='VARIANCE'),
                      fits.ImageHDU(np.zeros((96,96),dtype='float32'),name='ZODI')]).writeto(path)
        rows.append(dict(frame_id=f'frame-{i}',path=str(path)))
    result=run(request(rows),tmp_path/'result')
    matches=[candidate for candidate in result['candidates'] if len(candidate['detections'])==4
             and np.max(np.linalg.norm(np.array([[d['x'],d['y']] for d in candidate['detections']])-expected,axis=1))<=1.]
    assert matches
    assert all(d['observation_id']==f'native-sip-observation-{i}:D6' for i,d in enumerate(matches[0]['detections']))
    assert all(frame['width']==20 and frame['height']==20 for frame in result['frames'])
