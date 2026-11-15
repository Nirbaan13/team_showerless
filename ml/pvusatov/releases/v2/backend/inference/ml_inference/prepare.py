"""FITS registration adapted from Ivan's 2b6dc43 science/motion/prepare_fits.py.

Legacy benchmark grids have decreasing DEC with y; native grids are north-up.
Evaluation labels such as expected_xy are intentionally never loaded.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import re
from urllib.parse import urlsplit
import zipfile

import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates
from .contracts import InferenceError, validate_request

SOURCE_BIT = 1 << 21
OUTLIER_BIT = 1 << 19
BLOOM_BIT = 1 << 26
PRESETS = ('comet-d6','comet-d2','vesta-d6','vesta-d3')
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_EXPANDED = 160 * 1024 * 1024


@dataclass
class PreparedStack:
    images: np.ndarray
    times: np.ndarray
    frames: list
    grid: WCS
    outlier: np.ndarray
    bloom: np.ndarray | None
    pixel_scale: float
    warnings: list
    provenance: dict


def make_grid(ra, dec, width, height, pixel_scale, *, legacy=False):
    grid = WCS(naxis=2)
    grid.wcs.ctype = ['RA---TAN','DEC--TAN']
    grid.wcs.crval = [ra,dec]
    grid.wcs.crpix = [(width+1)/2,(height+1)/2]
    grid.wcs.cdelt = [-pixel_scale/3600,(-1 if legacy else 1)*pixel_scale/3600]
    return grid


def _shape(images):
    if images.ndim != 3 or not 3 <= images.shape[0] <= 32 or not 1 <= min(images.shape[1:]) <= max(images.shape[1:]) <= 512:
        raise InferenceError('workload_limit','Use 3 to 32 frames on a grid no larger than 512 by 512')
    if np.isinf(images).any():
        raise InferenceError('invalid_input','Infinite image measurements are unsupported')


def _ordered(images, dates, ids, frame_ids, outlier, bloom):
    if not len(dates)==len(ids)==len(frame_ids)==len(images):
        raise InferenceError('invalid_input','Frame metadata must match image count')
    try:
        mjd=np.asarray(Time([str(d).removesuffix('Z') for d in dates],format='isot',scale='utc').mjd)
    except (ValueError,TypeError):
        raise InferenceError('invalid_input','Exposure midpoint dates must be valid UTC timestamps') from None
    order=np.argsort(mjd,kind='stable')
    keep=[]; seen={}; frame_seen=set()
    for index in order:
        identifier=str(ids[index])
        if not identifier or len(identifier)>256 or not str(frame_ids[index]) or len(str(frame_ids[index]))>256:
            raise InferenceError('invalid_input','Frame identifiers must be bounded nonempty strings')
        if identifier in seen:
            if abs(seen[identifier]-mjd[index])>1e-8:
                raise InferenceError('invalid_input','Repeated observation has inconsistent midpoint')
            continue
        if str(frame_ids[index]) in frame_seen:
            raise InferenceError('invalid_input','Frame identifiers must be unique')
        seen[identifier]=mjd[index]; frame_seen.add(str(frame_ids[index])); keep.append(int(index))
    mjd=mjd[keep]
    if len(keep)<3 or not np.isfinite(mjd).all() or np.any(np.diff(mjd)<=1e-10):
        raise InferenceError('insufficient_observations','At least three independent observations with distinct physical midpoints are required')
    frames=[dict(frame_id=str(frame_ids[i]),observation_id=str(ids[i]),midpoint_utc=str(Time(mjd[j],format='mjd').isot)+'Z',
                 midpoint_mjd=float(mjd[j])) for j,i in enumerate(keep)]
    return images[keep],(mjd-mjd[0])*24,frames,outlier[keep],None if bloom is None else bloom[keep]


def _preset(source, options):
    preset=source.get('preset_id')
    if preset not in PRESETS:
        raise InferenceError('invalid_preset','Unknown real-data preset')
    path=Path(source.get('path') or Path(__file__).resolve().parents[1]/'fixtures'/f'{preset}.npz')
    try:
        if path.stat().st_size > MAX_ARCHIVE:
            raise InferenceError('workload_limit','Compressed input exceeds the supported size')
        with zipfile.ZipFile(path) as archive:
            members=archive.infolist()
            if len(members)>32 or sum(x.file_size for x in members)>MAX_EXPANDED or any(x.file_size>MAX_EXPANDED for x in members):
                raise InferenceError('workload_limit','Expanded input exceeds the supported size')
        with np.load(path,allow_pickle=False) as data:
            images=np.asarray(data['images'],dtype=float)
            _shape(images)
            dates=np.array(data['dates']); ids=np.array(data['observation_ids'])
            outlier=np.asarray(data['outlier'],dtype=bool) if 'outlier' in data else np.zeros(images.shape,dtype=bool)
            bloom=np.asarray(data['bloom'],dtype=bool) if 'bloom' in data else None
            center=np.asarray(data['center_deg'],dtype=float)
            scale=float(data['pixel_scale_arcsec'])
            retains=bool(data['retain_outliers']) if 'retain_outliers' in data else False
            if center.shape!=(2,) or not np.isfinite(center).all() or not 0<=center[0]<360 or not -90<center[1]<90 or not np.isfinite(scale) or not 0<scale<=60:
                raise InferenceError('invalid_input','Invalid registered sky grid')
            if outlier.shape!=images.shape or (bloom is not None and bloom.shape!=images.shape):
                raise InferenceError('invalid_input','Mask dimensions must match image dimensions')
    except InferenceError:
        raise
    except (OSError,KeyError,ValueError,zipfile.BadZipFile,TypeError):
        raise InferenceError('invalid_input','Unable to read the registered numeric input') from None
    if options['mask_policy']=='science':
        images=np.where(outlier,np.nan,images)
    images,times,frames,outlier,bloom=_ordered(images,dates,ids,ids,outlier,bloom)
    detector=int(preset[-1])
    for frame in frames:
        frame.update(detector=detector,units='MJy/sr',release='qr2' if preset.startswith('comet') else 'dr1',
                     processing_version='l2b-v20-2025-349' if preset.startswith('comet') else 'l2b-v27-2026-226')
    grid=make_grid(*center,images.shape[2],images.shape[1],scale,legacy=True)
    warnings=['selected_development_case','legacy_decreasing_declination_grid']
    if retains and options['mask_policy']=='motion': warnings.append('outlier_measurements_retained')
    return PreparedStack(images,times,frames,grid,outlier,bloom,scale,warnings,
                         {'source_kind':'preset','preset_id':preset,'source_revision':'2b6dc435b0f73a6f255e50ca795900acfd69cd33','grid_convention':'legacy_cd_negative_negative'})


def _bounded_token(value):
    """Keep archive/header identifiers useful without publishing filesystem paths."""
    token=str(value).strip() if value is not None else ''
    return token if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._ +:()-]{0,199}',token) else None


def _native_metadata(row, header, path):
    """Physical identity comes from FITS; archive identity comes from its manifest.

    SPHEREx primary VERSION is the pipeline software version. The archive
    product processing version is the l2b-vNN-YYYY-DDD token in the original
    product filename/URL or the trusted archive manifest, never VERSION.
    OBSID does not include the detector in native SPHEREx headers, hence the
    explicit detector suffix in the analysis observation identity.
    """
    header_key=next((key for key in ('OBSID','OBS_ID') if header.get(key) not in (None,'')),None)
    if header_key:
        raw_identifier=_bounded_token(header[header_key]); identity_source=f'fits:{header_key}'
    else:
        key='observation_id' if row.get('observation_id') else 'frame_id'
        raw_identifier=_bounded_token(row.get(key)); identity_source=f'manifest:{key}'
    if raw_identifier is None:
        raise InferenceError('invalid_fits','A bounded physical observation identity is required')
    detector=header.get('DETECTOR',header.get('DET_ID',header.get('DETID')))
    if detector is None:
        found=re.search(r'D([1-6])(?:\D|$)',raw_identifier)
        detector=found.group(1) if found else None
    match=re.fullmatch(r'(?:SPHEREx-)?D?([1-6])',str(detector))
    if not match:
        raise InferenceError('invalid_fits','Native detector identity is required')
    detector=int(match.group(1))
    access_url=row.get('access_url')
    if access_url is not None:
        if not isinstance(access_url,str) or len(access_url)>4096 or any(char.isspace() for char in access_url):
            raise InferenceError('invalid_input','Archive source URL must be a bounded public HTTP URL')
        parsed=urlsplit(access_url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise InferenceError('invalid_input','Archive source URL must be a bounded public HTTP URL')
    release=_bounded_token(row.get('release')) or next((_bounded_token(header.get(key)) for key in ('DATA_REL','RELEASE','DR') if _bounded_token(header.get(key))),None)
    if release is None and access_url:
        found=re.search(r'/(dr\d+|qr\d+)(?:/|$)',urlsplit(access_url).path,re.I)
        release=found.group(1) if found else None
    version=_bounded_token(row.get('processing_version'))
    # PROCVER/CAL_VER can themselves denote software/calibration versions;
    # accept only the archive's recognizable product-version syntax.
    if version is None:
        for value in (header.get('PRODVER'),header.get('PROCVER'),header.get('CAL_VER'),path.name,access_url):
            found=re.search(r'(?<![A-Za-z0-9])(l2b-v\d+-\d{4}-\d{3})(?![A-Za-z0-9])',str(value or ''),re.I)
            if found:
                version=found.group(1); break
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
    checksum=digest.hexdigest()
    expected=row.get('sha256')
    if expected is not None and (not isinstance(expected,str) or expected.lower()!=checksum):
        raise InferenceError('invalid_input','Native input checksum does not match the trusted manifest')
    result=dict(detector=detector,physical_observation_id=raw_identifier,
                observation_id_source=identity_source,units=str(header.get('BUNIT','unknown'))[:80],
                release=release or 'unknown',processing_version=version or 'unknown',
                software_version=_bounded_token(header.get('VERSION')) or 'unknown',
                sha256=checksum,input_size_bytes=path.stat().st_size)
    if access_url: result['access_url']=access_url
    return f'{raw_identifier}:D{detector}',result


def _fits(source, options):
    rows=source.get('observations'); region=source.get('region')
    if not isinstance(rows,list) or not 3<=len(rows)<=32:
        raise InferenceError('workload_limit','Use 3 to 32 native observations')
    try:
        ra=float(region['right_ascension_deg']); dec=float(region['declination_deg'])
        width_arcmin=float(region['width_arcmin']); height_arcmin=float(region['height_arcmin'])
        scale=options['pixel_scale_arcsec']
        if not np.isfinite([ra,dec,width_arcmin,height_arcmin]).all() or not 0<=ra<360 or not -90<dec<90 or min(width_arcmin,height_arcmin)<=0:
            raise ValueError()
        width=int(np.ceil(width_arcmin*60/scale)); height=int(np.ceil(height_arcmin*60/scale))
        if not 1<=min(width,height)<=max(width,height)<=512:
            raise InferenceError('workload_limit','Requested sky grid exceeds 512 by 512')
    except (TypeError,ValueError,KeyError):
        raise InferenceError('invalid_request','A finite sky region in degrees and arcminutes is required') from None
    grid=make_grid(ra,dec,width,height,scale)
    yy,xx=np.indices((height,width)); sky=grid.pixel_to_world_values(xx,yy)
    images=[]; dates=[]; ids=[]; frame_ids=[]; outliers=[]; blooms=[]; metadata=[]
    for row in rows:
        try:
            path=Path(row['path'])
            if path.stat().st_size>256*1024*1024:
                raise InferenceError('workload_limit','Native FITS exceeds supported file size')
            # Native unsigned flag arrays use FITS BZERO scaling, which Astropy
            # cannot read when memory mapping is explicitly forced on.
            with fits.open(path,memmap=False,lazy_load_hdus=True) as hdus:
                if any(name not in hdus for name in ('IMAGE','FLAGS','VARIANCE','ZODI')):
                    raise InferenceError('invalid_fits','Native FITS is missing a required science HDU')
                h=hdus[0].header.copy(); h.update(hdus['IMAGE'].header)
                identifier,native_metadata=_native_metadata(row,h,path)
                image=hdus['IMAGE'].data
                shape=image.shape
                if image.ndim!=2 or max(shape)>4096 or any(hdus[name].data.shape!=shape for name in ('FLAGS','VARIANCE','ZODI')):
                    raise InferenceError('invalid_fits','Native science HDUs have inconsistent or excessive dimensions')
                native=WCS(h).celestial
                if not native.has_celestial:
                    raise InferenceError('invalid_fits','Native FITS requires a celestial WCS')
                signal=np.asarray(image,dtype=float)-hdus['ZODI'].data
                raw_flags=hdus['FLAGS'].data
                if not np.issubdtype(raw_flags.dtype,np.integer):
                    raise InferenceError('invalid_fits','Native flags must be integer bit masks')
                flags=raw_flags.astype(np.int64); variance=hdus['VARIANCE'].data
                allowed=SOURCE_BIT | (OUTLIER_BIT if options['mask_policy']=='motion' else 0)
                good=((flags & ~allowed)==0)&np.isfinite(signal)&np.isfinite(variance)&(variance>0)
                x,y=native.world_to_pixel_values(*sky)
                points=[y,x]
                support=map_coordinates(good.astype(float),points,order=1,cval=0)
                projected=map_coordinates(np.where(good,signal,0),points,order=1,cval=0)
                usable=support>=.995
                if not usable.any():
                    raise InferenceError('no_coverage','An observation has no usable requested sky coverage')
                projected=np.divide(projected,support,where=usable,out=np.full(projected.shape,np.nan))
                projected-=np.nanmedian(projected)
                outlier=map_coordinates(((flags&OUTLIER_BIT)!=0).astype(float),points,order=1,cval=0)>0
                bloom=map_coordinates(((flags&BLOOM_BIT)!=0).astype(np.uint8),points,order=0,cval=0).astype(bool)
                midpoint=float(h['MJD-AVG']); date=str(h['DATE-AVG']).removesuffix('Z')
                if not np.isfinite(midpoint) or abs(float(Time(date,format='isot').mjd)-midpoint)>2/86400:
                    raise InferenceError('invalid_fits','Native midpoint metadata is inconsistent')
                metadata.append(native_metadata)
                images.append(projected); outliers.append(outlier); blooms.append(bloom)
                dates.append(Time(midpoint,format='mjd').isot); ids.append(identifier); frame_ids.append(row['frame_id'])
        except InferenceError:
            raise
        except (OSError,KeyError,ValueError,TypeError,AttributeError,IndexError):
            raise InferenceError('invalid_fits','Unable to prepare the native FITS science data') from None
    if len({row['detector'] for row in metadata})!=1:
        raise InferenceError('mixed_detectors','Analyze each detector separately')
    if len({row['units'] for row in metadata})!=1:
        raise InferenceError('mixed_units','Native observations must use comparable units')
    lookup={str(frame):meta for frame,meta in zip(frame_ids,metadata)}
    images,times,frames,outlier,bloom=_ordered(np.stack(images),dates,ids,frame_ids,np.stack(outliers),np.stack(blooms))
    for frame in frames: frame.update(lookup[frame['frame_id']])
    warnings=['passband_variation_not_corrected','psf_matching_not_applied']
    if len(frames)<len(rows): warnings.append('duplicate_observations_deduplicated')
    if any(frame['observation_id_source'].startswith('manifest:') for frame in frames):
        warnings.append('physical_observation_id_missing_manifest_fallback')
    if options['mask_policy']=='motion' and outlier.any(): warnings.append('outlier_measurements_retained')
    inputs=[dict(frame_id=str(frame),observation_id=str(identifier),**meta) for frame,identifier,meta in zip(frame_ids,ids,metadata)]
    return PreparedStack(images,times,frames,grid,outlier,bloom,scale,warnings,
                         {'source_kind':'fits','grid_convention':'north_up_cd_negative_positive',
                          'duplicate_observation_count':len(rows)-len(frames),'inputs':inputs})


def prepare(request):
    options=validate_request(request)
    stack=(_preset if request['source']['kind']=='preset' else _fits)(request['source'],options)
    _shape(stack.images)
    if len(stack.images)<options['min_epochs']:
        raise InferenceError('insufficient_observations','Insufficient independent observations for the requested minimum epochs')
    return stack
