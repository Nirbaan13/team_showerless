#!/usr/bin/env python3
"""Bounded native-pixel FITS cutouts of the official public SPHEREx mirror.

The IBE URL supplies geometry only. No IBE request, resampling, full source
image download, redirect, compressed transport, or implicit remote FITS I/O is
performed. Raw pixel bytes and all ancillary tables remain archive originals.
"""
import argparse
import http.client
import io
import json
import math
import os
from pathlib import Path
import re
import ssl
import sys
import time
import urllib.parse
import warnings

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

OFFICIAL_HOSTS = frozenset(('nasa-irsa-spherex.s3.amazonaws.com',
                            'nasa-irsa-spherex.s3.us-east-1.amazonaws.com'))
MAX_BYTES = 64 * 1024 * 1024
MAX_SOURCE = 512 * 1024 * 1024
BLOCK = 2880


class CutoutError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(f'{code}: {message}')


def fail(code, message):
    raise CutoutError(code, message)


def _urls(source, cutout_url, allow_loopback):
    try:
        s, c = urllib.parse.urlsplit(source), urllib.parse.urlsplit(cutout_url)
        fixture = (allow_loopback and s.scheme == 'http' and s.hostname in ('127.0.0.1', '::1') and s.port is not None)
        if not fixture and (s.scheme != 'https' or s.netloc not in OFFICIAL_HOSTS):
            fail('archive_cutout_source', 'Source must use an exact official HTTPS SPHEREx S3 host')
        if (s.username or s.password or s.query or s.fragment or
                not re.fullmatch(r'/(?:qr[23]|dr1)/level2/[A-Za-z0-9_./-]+\.fits', s.path) or
                any(x in ('', '.', '..') for x in s.path.split('/')[1:])):
            fail('archive_cutout_source', 'Unsafe source FITS object path')
        if (c.scheme != 'https' or c.netloc != 'irsa.ipac.caltech.edu' or c.fragment or
                c.path != '/ibe/data/spherex' + s.path):
            fail('archive_cutout_geometry', 'Cutout must refer to the same object on the official IBE service')
        values = urllib.parse.parse_qs(c.query, strict_parsing=True, keep_blank_values=True)
        if set(values) != {'center', 'size'} or any(len(v) != 1 for v in values.values()):
            fail('archive_cutout_geometry', 'Expected one center and one size')
        center = values['center'][0].removesuffix('deg').split(',')
        if len(center) != 2: fail('archive_cutout_geometry', 'Center must contain RA and declination')
        ra, dec = map(float, center)
        size = float(values['size'][0].removesuffix('deg'))
        if not all(map(math.isfinite, (ra, dec, size))) or not (0 <= ra < 360 and -90 <= dec <= 90 and 0 < size <= 2):
            fail('archive_cutout_geometry', 'Invalid finite sky coordinates or cutout size (maximum 2 degrees)')
        return s, ra, dec, size
    except (ValueError, TypeError) as exc:
        fail('archive_cutout_geometry', f'Invalid URL or numeric geometry: {type(exc).__name__}')


class _Ranges:
    """A single pinned object identity with aggregate and per-read budgets."""
    def __init__(self, parsed, budget, timeout):
        self.parsed, self.budget, self.used, self.size, self.etag = parsed, budget, 0, None, None
        self.started = time.monotonic()
        self.deadline = self.started + timeout
        self.requests = 0
        self.connection = (http.client.HTTPSConnection(parsed.hostname, timeout=min(10, timeout), context=ssl.create_default_context())
                           if parsed.scheme == 'https' else http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=min(10, timeout)))

    def close(self): self.connection.close()

    def read(self, start, length):
        if (length <= 0 or start < 0 or length > self.budget - self.used or
                self.requests >= 2048 or time.monotonic() > self.deadline):
            fail('archive_cutout_limit', 'Bounded cutout network, time or request budget exceeded')
        end = start + length - 1
        if self.size is not None and end >= self.size:
            fail('archive_cutout_fits', 'FITS layout exceeds source object')
        headers = {'Range': f'bytes={start}-{end}', 'Accept-Encoding': 'identity', 'User-Agent': 'SpaceApps-native-cutout/1'}
        if self.etag is not None: headers['If-Match'] = self.etag
        self.requests += 1
        try:
            remaining=self.deadline-time.monotonic()
            if remaining<=0:fail('archive_cutout_limit','Cutout deadline exceeded')
            self.connection.timeout=min(10,remaining)
            if self.connection.sock is not None:self.connection.sock.settimeout(self.connection.timeout)
            self.connection.request('GET', self.parsed.path, headers=headers)
            with self.connection.getresponse() as response:
                match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.getheader('Content-Range', ''))
                if response.status != 206 or not match:
                    fail('archive_cutout_range', 'Server must return HTTP 206 with exact Content-Range')
                first, last, total = map(int, match.groups())
                if (first != start or last != end or total <= end or total > MAX_SOURCE or
                        (self.size is not None and self.size != total)):
                    fail('archive_cutout_range', 'Unexpected Content-Range or source size')
                etag = response.getheader('ETag', '')
                if not re.fullmatch(r'"[^"\r\n]+"', etag) or (self.etag is not None and etag != self.etag):
                    fail('archive_cutout_identity', 'Source must retain the same strong ETag for every range')
                if (response.getheader('Content-Encoding', 'identity').lower() != 'identity' or
                        any(x in response.getheader('Content-Type', '').lower() for x in ('html', 'json', 'xml'))):
                    fail('archive_cutout_transport', 'Encoded or non-FITS response rejected')
                try: content_length = int(response.getheader('Content-Length', '-1'))
                except ValueError: content_length = -1
                if content_length != length:
                    fail('archive_cutout_range', 'Response length differs from requested range')
                self.size, self.etag = total, etag
                body = bytearray()
                while len(body) < length:
                    remaining = self.deadline-time.monotonic()
                    if remaining <= 0: fail('archive_cutout_limit','Cutout deadline exceeded')
                    if self.connection.sock is not None: self.connection.sock.settimeout(min(10,remaining))
                    chunk=response.read1(min(65536,length-len(body)))
                    if not chunk: break
                    body.extend(chunk); self.used += len(chunk)
                if len(body) != length:
                    fail('archive_cutout_range', 'Truncated or excessive range response')
                return bytes(body)
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            fail('archive_cutout_transport', f'Range transport failed: {type(exc).__name__}')


def _layout(remote):
    result, offset = [], 0
    while remote.size is None or offset < remote.size:
        if len(result) >= 32: fail('archive_cutout_limit', 'Too many FITS HDUs')
        raw, done = bytearray(), False
        for _ in range(92):
            take = BLOCK if remote.size is None else min(24*BLOCK,remote.size-offset-len(raw))
            if take <= 0: fail('archive_cutout_fits','Unterminated FITS header')
            if len(raw)+take > 92*BLOCK: fail('archive_cutout_limit','FITS header exceeds bound')
            block = remote.read(offset + len(raw), take)
            if not raw and block[:8] not in (b'SIMPLE  ', b'XTENSION'):
                fail('archive_cutout_fits', 'Expected FITS primary or extension header')
            raw.extend(block)
            end=next((i+80 for i in range(0,len(raw),80) if raw[i:i+8]==b'END     '),None)
            if end is not None:
                raw=raw[:((end+BLOCK-1)//BLOCK)*BLOCK]
                done = True; break
        if not done: fail('archive_cutout_limit', 'FITS header exceeds bound')
        try:
            header = fits.Header.fromstring(raw.decode('ascii'), sep='')
            naxis, bitpix = int(header['NAXIS']), int(header['BITPIX'])
            if not 0 <= naxis <= 2 or bitpix not in (8,16,32,64,-32,-64):
                fail('archive_cutout_unsupported', 'unsupported FITS dimensions or BITPIX')
            dims = [int(header[f'NAXIS{i}']) for i in range(1,naxis+1)]
            pcount, gcount = int(header.get('PCOUNT',0)), int(header.get('GCOUNT',1))
            if any(d < 0 for d in dims) or pcount < 0 or gcount != 1 or header.get('GROUPS'):
                fail('archive_cutout_unsupported', 'unsupported FITS groups or dimensions')
            kind = str(header.get('XTENSION','PRIMARY')).strip()
            if kind not in ('PRIMARY','IMAGE','BINTABLE'):
                fail('archive_cutout_unsupported', 'unsupported non-image FITS HDU')
            if header.get('ZIMAGE'):
                if (kind != 'BINTABLE' or header.get('ZCMPTYPE') != 'RICE_1' or
                        header.get('ZNAXIS') != 2 or header.get('ZBITPIX') not in (8,16,32)):
                    fail('archive_cutout_unsupported','unsupported compressed image format')
                zw,zh = int(header['ZNAXIS1']),int(header['ZNAXIS2'])
                tw,th = int(header.get('ZTILE1',zw)),int(header.get('ZTILE2',1))
                if (min(zw,zh,tw,th) <= 0 or tw > zw or th > zh or
                        tw*th*abs(header['ZBITPIX'])//8 > 1024*1024 or
                        int(header['NAXIS1'])*int(header['NAXIS2']) > 1024*1024):
                    fail('archive_cutout_unsupported','unsupported oversized compressed tiles or descriptor table')
                kind = 'COMPRESSED'
            if kind in ('PRIMARY','IMAGE') and naxis not in (0,2):
                fail('archive_cutout_unsupported', 'unsupported non-spatial image dimensions')
            if kind in ('PRIMARY','IMAGE') and pcount:
                fail('archive_cutout_unsupported', 'unsupported image heap')
            length = abs(bitpix)//8 * (math.prod(dims) if dims else 0) + pcount
            data_start = offset + len(raw)
            next_offset = data_start + ((length + BLOCK-1)//BLOCK)*BLOCK
            if next_offset > remote.size: fail('archive_cutout_fits','FITS HDU exceeds source object')
        except CutoutError: raise
        except Exception as exc: fail('archive_cutout_fits',f'Invalid FITS header: {type(exc).__name__}')
        result.append((header, bytes(raw), data_start, length, kind))
        offset = next_offset
    if not result or result[0][4] != 'PRIMARY': fail('archive_cutout_fits','Missing FITS primary HDU')
    return result


def _bounds(header, ra, dec, diameter):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            wcs = WCS(header)
        if not wcs.has_celestial or wcs.pixel_n_dim != 2 or wcs.world_n_dim != 2:
            fail('archive_cutout_unsupported', 'unsupported non-celestial science WCS')
        center = SkyCoord(ra*u.deg,dec*u.deg)
        perimeter = center.directional_offset_by(np.linspace(0,360,2049)*u.deg, diameter/2*u.deg)
        world = np.column_stack((perimeter.ra.deg,perimeter.dec.deg))
        world = np.vstack((world,[ra,dec]))
        pixels = wcs.all_world2pix(world,0,tolerance=1e-9,maxiter=100,quiet=False)
        if not np.all(np.isfinite(pixels)): fail('archive_cutout_wcs','Nonfinite inverse WCS')
        roundtrip = wcs.all_pix2world(pixels,0)
        error = SkyCoord(world[:,0]*u.deg,world[:,1]*u.deg).separation(SkyCoord(roundtrip[:,0]*u.deg,roundtrip[:,1]*u.deg)).arcsec
        if np.max(error) > 1e-4: fail('archive_cutout_wcs','Inverse WCS reconstruction exceeds tolerance')
        # Dense cap perimeter plus a two-pixel guard encloses pixel centers and
        # edge curvature; no pixel values are interpolated or reprojected.
        x0,y0 = np.floor(np.min(pixels,axis=0)-2).astype(int)
        x1,y1 = np.ceil(np.max(pixels,axis=0)+2).astype(int)+1
        width,height = int(header['NAXIS1']),int(header['NAXIS2'])
        if x1 <= 0 or y1 <= 0 or x0 >= width or y0 >= height:
            fail('archive_cutout_off_image','Requested sky region does not overlap this image')
        return wcs, (max(0,int(x0)),max(0,int(y0)),min(width,int(x1)),min(height,int(y1)))
    except CutoutError: raise
    except Exception as exc: fail('archive_cutout_wcs',f'Unsupported or nonconvergent WCS: {type(exc).__name__}')


def _sliced_header(header, bounds):
    x0,y0,x1,y1 = bounds
    output = header.copy()
    # WCS.slice correctly translates SIP reference pixels without altering its
    # distortion polynomial. Preserve all original non-WCS and alternate cards.
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        original = WCS(header)
        if original.has_celestial:
            sliced = original.slice((slice(y0,y1),slice(x0,x1)))
            output.update(sliced.to_header(relax=True))
            points = np.array([[0.,0.],[x1-x0-1.,y1-y0-1.],[(x1-x0-1)/2,(y1-y0-1)/2]])
            before = original.all_pix2world(points+[x0,y0],0)
            after = WCS(output).all_pix2world(points,0)
            if not np.allclose(before,after,atol=1e-10,rtol=0):
                fail('archive_cutout_wcs','Sliced WCS does not reconstruct original sky coordinates')
        else:
            for axis,shift in ((1,x0),(2,y0)):
                key=f'CRPIX{axis}'
                if key in output: output[key] = float(output[key])-shift
    for key in list(output):
        if re.fullmatch(r'CRPIX[12][A-Z]',key):
            output[key] = float(output[key]) - (x0 if key[5]=='1' else y0)
    for key in ('CHECKSUM','DATASUM'):
        if key in output: del output[key]
    output['NAXIS1'],output['NAXIS2'] = x1-x0,y1-y0
    return output


def _image_bytes(remote, start, header, bounds):
    x0,y0,x1,y1 = bounds
    bpp, width = abs(int(header['BITPIX']))//8, int(header['NAXIS1'])
    stride, count = width*bpp, (x1-x0)*bpp
    # Coalesce only a bounded number of requested rows, discarding intervening
    # columns. This keeps request count finite without loading a whole image.
    batch = max(1, min(32, 262144//stride))
    result = bytearray()
    for y in range(y0,y1,batch):
        rows = min(batch,y1-y)
        block = remote.read(start+y*stride+x0*bpp,(rows-1)*stride+count)
        for i in range(rows): result.extend(block[i*stride:i*stride+count])
    return result



class _CompressedFile(io.RawIOBase):
    """Virtual single-HDU FITS file: memory headers plus ranged original heap.

    Astropy's CompImageHDU.section reads the small descriptor table and only
    overlapping compressed tiles. It cannot inspect or download other images.
    """
    def __init__(self, remote, raw_header, start, length):
        super().__init__()
        self.remote,self.start=remote,start
        self.prefix=fits.PrimaryHDU().header.tostring().encode('ascii')+raw_header
        self.size=len(self.prefix)+((length+BLOCK-1)//BLOCK)*BLOCK
        self.position=0
        h=fits.Header.fromstring(raw_header.decode('ascii'))
        self.heap_start=start+int(h.get('THEAP',h['NAXIS1']*h['NAXIS2']))
        self.cache_start,self.cache=0,b''

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.position
    def seek(self,offset,whence=0):
        target=offset+(0 if whence==0 else self.position if whence==1 else self.size)
        if target<0: raise ValueError('negative seek')
        self.position=target
        return target

    def read(self,size=-1):
        if size is None or size<0:
            fail('archive_cutout_limit','Unbounded compressed FITS read rejected')
        size=min(size,max(0,self.size-self.position))
        if size==0:return b''
        result=b''
        if self.position<len(self.prefix):
            count=min(size,len(self.prefix)-self.position)
            result=self.prefix[self.position:self.position+count]
            self.position+=count;size-=count
        if size:
            address=self.start+self.position-len(self.prefix)
            if address >= self.heap_start:
                if not (self.cache_start <= address and address+size <= self.cache_start+len(self.cache)):
                    count=min(max(size,65536),self.start+self.size-len(self.prefix)-address)
                    # Speculative coalescing never weakens aggregate budgets.
                    if count > self.remote.budget-self.remote.used:count=size
                    self.cache_start,self.cache=address,self.remote.read(address,count)
                result+=self.cache[address-self.cache_start:address-self.cache_start+size]
            else:
                result+=self.remote.read(address,size)
            self.position+=size
        return result

    def readinto(self,buffer):
        result=self.read(len(buffer));buffer[:len(result)]=result
        return len(result)


def _compressed_bytes(remote,raw,start,length,bounds):
    x0,y0,x1,y1=bounds
    with fits.open(_CompressedFile(remote,raw,start,length),memmap=False,
                   do_not_scale_image_data=True,lazy_load_hdus=True) as hdus:
        hdu=hdus[1]
        # Explicitly request a section, never .data (which loads all tiles).
        data=hdu.section[y0:y1,x0:x1]
        header=hdu.header.copy()
        dtype=np.dtype('>u1' if header['BITPIX']==8 else f">i{header['BITPIX']//8}")
        payload=data.astype(dtype,copy=False).tobytes()
    return payload,_sliced_header(header,bounds)


def cutout(source, cutout_url, output, *, allow_loopback=False, max_network_bytes=MAX_BYTES, max_output_bytes=MAX_BYTES, timeout_seconds=90):
    parsed,ra,dec,diameter = _urls(source,cutout_url,allow_loopback)
    if not 0 < max_network_bytes <= MAX_BYTES or not 0 < max_output_bytes <= MAX_BYTES:
        fail('archive_cutout_limit','Invalid cutout resource budget')
    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 180:
        fail('archive_cutout_limit','Invalid finite cutout timeout')
    remote, temporary = _Ranges(parsed,max_network_bytes,timeout_seconds), None
    output = Path(output)
    try:
        layout = _layout(remote)
        science = next((h for h,_,_,_,kind in layout if kind in ('PRIMARY','IMAGE') and h.get('NAXIS')==2 and h.get('EXTNAME','').strip()=='IMAGE'),None)
        if science is None: fail('archive_cutout_fits','Missing two-dimensional IMAGE extension')
        _,bounds = _bounds(science,ra,dec,diameter)
        native_shape = (science['NAXIS1'],science['NAXIS2'])
        estimated = 0
        for h,raw,_,length,kind in layout:
            if kind == 'COMPRESSED' or (kind in ('PRIMARY','IMAGE') and h['NAXIS']==2):
                shape = (h['ZNAXIS1'],h['ZNAXIS2']) if kind=='COMPRESSED' else (h['NAXIS1'],h['NAXIS2'])
                if shape != native_shape:
                    fail('archive_cutout_unsupported','unsupported image extension on a different native grid')
                length = (bounds[2]-bounds[0])*(bounds[3]-bounds[1])*abs(h['ZBITPIX'] if kind=='COMPRESSED' else h['BITPIX'])//8
            estimated += len(raw)+((length+BLOCK-1)//BLOCK)*BLOCK
        if estimated > max_output_bytes: fail('archive_cutout_limit','Output exceeds bounded FITS budget')
        output.parent.mkdir(parents=True,exist_ok=True)
        pending = str(output)+'.mirror-part'
        descriptor = os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        temporary = pending
        with os.fdopen(descriptor,'wb') as stream:
            for index,(header,raw,start,length,kind) in enumerate(layout):
                header = header.copy()
                if kind == 'COMPRESSED':
                    payload,header = _compressed_bytes(remote,raw,start,length,bounds)
                elif kind in ('PRIMARY','IMAGE') and header['NAXIS']==2:
                    payload = _image_bytes(remote,start,header,bounds)
                    header = _sliced_header(header,bounds)
                else:
                    payload = remote.read(start,length) if length else b''
                    for key in ('CHECKSUM','DATASUM'):
                        if key in header: del header[key]
                if index==0:
                    header['SRCURL'] = source
                    header['SRCETAG'] = remote.etag
                    header['CUTX0'],header['CUTY0'],header['CUTX1'],header['CUTY1'] = bounds
                    header.add_history('Native detector pixel slice; no resampling or interpolation')
                stream.write(header.tostring().encode('ascii'))
                stream.write(payload)
                stream.write(b'\0' * ((-len(payload))%BLOCK))
                if stream.tell() > max_output_bytes: fail('archive_cutout_limit','Output exceeds bounded FITS budget')
            stream.flush(); os.fsync(stream.fileno())
        # Read only the small local result to validate its FITS structure before
        # atomic publication. This never triggers archive data access.
        with fits.open(temporary,memmap=False,do_not_scale_image_data=True) as hdus:
            hdus.verify('exception')
        os.replace(temporary,output); temporary = None
        return {'ok':True,'output':str(output),'sourceUrl':source,'bounds':list(bounds),'networkBytes':remote.used,'sourceBytes':remote.size,'etag':remote.etag,'nRanges':remote.requests,'elapsedSeconds':time.monotonic()-remote.started}
    except CutoutError: raise
    except Exception as exc: fail('archive_cutout_failed',f'Native cutout failed: {type(exc).__name__}')
    finally:
        remote.close()
        if temporary is not None:
            try: os.unlink(temporary)
            except FileNotFoundError: pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True)
    parser.add_argument('--cutout',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--max-bytes',type=int,default=MAX_BYTES)
    args=parser.parse_args()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            result=cutout(args.source,args.cutout,args.output,max_network_bytes=args.max_bytes,max_output_bytes=args.max_bytes)
        print(json.dumps(result,separators=(',',':')))
        return 0
    except CutoutError as exc:
        print(json.dumps({'error':{'code':exc.code,'message':exc.message}},separators=(',',':')))
        return 1


if __name__ == '__main__': sys.exit(main())
