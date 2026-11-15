"""FITS header-only integrity scanner: never reads any HDU data payload."""
from pathlib import Path
import hashlib,math

def value(text):
    text=text.strip()
    if text.startswith("'"):
        result='';index=1
        while index<len(text):
            if text[index]=="'":
                if index+1<len(text)and text[index+1]=="'":result+="'";index+=2;continue
                return result.rstrip()
            result+=text[index];index+=1
        raise ValueError('Unterminated FITS header string')
    raw=text.split('/',1)[0].strip()
    if raw in ['T','F']:return raw=='T'
    try:return int(raw)
    except ValueError:
        try:return float(raw.replace('D','E'))
        except ValueError:return raw

def scan(stream,size):
    if size%2880:raise ValueError('FITS block alignment failure')
    result=[];offset=0
    while offset<size:
        stream.seek(offset);header={};ended=False;header_bytes=0;sha=hashlib.sha256()
        while not ended:
            block=stream.read(2880);sha.update(block);header_bytes+=2880
            if len(block)!=2880:raise ValueError('Truncated FITS header')
            if header_bytes>1048576:raise ValueError('Unbounded FITS header')
            for index in range(0,2880,80):
                card=block[index:index+80].decode('ascii');key=card[:8].strip()
                if key=='END':ended=True;break
                if card[8:10]=='= ':header[key]=value(card[10:])
        if not result and header.get('SIMPLE')is not True:raise ValueError('Missing SIMPLE primary signature')
        axes=int(header['NAXIS']);dimensions=[int(header[f'NAXIS{i}'])for i in range(1,axes+1)]
        if not 0<=axes<=8 or any(n<0 for n in dimensions):raise ValueError('Invalid FITS dimensions')
        bitpix=int(header['BITPIX'])
        if bitpix not in [8,16,32,64,-32,-64]:raise ValueError('Invalid BITPIX')
        count=math.prod(dimensions)if axes else 0
        data_bytes=abs(bitpix)//8*int(header.get('GCOUNT',1))*(count+int(header.get('PCOUNT',0)))
        next_offset=offset+header_bytes+math.ceil(data_bytes/2880)*2880
        if next_offset>size:raise ValueError('Truncated FITS data block')
        result.append(dict(name=header.get('EXTNAME','PRIMARY'if not result else'UNNAMED'),header=header,header_offset=offset,header_bytes=header_bytes,data_bytes=data_bytes,header_sha256=sha.hexdigest()))
        offset=next_offset
    return result

def inspect(path,expected_obsid,expected_detector):
    path=Path(path)
    with path.open('rb')as stream:hdus=scan(stream,path.stat().st_size)
    byname={h['name']:h for h in hdus};required={'IMAGE','FLAGS','VARIANCE','ZODI','EPSF','WCS-WAVE'}
    if not required.issubset(byname):raise ValueError('Missing native mission extension')
    combined={**hdus[0]['header'],**byname['IMAGE']['header']};shape=[byname['IMAGE']['header'][key]for key in ['NAXIS2','NAXIS1']]
    for name in ['FLAGS','VARIANCE','ZODI']:
        if[byname[name]['header'][key]for key in ['NAXIS2','NAXIS1']]!=shape:raise ValueError('Native image/mask/variance/ZODI shape mismatch')
    if combined.get('OBSID')!=expected_obsid or int(combined['DETECTOR'])!=expected_detector:raise ValueError('Native physical OBSID/detector mismatch')
    if expected_detector not in [1,2,3]or byname['EPSF']['header'].get('DETCOORD')!='sky':raise ValueError('Unsupported native ePSF coordinate frame')
    if any(key not in combined for key in ['CTYPE1','CTYPE2','CRVAL1','CRVAL2','CRPIX1','CRPIX2','MJD-AVG']):raise ValueError('Missing native celestial WCS/midpoint')
    return dict(header_only=True,pixels_opened=False,native_orientation_preserved=True,hdu_names=[h['name']for h in hdus],native_shape=shape,
        detector=expected_detector,physical_obsid=combined['OBSID'],midpoint_mjd=combined['MJD-AVG'],
        epsf_detcoord=byname['EPSF']['header']['DETCOORD'],epsf_oversampling=[byname['EPSF']['header'].get('OVSMPX'),byname['EPSF']['header'].get('OVSMPY')],
        header_layout=[{key:h[key]for key in ['name','header_offset','header_bytes','data_bytes','header_sha256']}for h in hdus],
        wcs={key:combined.get(key)for key in ['CTYPE1','CTYPE2','CRVAL1','CRVAL2','CRPIX1','CRPIX2','CD1_1','CD1_2','CD2_1','CD2_2','CDELT1','CDELT2']})
