"""Bounded client for the application's shared IRSA discovery infrastructure.

A configured gateway owns discovery and outage handling. Callers must propagate
its failures rather than creating independent retries, breakers, or SIA requests.
The returned URL is the official IBE original so callers can request real cutouts.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from math import isfinite
import os
import re
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 2048
REQUEST_TIMEOUT = 45
MJD_EPOCH = datetime(1858, 11, 17, tzinfo=timezone.utc)
ARCHIVE_HOST = 'irsa.ipac.caltech.edu'
MIRROR_HOSTS = {'nasa-irsa-spherex.s3.amazonaws.com', 'nasa-irsa-spherex.s3.us-east-1.amazonaws.com'}
RELEASES = {'QR2', 'QR3', 'DR1'}


class GatewayError(ValueError):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


@dataclass(frozen=True)
class Image:
    frame_id: str
    observation_date: str
    mjd: float
    detector: int
    release: str
    url: str
    source_url: str
    discovery_source: str


class Discovery(list):
    """List-compatible discovery result with explicit completeness and provenance."""
    def __init__(self, values=(), *, complete=True, sources=()):
        super().__init__(values)
        self.discovery_complete = complete
        self.discovery_source = sorted(set(sources))


def configured():
    return bool(os.getenv('IRSA_DISCOVERY_URL', '').strip())


def mjd_iso(value):
    return (MJD_EPOCH + timedelta(days=float(value))).isoformat().replace('+00:00', 'Z')


def canonical_url(value, release):
    """Map only official original URLs to the same exact IBE object key."""
    if not isinstance(value, str) or not value or len(value) > 4096 or any(ord(c) <= 32 or ord(c) >= 127 for c in value):
        raise GatewayError('Discovery image is missing its original archive URL')
    parts = urlsplit(value)
    if (parts.scheme != 'https' or parts.query or parts.fragment or parts.username or parts.password
            or parts.netloc not in MIRROR_HOSTS | {ARCHIVE_HOST}
            or any(c in value for c in ('%', '\\'))
            or any(p in ('.', '..', '') for p in parts.path.split('/')[1:])):
        raise GatewayError('Discovery returned an untrusted original archive URL')
    if parts.netloc == ARCHIVE_HOST:
        if not parts.path.startswith('/ibe/data/spherex/'):
            raise GatewayError('Discovery URL is not an original SPHEREx image')
        key = parts.path.removeprefix('/ibe/data/spherex/')
    else:
        key = parts.path.lstrip('/')
    if not key.startswith(f'{release.lower()}/level2/') or not key.endswith('.fits'):
        raise GatewayError('Discovery URL disagrees with the native release or product level')
    return f'https://{ARCHIVE_HOST}/ibe/data/spherex/{key}'


def _image(item):
    if not isinstance(item, dict) or not isinstance(item.get('observation'), dict):
        raise GatewayError('Discovery is missing observation metadata')
    obs = item['observation']
    frame = obs.get('frame_id')
    date = obs.get('observation_date')
    detector = obs.get('detector_array')
    release = obs.get('release')
    meta = obs.get('header_metadata')
    if (not isinstance(frame, str) or not frame.strip() or len(frame) > 2048
            or type(detector) is not int or not 1 <= detector <= 6
            or release not in RELEASES or not isinstance(meta, dict)):
        raise GatewayError('Discovery returned invalid native observation identity')
    try:
        instant = datetime.fromisoformat(date.replace('Z', '+00:00'))
        if instant.tzinfo is None:
            raise ValueError('Observation time has no timezone')
        mjd = (instant.astimezone(timezone.utc) - MJD_EPOCH).total_seconds() / 86400
    except (TypeError, ValueError, AttributeError, OverflowError) as exc:
        raise GatewayError('Discovery returned invalid observation time') from exc
    url = canonical_url(item.get('accessUrl'), release)
    original = item.get('sourceUrl') or item['accessUrl']
    if canonical_url(original, release) != url:
        raise GatewayError('Discovery returned conflicting original archive URLs')
    # Level 2 alone does not establish that a product is science data.
    if str(meta.get('dataproduct_subtype', '')).lower() != 'science':
        return None
    collection = meta.get('obs_collection')
    band = meta.get('energy_bandpassname')
    if collection is not None and collection != f'spherex_{release.lower()}':
        raise GatewayError('Discovery collection disagrees with the native release')
    if band is not None and band != f'SPHEREx-D{detector}':
        raise GatewayError('Discovery band disagrees with the native detector')
    source = meta.get('discovery_source', 'gateway')
    if not isinstance(source, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', source):
        raise GatewayError('Discovery returned invalid source metadata')
    return Image(frame, date, mjd, detector, release, url, original, source)


def discover(ra, dec, radius, *, detector=None, start=None, stop=None):
    endpoint = os.getenv('IRSA_DISCOVERY_URL', '').strip()
    if not endpoint:
        raise GatewayError('IRSA discovery gateway is not configured')
    try:
        ra, dec, radius = float(ra), float(dec), float(radius)
        if not all(isfinite(v) for v in (ra, dec, radius)) or not (0 <= ra < 360 and -90 <= dec <= 90 and 0 <= radius <= 180):
            raise ValueError('Invalid search region')
        if detector is not None and (type(detector) is not int or not 1 <= detector <= 6):
            raise ValueError('Invalid detector')
        if start is not None and stop is not None and not float(start) < float(stop):
            raise ValueError('Invalid date range')
        body = dict(right_ascension_deg=ra, declination_deg=dec, radius_degrees=radius)
        if detector is not None:
            body['detector_array'] = detector
        if start is not None:
            body['observed_after'] = mjd_iso(start)
        if stop is not None:
            body['observed_before'] = mjd_iso(stop)
        request = Request(endpoint, data=json.dumps(body, allow_nan=False).encode(),
                          headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, method='POST')
        deadline = monotonic() + REQUEST_TIMEOUT
        with build_opener(NoRedirects()).open(request, timeout=REQUEST_TIMEOUT) as response:
            if int(response.headers.get('Content-Length', 0)) > MAX_RESPONSE_BYTES:
                raise GatewayError('Discovery response exceeds the byte limit')
            data = bytearray()
            while True:
                chunk = response.read1(64 * 1024)
                if monotonic() > deadline:
                    raise GatewayError('Discovery response timed out')
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > MAX_RESPONSE_BYTES:
                    raise GatewayError('Discovery response exceeds the byte limit')
        document = json.loads(data)
        if (not isinstance(document, dict) or not isinstance(document.get('images'), list)
                or type(document.get('discovery_complete')) is not bool):
            raise GatewayError('Discovery returned an invalid result document')
        if len(document['images']) > MAX_RECORDS:
            raise GatewayError('Discovery response exceeds the record limit')
        images = [parsed for item in document['images'] if (parsed := _image(item)) is not None]
        return Discovery(images, complete=document['discovery_complete'], sources=[i.discovery_source for i in images])
    except HTTPError as exc:
        exc.close()
        raise GatewayError('IRSA discovery is temporarily unavailable', 503 if exc.code == 503 else 502) from exc
    except (URLError, OSError, ValueError, TypeError, OverflowError) as exc:
        if isinstance(exc, GatewayError):
            raise
        raise GatewayError('IRSA discovery did not return a usable observation list') from exc


def read_cutout(url, limit, timeout=18):
    """Read an IBE response with explicit byte and transfer-time bounds."""
    deadline = monotonic() + timeout
    with build_opener(NoRedirects()).open(url, timeout=timeout) as response:
        if int(response.headers.get('Content-Length', 0)) > limit:
            raise GatewayError('Archive response exceeds the byte limit')
        data = bytearray()
        while True:
            chunk = response.read1(256 * 1024)
            if monotonic() > deadline:
                raise TimeoutError('Archive transfer timed out')
            if not chunk:
                return bytes(data)
            data.extend(chunk)
            if len(data) > limit:
                raise GatewayError('Archive response exceeds the byte limit')


def _mirror_source(url, source_url=None):
    """Map an official IBE original to precisely the same public S3 key."""
    parts = urlsplit(url)
    original = parts._replace(query='', fragment='').geturl()
    prefix = '/ibe/data/spherex/'
    if parts.fragment or not parts.path.startswith(prefix):
        raise GatewayError('Cutout is not an official SPHEREx original')
    release = parts.path.removeprefix(prefix).split('/', 1)[0].upper()
    if release not in RELEASES or canonical_url(original, release) != original:
        raise GatewayError('Cutout is not an official SPHEREx original')
    if source_url and canonical_url(source_url, release) != original:
        raise GatewayError('Cutout source disagrees with the original archive object')
    if source_url and urlsplit(source_url).netloc in MIRROR_HOSTS:
        return source_url
    return f'https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/{parts.path.removeprefix(prefix)}'


def download_cutout(url, output, *, source_url=None, discovery_source='sia',
                    max_bytes=24 * 1024 * 1024, timeout=18, mirror_timeout=90, read_ibe=None):
    """Fetch an IBE cutout or crop the identical native S3 pixels during an outage.

    Mirror discovery selects S3 immediately. Other callers preserve the IBE path
    and can switch only after a retryable transport error for a verified object.
    Geometry, content, permission and absent-object errors never select S3.
    Native S3 range reads have their own bounded deadline because preserving
    the ancillary FITS tables can take longer than one IBE response.
    """
    from pathlib import Path
    output = Path(output)

    def native(source):
        from backend.python.irsa_cutout import CutoutError, cutout
        try:
            cutout(source, url, output, max_network_bytes=max_bytes,
                   max_output_bytes=max_bytes, timeout_seconds=mirror_timeout)
        except CutoutError as exc:
            raise GatewayError(str(exc)) from exc

    if discovery_source == 's3_mirror':
        if not source_url or urlsplit(source_url).netloc not in MIRROR_HOSTS:
            raise GatewayError('Mirror discovery is missing its original S3 URL')
        native(_mirror_source(url, source_url))
        return
    try:
        reader = read_ibe or (lambda value, limit: read_cutout(value, limit, timeout))
        data = reader(url, max_bytes)
    except (HTTPError, URLError, OSError) as exc:
        if isinstance(exc, HTTPError):
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            exc.close()
            if not retryable:
                raise
        try:
            source = _mirror_source(url, source_url)
        except GatewayError:
            raise exc
        native(source)
        return
    # Do not replace an existing cache entry until the complete bounded read.
    temporary = output.with_suffix(output.suffix + '.part')
    try:
        temporary.write_bytes(data)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
