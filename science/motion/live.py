"""Search IRSA and track moving sources in a bounded stack of real cutouts."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from math import ceil, isfinite
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import os
from time import monotonic
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, build_opener
from xml.etree import ElementTree

import numpy as np

from science import archive_gateway

from .prepare_fits import align_exposure, grid_coordinates, stack_payload
from .review import build_review


def bounded_env_int(name, default, maximum):
    message = f'{name} must be an integer between 1 and {maximum}'
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ValueError(message) from exc
    if not 1 <= value <= maximum:
        raise ValueError(message)
    return value


FETCH_WORKERS = bounded_env_int('MOTION_FETCH_WORKERS', 4, 8)
ARCHIVE_HOST = 'irsa.ipac.caltech.edu'
COLLECTIONS = tuple(
    c.strip() for c in os.getenv('SPHEREX_COLLECTIONS', 'spherex_dr1,spherex_qr3,spherex_qr2,spherex_dr2,spherex_qr4').split(',') if c.strip()
)
PIXEL_SCALE = 6.15
MAX_VISITS = 8
MAX_RECORDS = 256
MAX_TRACKS = 25
MAX_FITS_BYTES = 24 * 1024 * 1024
REQUEST_TIMEOUT = 18
MIN_COVERAGE = 0.50
OBSERVATION_NAME = re.compile(r'level2_(\d{4}W\d{2}_\d[A-Z]_\d{4}_\dD[1-6])_spx_.*\.fits')


class SearchError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


@dataclass(frozen=True)
class Exposure:
    id: str
    mjd: float
    url: str
    release: str
    source_url: str | None = None
    discovery_source: str = 'sia'


def read_archive(url, limit):
    deadline = monotonic() + REQUEST_TIMEOUT
    with build_opener(NoRedirects()).open(url, timeout=REQUEST_TIMEOUT) as response:
        if int(response.headers.get('Content-Length', 0)) > limit:
            raise ValueError('Archive response exceeds the byte limit')
        data = bytearray()
        while True:
            chunk = response.read1(256 * 1024)
            if monotonic() > deadline:
                raise TimeoutError('Archive transfer timed out')
            if not chunk:
                return bytes(data)
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError('Archive response exceeds the byte limit')


def mjd_day(day):
    return (day - date(1858, 11, 17)).days


def parse_exposures(content, detector, start, stop):
    if b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
        raise ValueError('Invalid archive XML')
    root = ElementTree.fromstring(content)
    statuses = [node.get('value') for node in root.findall('.//{*}INFO') if node.get('name') == 'QUERY_STATUS']
    if 'OVERFLOW' in statuses:
        raise SearchError(422, 'Too many archive records. Try a shorter date range.')
    if not statuses or any(status != 'OK' for status in statuses):
        raise ValueError('Archive query failed')

    tables = root.findall('.//{*}TABLE')
    if len(tables) != 1:
        raise ValueError('Expected one archive table')
    table = tables[0]
    fields = [node.get('name') for node in table.findall('./{*}FIELD')]
    required = {'access_url', 'energy_bandpassname', 'dataproduct_subtype', 'obs_collection', 't_min'}
    data = table.find('./{*}DATA/{*}TABLEDATA')
    if not required.issubset(fields) or data is None:
        raise ValueError('Archive response is missing observation metadata')

    exposures = {}
    for row in data:
        values = dict(zip(fields, [value.text or '' for value in row]))
        if values.get('dataproduct_subtype') != 'science' or values.get('energy_bandpassname') != f'SPHEREx-D{detector}':
            continue
        collection = values.get('obs_collection')
        if collection not in COLLECTIONS:
            continue
        time = float(values['t_min'])
        if not start <= time < stop:
            continue
        url = urlsplit(values['access_url'])
        filename = url.path.rsplit('/', 1)[-1]
        match = OBSERVATION_NAME.fullmatch(filename)
        prefix = f'/ibe/data/spherex/{collection.removeprefix("spherex_")}/level2/'
        if (url.scheme != 'https' or url.netloc != ARCHIVE_HOST or not url.path.startswith(prefix)
                or not match or not match[1].endswith(f'D{detector}')):
            continue
        identifier = match[1]
        exposure = Exposure(identifier, time, urlunsplit(url._replace(query='', fragment='')),
                            collection.removeprefix('spherex_').upper())
        if identifier not in exposures or exposure.release.startswith('DR'):
            exposures[identifier] = exposure
    return sorted(exposures.values(), key=lambda exposure: (exposure.mjd, exposure.id))


def discover(ra, dec, detector, start, stop):
    if archive_gateway.configured():
        try:
            # The shared cone search requires a positive radius, matching the existing SIA retry.
            found = archive_gateway.discover(ra, dec, 0.001, detector=detector, start=start, stop=stop)
            if len(found) > MAX_RECORDS:
                raise SearchError(422, 'Too many archive records. Try a shorter date range.')
            exposures = {}
            for image in found:
                match = OBSERVATION_NAME.fullmatch(urlsplit(image.url).path.rsplit('/', 1)[-1])
                if (image.detector != detector or not start <= image.mjd < stop or not match
                        or not match[1].endswith(f'D{detector}')):
                    continue
                exposure = Exposure(match[1], image.mjd, image.url, image.release, image.source_url, image.discovery_source)
                if exposure.id not in exposures or exposure.release.startswith('DR'):
                    exposures[exposure.id] = exposure
            return archive_gateway.Discovery(sorted(exposures.values(), key=lambda e: (e.mjd, e.id)),
                    complete=found.discovery_complete, sources=found.discovery_source)
        except archive_gateway.GatewayError as exc:
            raise SearchError(exc.status, str(exc)) from exc
    params = [
        ('TIME', f'{start} {stop}'),
        ('CALIB', '2'), ('DPTYPE', 'image'), ('MAXREC', str(MAX_RECORDS)), ('RESPONSEFORMAT', 'VOTABLE'),
        *[('COLLECTION', collection) for collection in COLLECTIONS],
    ]
    for radius in (0.0, 0.001):
        query = urlencode([('POS', f'CIRCLE {ra} {dec} {radius:g}'), *params])
        try:
            xml = read_archive(f'https://{ARCHIVE_HOST}/SIA?{query}', 4 * 1024 * 1024)
            return parse_exposures(xml, detector, start, stop)
        except (OSError, ValueError, ElementTree.ParseError, KeyError) as exc:
            if radius:
                raise SearchError(502, 'IRSA did not return a usable observation list. Try again in a moment.') from exc


def sample_visits(exposures):
    visits = {}
    for exposure in exposures:
        visit = exposure.id.rsplit('_', 1)[0]
        visits.setdefault(visit, []).append(exposure)
    groups = list(visits.values())
    if len(groups) > MAX_VISITS:
        indices = np.linspace(0, len(groups) - 1, MAX_VISITS).round().astype(int)
        groups = [groups[index] for index in indices]
    return groups, len(visits)


def representative_exposures(group):
    # Use one exposure per visit so closely spaced dithers cannot dominate the reference or ranking.
    center = (len(group) - 1) / 2
    order = sorted(range(len(group)), key=lambda index: abs(index - center))
    return [group[index] for index in order[:2]]


def load_exposure(exposure, directory, center, size_deg, sky, retain_outliers):
    path = directory / f'{exposure.id}.fits'
    # The IRSA cutout gateway accepts a plain comma in its documented URL format.
    sizes = (round(size_deg * 1.27, 2), round(size_deg * 1.2, 2), round(size_deg * 1.32, 2))
    urls = [f'{exposure.url}?center={center[0]},{center[1]}&size={size}' for size in dict.fromkeys(sizes)]
    for url in urls:
        try:
            path.write_bytes(read_archive(url, MAX_FITS_BYTES))
        except (OSError, ValueError):
            continue
        try:
            row = align_exposure(path, *sky, retain_outliers=retain_outliers, include_bloom=True)
        except (OSError, ValueError, KeyError, IndexError, TypeError, RuntimeError):
            return None, 'unusable FITS'
        if not isfinite(row[0]) or np.isfinite(row[3]).mean() < MIN_COVERAGE:
            return None, 'insufficient valid coverage'
        return row, None
    return None, 'download failed'


def load_visit(group, directory, center, size_deg, sky, retain_outliers, start, stop):
    skipped = []
    for exposure in representative_exposures(group):
        row, reason = load_exposure(exposure, directory, center, size_deg, sky, retain_outliers)
        if reason is None and start <= row[0] < stop:
            return exposure, row, skipped
        skipped.append({'observation_id': exposure.id, 'reason': reason or 'exposure midpoint outside the date range'})
    return None, None, skipped


def search_motion(ra, dec, detector, start_date, end_date, size_arcmin, retain_outliers):
    start, stop = mjd_day(start_date), mjd_day(end_date + timedelta(days=1))
    discovered = discover(ra, dec, detector, start, stop)
    groups, visit_count = sample_visits(discovered)
    if len(groups) < 3:
        if not getattr(discovered, 'discovery_complete', True):
            raise SearchError(503, f'Archive discovery is incomplete and currently contains {visit_count} visits. '
                                   'At least 3 visits are needed. Try again as the index grows.')
        raise SearchError(404, f'IRSA found {visit_count} visits for D{detector}. '
                               'Choose another detector or date range. At least 3 visits are needed.')
    center = (ra, dec)
    width = ceil(size_arcmin * 60 / PIXEL_SCALE)
    _, sky = grid_coordinates(*center, width, width, PIXEL_SCALE)
    with TemporaryDirectory(prefix='spherex-motion-') as tmp, ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        futures = [pool.submit(load_visit, group, Path(tmp), center, size_arcmin / 60, sky, retain_outliers, start, stop)
                   for group in groups]
        rows, skipped, provenance = {}, [], {}
        for future in futures:
            exposure, row, failed = future.result()
            skipped.extend(failed)
            if row is None:
                continue
            if row[0] not in rows:
                rows[row[0]] = row
                provenance[exposure.id] = {'archive_url': exposure.url, 'release': exposure.release,
                                           'source_url': exposure.source_url or exposure.url,
                                           'discovery_source': exposure.discovery_source}
            else:
                skipped.append({'observation_id': exposure.id, 'reason': 'duplicate exposure midpoint'})
    if len(rows) < 3:
        failed = sum(entry['reason'] == 'download failed' for entry in skipped)
        status = 502 if failed else 422
        raise SearchError(status, f'Only {len(rows)} of {len(groups)} selected visits could be aligned. '
                                  f'{failed} downloads failed. At least 3 usable exposures are needed.')

    payload = stack_payload(rows.values(), center, PIXEL_SCALE, retain_outliers)
    result = build_review(payload, 'live', f'RA {ra:.5f}°, Dec {dec:.5f}°', f'D{detector}',
                          'https://irsa.ipac.caltech.edu/Missions/spherex.html', track_limit=MAX_TRACKS)
    for frame in result['frames']:
        frame.update(provenance[frame['id']])
    result['live_search'] = {
        'ra_deg': ra, 'dec_deg': dec, 'detector': detector, 'size_arcmin': size_arcmin,
        'start_date': start_date.isoformat(), 'end_date': end_date.isoformat(),
        'archive_exposures': len(discovered), 'archive_visits': visit_count,
        'discovery_complete': getattr(discovered, 'discovery_complete', True),
        'discovery_source': getattr(discovered, 'discovery_source', ['sia']),
        'attempted_exposures': len(rows) + len(skipped),
        'skipped': skipped, 'result_limit_per_method': MAX_TRACKS,
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }
    return result
