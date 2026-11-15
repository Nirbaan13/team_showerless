#!/usr/bin/env python3
"""Resumable metadata-only index of the official public SPHEREx S3 mirror.

Only bounded HTTP Range header reads are made; science image arrays are never
opened. `scan` is incremental and idempotent after completion. `reset` explicitly
clears configured release metadata and starts a fresh listing.
Searches of incomplete indexes never present an empty result as complete sky.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
from functools import wraps
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import shutil
import ssl
import threading
import sys
import time
import urllib.parse
import warnings
import zlib
import xml.etree.ElementTree as ET

import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS

OFFICIAL_ROOT = 'https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/'
HEADER_LIMIT = 262144


class MirrorError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(f'{code}: {message}')


def fail(code, message):
    raise MirrorError(code, message)


def _root(value):
    p = urllib.parse.urlsplit(value)
    official = value == OFFICIAL_ROOT
    fixture = (p.scheme == 'http' and p.hostname in ('127.0.0.1', '::1') and p.port is not None)
    if not (official or fixture) or p.path not in ('', '/') or p.query or p.fragment or p.username or p.password:
        fail('archive_mirror_configuration', 'Use the official HTTPS mirror root or an explicit loopback HTTP fixture root')
    return value.rstrip('/') + '/'


def _key(key, releases):
    if (not isinstance(key, str) or len(key) > 1024 or not re.fullmatch(r'[A-Za-z0-9_./-]+', key)
            or any(part in ('', '.', '..') for part in key.split('/'))):
        fail('archive_mirror_object_invalid', 'Unsafe S3 object key')
    parts = key.split('/')
    if len(parts) < 3 or parts[0] not in releases or parts[1] != 'level2' or not key.endswith('.fits'):
        fail('archive_mirror_object_invalid', 'Object is outside configured level2 releases')
    return key


_connections = threading.local()
_tls_context = ssl.create_default_context()


def _http(url, byte_limit, headers=None, ranged=False):
    """Thread-local keepalive, strict TLS, bounded reads and finite retries.

    Only the allowlisted root constructs URLs. Redirects and compressed bodies
    remain forbidden; reuse never weakens Range/identity validation.
    """
    parsed = urllib.parse.urlsplit(url)
    address = (parsed.scheme, parsed.hostname, parsed.port)
    for attempt in range(2):
        connection = getattr(_connections, 'connection', None)
        if connection is None or getattr(_connections, 'address', None) != address:
            if connection is not None:
                connection.close()
            connection = (http.client.HTTPSConnection(parsed.hostname, parsed.port, timeout=10, context=_tls_context)
                          if parsed.scheme == 'https' else http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=10))
            _connections.connection, _connections.address = connection, address
        try:
            target = parsed.path or '/'
            if parsed.query:
                target += '?' + parsed.query
            connection.request('GET', target, headers={'Accept-Encoding': 'identity', 'User-Agent': 'SpaceApps-SPHEREx-metadata-index/2', **(headers or {})})
            with connection.getresponse() as response:
                if response.status in (429, 500, 502, 503, 504) and attempt == 0:
                    connection.close()
                else:
                    if response.getheader('Content-Encoding', 'identity') != 'identity':
                        fail('archive_mirror_transport', 'Encoded bodies cannot be range-validated')
                    if ranged:
                        match = re.fullmatch(r'bytes 0-(\d+)/(\d+)', response.getheader('Content-Range', ''))
                        if response.status != 206 or not match:
                            fail('archive_mirror_range_required', 'Server must honor bounded Range with HTTP 206 and Content-Range')
                        end, size = map(int, match.groups())
                        if size <= 0 or end != min(byte_limit, size) - 1:
                            fail('archive_mirror_range_required', 'Unexpected Content-Range extent')
                        expected = end + 1
                    else:
                        if response.status != 200:
                            fail('archive_mirror_transport', f'Mirror HTTP {response.status}')
                        expected = None
                    length = response.getheader('Content-Length')
                    if length is not None and (int(length) > byte_limit or (expected is not None and int(length) != expected)):
                        fail('archive_mirror_transport', 'Response exceeds requested byte budget')
                    body = response.read(byte_limit + 1)
                    if len(body) > byte_limit or (expected is not None and len(body) != expected):
                        fail('archive_mirror_transport', 'Response byte count violates range contract')
                    return body, {k.lower(): v for k, v in response.getheaders()}
        except MirrorError:
            connection.close()
            raise
        except (OSError, TimeoutError, http.client.HTTPException) as exc:
            connection.close()
            if attempt == 1:
                fail('archive_mirror_transport', f'Mirror transport failed: {type(exc).__name__}')
        time.sleep(0.25 * (attempt + 1))


class _NeedHeader(Exception):
    pass


def _headers(data):
    """Walk FITS block offsets from cards, without instantiating any image HDU."""
    offset = 0
    primary = None
    for _ in range(32):
        if offset + 80 > len(data):
            raise _NeedHeader()
        if data[offset:offset+8] not in (b'SIMPLE  ', b'XTENSION'):
            fail('archive_mirror_fits_invalid', 'Expected a FITS primary or extension header')
        end = None
        for cursor in range(offset, len(data) - 79, 80):
            if data[cursor:cursor+8] == b'END     ':
                end = cursor + 80
                break
        if end is None:
            raise _NeedHeader()
        try:
            h = fits.Header.fromstring(data[offset:end].decode('ascii'), sep='')
        except Exception as exc:
            fail('archive_mirror_fits_invalid', f'Invalid FITS header: {type(exc).__name__}')
        if primary is None:
            primary = h
        elif h.get('EXTNAME', '').strip().upper() == 'IMAGE':
            return primary, h
        # Skip only according to the FITS standard layout; no array is read.
        naxis = int(h.get('NAXIS', 0))
        elements = math.prod(int(h[f'NAXIS{i}']) for i in range(1, naxis + 1)) if naxis else 0
        size = abs(int(h.get('BITPIX', 8))) // 8 * int(h.get('GCOUNT', 1)) * (elements + int(h.get('PCOUNT', 0)))
        offset = ((end + 2879) // 2880) * 2880 + ((size + 2879) // 2880) * 2880
    fail('archive_mirror_fits_invalid', 'No IMAGE extension within bounded header traversal')


def _instant(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except (TypeError, ValueError):
        fail('invalid_request', 'Date must be an ISO UTC date or timestamp')


def _stamp(value):
    return value.isoformat(timespec='microseconds').replace('+00:00', 'Z').replace('000Z', 'Z')


def _vectors(radec):
    values = np.radians(np.asarray(radec, dtype=float))
    ra, dec = values[..., 0], values[..., 1]
    return np.stack((np.cos(dec)*np.cos(ra), np.cos(dec)*np.sin(ra), np.sin(dec)), axis=-1)


def _angle(a, b):
    return np.arctan2(np.linalg.norm(np.cross(a, b), axis=-1), np.sum(a*b, axis=-1))


def _on_arc(p, a, b):
    return abs(float(_angle(a, p) + _angle(p, b) - _angle(a, b))) < 1e-8


def _contains(poly, point):
    # The opposite hemisphere has the opposite winding and must be excluded.
    if float(np.dot(np.sum(poly, axis=0), point)) < 0:
        return False
    following = np.roll(poly, -1, axis=0)
    projected = poly - np.outer(poly @ point, point)
    lengths = np.linalg.norm(projected, axis=1)
    if np.any(lengths < 1e-12):
        return True
    projected /= lengths[:, None]
    nxt = np.roll(projected, -1, axis=0)
    winding = np.sum(np.arctan2(np.cross(projected, nxt) @ point, np.sum(projected * nxt, axis=1)))
    if abs(winding) > math.pi:
        return True
    return any(_on_arc(point, a, b) for a, b in zip(poly, following))


def _arcs_intersect(a, b, c, d):
    line = np.cross(np.cross(a, b), np.cross(c, d))
    norm = float(np.linalg.norm(line))
    if norm < 1e-14:
        return any(_on_arc(p, a, b) for p in (c, d)) or any(_on_arc(p, c, d) for p in (a, b))
    p = line / norm
    return any(_on_arc(v, a, b) and _on_arc(v, c, d) for v in (p, -p))


def _cap(poly):
    center = np.sum(poly, axis=0)
    center /= np.linalg.norm(center)
    return center, float(np.max(_angle(poly, center)))


def _polygon_overlap(a, b):
    ac, ar = _cap(a)
    bc, br = _cap(b)
    if ar < math.pi/2 and br < math.pi/2 and _angle(ac, bc) > ar + br + 1e-8:
        return False
    if _contains(a, b[0]) or _contains(b, a[0]):
        return True
    return any(_arcs_intersect(p, q, r, s) for p, q in zip(a, np.roll(a, -1, axis=0)) for r, s in zip(b, np.roll(b, -1, axis=0)))


def _circle_overlap(poly, center, radius):
    pc, pr = _cap(poly)
    if pr < math.pi/2 and _angle(pc, center) > pr + radius + 1e-8:
        return False
    if _contains(poly, center) or np.any(_angle(poly, center) <= radius + 1e-10):
        return True
    for a, b in zip(poly, np.roll(poly, -1, axis=0)):
        normal = np.cross(a, b)
        norm = np.linalg.norm(normal)
        if norm < 1e-14:
            continue
        normal /= norm
        projection = center - np.dot(center, normal) * normal
        length = np.linalg.norm(projection)
        if length < 1e-14:
            continue
        near = projection / length
        if _on_arc(near, a, b) and _angle(near, center) <= radius + 1e-10:
            return True
    return False


def _range_overlap(poly, lo, width, bottom, top):
    """Exact spherical meridian/small-circle box intersections, including poles."""
    def longitude_inside(ra):
        return width >= 360 or (ra - lo) % 360 <= width + 1e-8
    ra = np.degrees(np.arctan2(poly[:, 1], poly[:, 0])) % 360
    dec = np.degrees(np.arcsin(np.clip(poly[:, 2], -1, 1)))
    if any(longitude_inside(x) and bottom-1e-8 <= y <= top+1e-8 for x, y in zip(ra, dec)):
        return True
    corners = _vectors([[lo, bottom], [lo+width, bottom], [lo+width, top], [lo, top]])
    if any(_contains(poly, corner) for corner in corners):
        return True
    following = np.roll(poly, -1, axis=0)
    if width < 360:
        latitudes = np.linspace(bottom, top, max(2, math.ceil((top-bottom)/45)+1))
        for meridian in (lo, lo+width):
            edge = _vectors([[meridian, latitude] for latitude in latitudes])
            if any(_arcs_intersect(a, b, c, d) for a, b in zip(poly, following) for c, d in zip(edge[:-1], edge[1:])):
                return True
    # Intersect each great-circle footprint segment with z=sin(latitude).
    for latitude in (bottom, top):
        latitude = math.radians(latitude)
        coslat, sinlat = math.cos(latitude), math.sin(latitude)
        if abs(coslat) < 1e-12:
            continue  # Polar contact is handled by containment above.
        for a, b in zip(poly, following):
            normal = np.cross(a, b)
            magnitude = math.hypot(normal[0], normal[1])
            if magnitude < 1e-15:
                continue
            ratio = -normal[2] * sinlat / (magnitude * coslat)
            if abs(ratio) > 1 + 1e-10:
                continue
            base = math.atan2(normal[1], normal[0])
            offset = math.acos(max(-1, min(1, ratio)))
            for longitude in (base-offset, base+offset):
                candidate = np.asarray([coslat*math.cos(longitude), coslat*math.sin(longitude), sinlat])
                if longitude_inside(math.degrees(longitude)) and _on_arc(candidate, a, b):
                    return True
    return False


def _region(position):
    try:
        fields = position.split()
        kind = fields[0].upper()
        nums = [float(v) for v in fields[1:]]
        if not nums or not all(math.isfinite(v) for v in nums):
            raise ValueError()
        if kind == 'CIRCLE' and len(nums) == 3:
            ra, dec, radius = nums
            if not (-90 <= dec <= 90 and 0 <= radius <= 180):
                raise ValueError()
            center = _vectors([[ra, dec]])[0]
            return lambda poly: _circle_overlap(poly, center, math.radians(radius))
        if kind == 'POLYGON' and len(nums) >= 6 and len(nums) <= 256 and len(nums) % 2 == 0:
            coords = np.asarray(nums).reshape(-1, 2)
            if np.any(np.abs(coords[:, 1]) > 90):
                raise ValueError()
            poly = _vectors(coords)
            center = np.sum(poly, axis=0)
            if np.linalg.norm(center) < 1e-9 or np.any(poly @ center <= 0):
                fail('archive_mirror_geometry_unsupported', 'Polygon must fit within one hemisphere')
            return lambda footprint: _polygon_overlap(footprint, poly)
        if kind == 'RANGE' and len(nums) == 4:
            lo, hi, bottom, top = nums
            if not (-90 <= bottom <= top <= 90) or lo == hi:
                raise ValueError()
            width = (hi - lo) % 360
            if abs(hi - lo) == 360:
                width = 360
            return lambda footprint: _range_overlap(footprint, lo, width, bottom, top)
    except (AttributeError, IndexError, TypeError, ValueError):
        pass
    fail('invalid_request', 'position must be valid CIRCLE, POLYGON, or RANGE geometry')


def _decode(value):
    return json.loads(zlib.decompress(value) if isinstance(value, bytes) else value)


def _cap_bounds(center, radius):
    """Conservative Cartesian bounds avoid RA seams and singular polar boxes."""
    if radius >= math.pi / 2:
        return (-1., 1., -1., 1., -1., 1.)
    cosine, sine = math.cos(radius), math.sin(radius)
    bounds = []
    for axis in center:
        offset = math.sqrt(max(0, 1 - axis * axis)) * sine
        lo, hi = axis * cosine - offset, axis * cosine + offset
        if axis >= cosine:
            hi = 1.
        if -axis >= cosine:
            lo = -1.
        bounds.extend((max(-1., lo-1e-7), min(1., hi+1e-7)))
    return tuple(bounds)


def _footprint_bounds(poly):
    center, radius = _cap(poly)
    return _cap_bounds(center, radius)


def _query_bounds(position):
    fields = position.split()
    nums = [float(value) for value in fields[1:]]
    kind = fields[0].upper()
    if kind == 'CIRCLE':
        return _cap_bounds(_vectors([nums[:2]])[0], math.radians(nums[2]))
    if kind == 'POLYGON':
        return _footprint_bounds(_vectors(np.asarray(nums).reshape(-1, 2)))
    lo, hi, bottom, top = nums
    width = 360 if abs(hi-lo) == 360 else (hi-lo) % 360
    # Cartesian extrema of a longitude/latitude rectangle occur at endpoints
    # or at stationary angles. This also covers full-longitude polar queries.
    longitudes = [lo, lo+width] + [v for v in (0, 90, 180, 270) if (v-lo) % 360 <= width]
    latitudes = [bottom, top] + ([0] if bottom <= 0 <= top else [])
    points = _vectors([[ra, dec] for ra in longitudes for dec in latitudes])
    return tuple(v for axis in range(3) for v in (max(-1., float(points[:, axis].min())-1e-7), min(1., float(points[:, axis].max())+1e-7)))


def _read_snapshot(method):
    @wraps(method)
    def read(self, *args, **kwargs):
        owner = not self.db.in_transaction
        if owner:
            self.db.execute('BEGIN')
        try:
            return method(self, *args, **kwargs)
        finally:
            if owner:
                self.db.rollback()
    return read


class MirrorIndex:
    def __init__(self, db, root=OFFICIAL_ROOT, releases=('qr2', 'dr1', 'qr3')):
        self.root = _root(root)
        self.releases = tuple(dict.fromkeys(str(v).lower() for v in releases))
        if not self.releases or any(v not in ('dr1', 'qr3', 'qr2') for v in self.releases):
            fail('archive_mirror_configuration', 'Supported releases: dr1, qr3, qr2')
        path = Path(db)
        self.path = path
        try:
            self.max_index_bytes = int(os.environ.get('IRSA_MIRROR_MAX_INDEX_BYTES', 512 * 1024 * 1024))
            if self.max_index_bytes <= 0:
                raise ValueError()
        except ValueError:
            fail('archive_mirror_configuration', 'IRSA_MIRROR_MAX_INDEX_BYTES must be positive')
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS mirror_configuration (name TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS mirror_pages (release TEXT PRIMARY KEY, token TEXT, complete INTEGER NOT NULL DEFAULT 0, pages INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS mirror_objects (key TEXT PRIMARY KEY, release TEXT NOT NULL, identity TEXT NOT NULL, body TEXT NOT NULL, footprint TEXT NOT NULL, observed REAL NOT NULL, detector INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS mirror_retries (key TEXT PRIMARY KEY, release TEXT NOT NULL, identity TEXT NOT NULL,
                error TEXT NOT NULL, last_attempt REAL NOT NULL, next_attempt REAL NOT NULL, attempts INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS mirror_retry_due ON mirror_retries(next_attempt, release);
            CREATE INDEX IF NOT EXISTS mirror_filter ON mirror_objects(release, detector, observed);
        ''')
        # Migration is one-time and preserves verified records from the older
        # sequential scanner. RTree bounds are conservative; exact WCS geometry
        # remains the final authority for every returned image.
        spatial_exists = self.db.execute("SELECT 1 FROM sqlite_master WHERE name='mirror_spatial'").fetchone()
        self.db.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS mirror_spatial USING rtree(id,min_x,max_x,min_y,max_y,min_z,max_z);
            CREATE TRIGGER IF NOT EXISTS mirror_spatial_delete AFTER DELETE ON mirror_objects
              BEGIN DELETE FROM mirror_spatial WHERE id=old.rowid; END;
        """)
        spatial_ready = self.db.execute("SELECT 1 FROM mirror_configuration WHERE name='spatial_schema' AND value='1'").fetchone()
        if not spatial_exists or not spatial_ready:
            with self.db:
                for row in self.db.execute('SELECT rowid,footprint FROM mirror_objects'):
                    self.db.execute('INSERT OR REPLACE INTO mirror_spatial VALUES (?,?,?,?,?,?,?)',
                                    (row['rowid'], *_footprint_bounds(np.asarray(_decode(row['footprint'])))))
                self.db.execute("INSERT OR REPLACE INTO mirror_configuration VALUES ('spatial_schema','1')")
        existing = self.db.execute("SELECT value FROM mirror_configuration WHERE name='root'").fetchone()
        if existing and existing[0] != self.root:
            fail('archive_mirror_configuration', 'Index belongs to a different mirror root')
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO mirror_configuration VALUES ('root', ?)", (self.root,))
            for release in self.releases:
                self.db.execute('INSERT OR IGNORE INTO mirror_pages(release) VALUES (?)', (release,))

    def _capacity(self, extra=0):
        total = sum(p.stat().st_size for p in (self.path, Path(str(self.path)+'-wal'), Path(str(self.path)+'-shm')) if p.exists())
        free = shutil.disk_usage(self.path.parent).free
        if total + extra > self.max_index_bytes or free - extra < 256 * 1024 * 1024:
            fail('archive_mirror_capacity', 'Mirror metadata disk budget reached or less than 256 MiB free; indexed partial results remain available')

    @_read_snapshot
    def status(self):
        marks = ','.join('?' for _ in self.releases)
        states = [dict(r) for r in self.db.execute(f'SELECT * FROM mirror_pages WHERE release IN ({marks})', self.releases)]
        total = self.db.execute(f'SELECT COUNT(*) FROM mirror_objects WHERE release IN ({marks})', self.releases).fetchone()[0]
        failed = self.db.execute(f'SELECT COUNT(*) FROM mirror_retries WHERE release IN ({marks})', self.releases).fetchone()[0]
        listing_complete = all(bool(s['complete']) for s in states)
        catalog = self.db.execute("SELECT 1 FROM sqlite_master WHERE name='mirror_catalog_releases'").fetchone()
        catalog_status = {}
        if catalog:
            discovered = self.db.execute(f'SELECT COUNT(*) FROM mirror_catalog_releases WHERE discovered=1 AND release IN ({marks})', self.releases).fetchone()[0]
            partitions = self.db.execute(f'SELECT COUNT(*),COALESCE(SUM(complete),0),COALESCE(SUM(pages),0) FROM mirror_catalog_partitions WHERE release IN ({marks})', self.releases).fetchone()
            listing_complete = discovered == len(self.releases) and partitions[0] == partitions[1]
            catalog_status = {'catalogue': {'releases_discovered': discovered, 'partitions': partitions[0], 'partitions_complete': partitions[1], 'pages_processed': partitions[2]}}

        return {'complete': listing_complete and failed == 0, 'listing_complete': listing_complete, 'failed_objects': failed,
                'objects_indexed': total, 'releases': states, 'source': 's3_mirror', **catalog_status}

    def reset(self):
        with self.db:
            for release in self.releases:
                self.db.execute('UPDATE mirror_pages SET token=NULL,complete=0,pages=0 WHERE release=?', (release,))
                self.db.execute('DELETE FROM mirror_objects WHERE release=?', (release,))
                self.db.execute('DELETE FROM mirror_retries WHERE release=?', (release,))
                if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='mirror_catalog_releases'").fetchone():
                    self.db.execute('DELETE FROM mirror_catalog_partitions WHERE release=?', (release,))
                    self.db.execute('DELETE FROM mirror_catalog_directories WHERE release=?', (release,))
                    self.db.execute('DELETE FROM mirror_catalog_releases WHERE release=?', (release,))
        return {'index': self.status()}

    def _list(self, release, token, page_size):
        params = {'list-type': '2', 'prefix': release + '/level2/', 'max-keys': page_size}
        if token:
            params['continuation-token'] = token
        body, _ = _http(self.root + '?' + urllib.parse.urlencode(params), 3 * 1024 * 1024)
        try:
            tree = ET.fromstring(body)
            def text(node, tag):
                found = node.find('{*}' + tag)
                return found.text if found is not None else None
            truncated = text(tree, 'IsTruncated')
            if truncated not in ('true', 'false'):
                raise ValueError('Missing IsTruncated')
            nxt = text(tree, 'NextContinuationToken')
            if truncated == 'true' and (not nxt or nxt == token or len(nxt) > 8192):
                raise ValueError('Invalid continuation token')
            objects = []
            for item in tree.findall('{*}Contents'):
                key = text(item, 'Key')
                if key and key.endswith('/'):
                    continue
                if key and not key.endswith('.fits'):
                    continue
                _key(key, [release])
                identity = json.dumps([text(item, 'ETag'), text(item, 'Size'), text(item, 'LastModified')])
                if not text(item, 'ETag') or not text(item, 'Size'):
                    raise ValueError('Missing object identity')
                objects.append((key, identity))
            if len(objects) > page_size:
                raise ValueError('Listing exceeds requested page size')
            return objects, nxt if truncated == 'true' else None
        except (ET.ParseError, TypeError, ValueError) as exc:
            fail('archive_mirror_listing_invalid', str(exc))

    def _object(self, key, identity):
        _key(key, self.releases)
        url = self.root + urllib.parse.quote(key, safe='/')
        etag, listed_size, _ = json.loads(identity)
        listed_size = int(listed_size)
        if not etag or listed_size <= 0:
            fail('archive_mirror_metadata_invalid', 'Invalid listed content identity')
        for limit in (65536, 131072, HEADER_LIMIT):
            body, response_headers = _http(url, limit, {'Range': f'bytes=0-{limit-1}', 'If-Match': etag}, ranged=True)
            actual_size = int(response_headers['content-range'].split('/')[1])
            if actual_size != listed_size or response_headers.get('etag', etag) != etag:
                fail('archive_mirror_object_changed', 'Object content identity changed since S3 listing')
            try:
                primary, image = _headers(body)
                break
            except _NeedHeader:
                if len(body) < limit or limit == HEADER_LIMIT:
                    fail('archive_mirror_header_limit', 'IMAGE metadata is not available within 256 KiB')
        combined = primary.copy()
        combined.extend(image, update=True)
        detector = int(combined.get('DETECTOR', 0))
        if detector not in range(1, 7):
            fail('archive_mirror_metadata_invalid', 'FITS detector identity is unavailable')
        if combined.get('TIMESYS', 'UTC').strip().upper() != 'UTC':
            fail('archive_mirror_metadata_invalid', 'Unsupported FITS time scale')
        if combined.get('DATE-OBS'):
            observed = _instant(combined['DATE-OBS'])
        elif combined.get('MJD-OBS') is not None:
            observed = Time(float(combined['MJD-OBS']), format='mjd', scale='utc').to_datetime(timezone=dt.timezone.utc)
        else:
            fail('archive_mirror_metadata_invalid', 'FITS observation date is unavailable')
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            wcs = WCS(image, relax=True).celestial
        if not wcs.has_celestial or image.get('NAXIS', 0) != 2:
            fail('archive_mirror_metadata_invalid', 'Celestial IMAGE WCS is unavailable')
        nx, ny = int(image['NAXIS1']), int(image['NAXIS2'])
        if nx <= 0 or ny <= 0:
            fail('archive_mirror_metadata_invalid', 'IMAGE dimensions are invalid')
        # Sample SIP-distorted boundaries, retaining true pixel edges.
        x = np.linspace(-0.5, nx-0.5, 17)
        y = np.linspace(-0.5, ny-0.5, 17)
        pixels = np.asarray([(a, -0.5) for a in x[:-1]] + [(nx-0.5, b) for b in y[:-1]] + [(a, ny-0.5) for a in x[::-1][:-1]] + [(-0.5, b) for b in y[::-1][:-1]])
        sky = wcs.all_pix2world(pixels, 0)
        if not np.all(np.isfinite(sky)):
            fail('archive_mirror_metadata_invalid', 'Nonfinite IMAGE footprint')
        # all_pix2world follows CTYPE axis ordering; retain ICRS RA,Dec ordering.
        footprint = _vectors(sky[:, [wcs.wcs.lng, wcs.wcs.lat]])
        release = key.split('/')[0]
        metadata = {'discovery_source': 's3_mirror', 'survey': 'unknown', 'source_key': key, 'content_identity': identity,
                    'native_frame_id': key.rsplit('/', 1)[-1][:-5],
                    'observation_time_source': 'DATE-OBS' if combined.get('DATE-OBS') else 'MJD-OBS',
                    'energy_bandpassname': f'SPHEREx-D{detector}', 'obs_collection': 'spherex_' + release,
                    't_min': str(Time(observed, scale='utc').mjd)}
        if re.fullmatch(r'level2_[A-Za-z0-9_.-]+\.fits', key.rsplit('/', 1)[-1]):
            metadata['dataproduct_subtype'] = 'science'
        for name in ('OBSID', 'EXPIDN', 'DATE-OBS', 'MJD-OBS', 'DETECTOR', 'SPS_FLAGS', 'NON_SURVEY', 'SPS_TARGET', 'DATE-BEG', 'DATE-END'):
            if name in combined:
                metadata[name] = str(combined[name]).strip()
        observation = {'frame_id': f'{release.upper()}-D{detector}-' + hashlib.sha256(key.encode()).hexdigest(), 'observation_date': _stamp(observed), 'detector_array': detector,
                       'release': release.upper(), 'is_available': True, 'header_metadata': metadata}
        return (key, release, identity, json.dumps({'observation': observation, 'accessUrl': url}), json.dumps(footprint.tolist()), observed.timestamp(), detector)

    def _read_objects(self, pending, workers):
        succeeded, failed = [], []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            tasks = {pool.submit(self._object, key, identity): (key, identity) for key, identity in pending}
            for future in as_completed(tasks):
                key, identity = tasks[future]
                try:
                    succeeded.append(future.result())
                except Exception as exc:
                    failed.append({'key': key, 'identity': identity,
                                   'code': str(getattr(exc, 'code', 'archive_mirror_metadata_invalid'))[:80],
                                   'message': str(exc)[:480]})
        return succeeded, failed

    def _persist_outcomes(self, pending, succeeded, failed, checkpoint=None):
        """Durable verified rows OR retry rows must precede page advancement.

        A crash between outcomes and checkpoint replays a page safely. Capacity
        errors never create thousands of failure rows or advance a checkpoint.
        Keep resolved retry rows until postwrite capacity validation succeeds.
        """
        written = 0
        capacity_error = next((error for error in failed if error['code'] == 'archive_mirror_capacity'), None)
        if capacity_error:
            return written, MirrorError('archive_mirror_capacity', capacity_error['message'])
        try:
            stored = [(key, release, identity, zlib.compress(body.encode()), zlib.compress(footprint.encode()), observed, detector)
                      for key, release, identity, body, footprint, observed, detector in succeeded]
            growth = sum(len(row[3]) + len(row[4]) + 2048 for row in stored)
            growth += sum(len(item['identity'].encode()) + len(item['key'].encode()) + 2048 for item in failed)
            self._capacity(extra=growth + 16384)
            now = time.time()
            with self.db:
                for key, _ in pending:
                    self.db.execute('DELETE FROM mirror_objects WHERE key=?', (key,))
                self.db.executemany('INSERT OR REPLACE INTO mirror_objects VALUES (?,?,?,?,?,?,?)', stored)
                for row in succeeded:
                    rowid = self.db.execute('SELECT rowid FROM mirror_objects WHERE key=?', (row[0],)).fetchone()[0]
                    self.db.execute('INSERT OR REPLACE INTO mirror_spatial VALUES (?,?,?,?,?,?,?)',
                                    (rowid, *_footprint_bounds(np.asarray(json.loads(row[4])))))
                for item in failed:
                    previous = self.db.execute('SELECT identity,attempts FROM mirror_retries WHERE key=?', (item['key'],)).fetchone()
                    attempts = previous['attempts']+1 if previous and previous['identity'] == item['identity'] else 1
                    delay = min(3600, 60 * 2 ** min(attempts-1, 6))
                    details = {'code': item['code'], 'message': item['message']}
                    error = json.dumps(details, ensure_ascii=False)
                    while len(error.encode()) > 640:
                        details['message'] = details['message'][:len(details['message'])//2]
                        error = json.dumps(details, ensure_ascii=False)
                    self.db.execute('INSERT OR REPLACE INTO mirror_retries VALUES (?,?,?,?,?,?,?)',
                                    (item['key'], item['key'].split('/')[0], item['identity'], error, now, now+delay, attempts))
            written = len(succeeded)
            self._capacity(extra=16384)
            with self.db:
                self.db.executemany('DELETE FROM mirror_retries WHERE key=?', ((row[0],) for row in succeeded))
                if checkpoint:
                    release, previous_token, next_token = checkpoint
                    self.db.execute('UPDATE mirror_pages SET token=?,complete=?,pages=pages+1 WHERE release=? AND token IS ? AND complete=0',
                                    (next_token, int(next_token is None), release, previous_token))
            return written, None
        except MirrorError as exc:
            return written, exc
        except sqlite3.OperationalError as exc:
            if getattr(exc, 'sqlite_errorcode', None) == sqlite3.SQLITE_FULL:
                return written, MirrorError('archive_mirror_capacity', 'SQLite metadata capacity exhausted; page remains resumable')
            raise

    def scan(self, page_size=100, max_pages=1, workers=4):
        if not 1 <= page_size <= 1000 or not 1 <= max_pages <= 10000 or not 1 <= workers <= 8:
            fail('invalid_request', 'scan page-size 1..1000, max-pages 1..10000, workers 1..8 required')
        pages, indexed, retried, errors_total = 0, 0, 0, 0
        errors = []
        def report(error):
            nonlocal errors_total
            errors_total += 1
            if len(errors) < 20:
                errors.append({key: value for key, value in error.items() if key != 'identity'})
        def result():
            return {'index': self.status(), 'pages_processed': pages, 'objects_indexed': indexed,
                    'retry_objects_processed': retried, 'errors': errors, 'errors_total': errors_total}

        # Retry a small due batch, then continue discovering fresh sky even when
        # some objects remain unavailable. Backoff is persisted across processes.
        marks = ','.join('?' for _ in self.releases)
        due = self.db.execute(f'SELECT key,identity FROM mirror_retries WHERE release IN ({marks}) AND next_attempt<=? ORDER BY next_attempt,key LIMIT ?',
                              (*self.releases, time.time(), min(page_size, workers*2, 16))).fetchall()
        if due:
            try:
                self._capacity()
            except MirrorError as exc:
                report({'code': exc.code, 'message': exc.message})
                return result()
            pending = [(row['key'], row['identity']) for row in due]
            succeeded, failed = self._read_objects(pending, workers)
            retried = len(pending)
            written, capacity = self._persist_outcomes(pending, succeeded, failed)
            indexed += written
            for error in failed:
                report(error)
            if capacity:
                report({'code': capacity.code, 'message': capacity.message})
                return result()

        # Persisted completed-page counts provide release round robin scheduling.
        # Configured order decides ties, preserving QR2 initial priority.
        while pages < max_pages:
            states = {row['release']: row for row in self.db.execute(f'SELECT * FROM mirror_pages WHERE release IN ({marks}) AND complete=0', self.releases)}
            if not states:
                break
            release = min(states, key=lambda value: (states[value]['pages'], self.releases.index(value)))
            state = states[release]
            try:
                self._capacity()
                objects, token = self._list(release, state['token'], page_size)
            except MirrorError as exc:
                report({'code': exc.code, 'message': exc.message})
                break
            pending = []
            for key, identity in objects:
                old = self.db.execute('SELECT identity FROM mirror_objects WHERE key=?', (key,)).fetchone()
                if not old or old[0] != identity:
                    pending.append((key, identity))
            succeeded, failed = self._read_objects(pending, workers)
            written, capacity = self._persist_outcomes(pending, succeeded, failed, (release, state['token'], token))
            indexed += written
            for error in failed:
                report(error)
            if capacity:
                report({'code': capacity.code, 'message': capacity.message})
                break
            pages += 1
        return result()

    @_read_snapshot
    def search(self, query, limit=256):
        if not isinstance(query, dict) or not 1 <= limit <= 256:
            fail('invalid_request', 'A query object and limit 1..256 are required')
        if query.get('channel') is not None:
            fail('archive_mirror_channel_unsupported', 'Mirror header indexing cannot apply wavelength channel calibration')
        if query.get('deep'):
            fail('archive_mirror_survey_unsupported', 'Deep survey identity is not verified by this mirror index')
        matches = _region(query.get('position'))
        after = _instant(query['after']).timestamp() if query.get('after') else None
        before = _instant(query['before']).timestamp() if query.get('before') else None
        if after is not None and before is not None and after > before:
            fail('invalid_request', 'after must not exceed before')
        clauses = ['release IN (' + ','.join('?' for _ in self.releases) + ')']
        values = list(self.releases)
        detector = query.get('detector')
        if detector is not None:
            if isinstance(detector, bool) or not isinstance(detector, int) or detector not in range(1, 7):
                fail('invalid_request', 'detector must be an integer 1..6')
            clauses.append('detector=?')
            values.append(detector)
        for bound, op in ((after, '>='), (before, '<=')):
            if bound is not None:
                clauses.append('observed' + op + '?')
                values.append(bound)
        status = self.status()
        bounds = _query_bounds(query['position'])
        spatial_clauses, spatial_values = [], []
        for axis, lo, hi in zip(('x', 'y', 'z'), bounds[::2], bounds[1::2]):
            spatial_clauses.extend((f'min_{axis}<=?', f'max_{axis}>=?'))
            spatial_values.extend((hi, lo))
        images = []
        # CROSS JOIN fixes the RTree as the outer lookup rather than a full
        # release/time scan. Geometry decoding is limited to sky candidates.
        sql = 'SELECT body,footprint FROM mirror_spatial CROSS JOIN mirror_objects ON mirror_objects.rowid=mirror_spatial.id WHERE '
        sql += ' AND '.join(spatial_clauses + clauses) + ' ORDER BY observed,key'
        for row in self.db.execute(sql, spatial_values + values):
            if matches(np.asarray(_decode(row['footprint']))):
                item = _decode(row['body'])
                item['observation']['header_metadata']['discovery_complete'] = str(status['complete']).lower()
                images.append(item)
                if len(images) > limit:
                    fail('archive_mirror_result_overflow', f'More than {limit} matching images; narrow the position, date, or detector query')
        if not images and not status['complete']:
            fail('archive_mirror_index_warming', 'Mirror index is incomplete; retry after metadata ingestion progresses')
        return {'images': images, 'index': status}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--root', default=OFFICIAL_ROOT)
    parser.add_argument('--releases', default='qr2,dr1,qr3')
    subs = parser.add_subparsers(dest='command', required=True)
    scan = subs.add_parser('scan')
    scan.add_argument('--page-size', type=int, default=100)
    scan.add_argument('--max-pages', type=int, default=1)
    scan.add_argument('--workers', type=int, default=4)
    catalog = subs.add_parser('catalog')
    catalog.add_argument('--page-size', type=int, default=128)
    catalog.add_argument('--max-pages', type=int, default=64)
    catalog.add_argument('--workers', type=int, default=32)
    catalog.add_argument('--max-seconds', type=float, default=180)
    subs.add_parser('status')
    search = subs.add_parser('search')
    search.add_argument('--limit', type=int, default=256)
    subs.add_parser('reset')
    args = parser.parse_args(argv)
    try:
        idx = MirrorIndex(args.db, args.root, args.releases.split(','))
        if args.command == 'scan':
            result = idx.scan(args.page_size, args.max_pages, args.workers)
        elif args.command == 'catalog':
            sys.modules.setdefault('irsa_mirror', sys.modules[__name__])
            from irsa_catalog import scan_catalog
            result = scan_catalog(idx, args.page_size, args.max_pages, args.workers, args.max_seconds)
        elif args.command == 'status':
            result = {'index': idx.status()}
        elif args.command == 'search':
            raw = sys.stdin.read(65537)
            if len(raw) > 65536:
                fail('invalid_request', 'Query exceeds 64 KiB')
            result = idx.search(json.loads(raw), args.limit)
        else:
            result = idx.reset()
        print(json.dumps(result, allow_nan=False))
        return 0
    except MirrorError as exc:
        print(json.dumps({'error': {'code': exc.code, 'message': exc.message}}))
        return 2
    except (ValueError, TypeError, sqlite3.Error) as exc:
        print(json.dumps({'error': {'code': 'archive_mirror_index_error', 'message': str(exc)[:512]}}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
