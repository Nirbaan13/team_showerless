"""Persistent, breadth-first metadata ingestion from the official SPHEREx mirror.

Directory discovery and object checkpoints are separate: a restart neither loses
verified headers nor mistakes one scanned detector/time slice for the whole sky.
All HTTP reads and science metadata validation use the mirror's bounded reader.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET

import irsa_mirror as mirror


def _text(node, name):
    child = node.find('{*}' + name)
    return child.text if child is not None else None


def _listing(index, prefix, token=None, page_size=1000, delimiter=False):
    params = {'list-type': '2', 'prefix': prefix, 'max-keys': page_size}
    if token:
        params['continuation-token'] = token
    if delimiter:
        params['delimiter'] = '/'
    body, _ = mirror._http(index.root + '?' + urllib.parse.urlencode(params), 3 * 1024 * 1024)
    try:
        tree = ET.fromstring(body)
        truncated = _text(tree, 'IsTruncated')
        if truncated not in ('true', 'false'):
            raise ValueError('Missing IsTruncated')
        nxt = _text(tree, 'NextContinuationToken')
        if truncated == 'true' and (not nxt or nxt == token or len(nxt) > 8192):
            raise ValueError('Invalid continuation token')
        values = []
        if delimiter:
            for entry in tree.findall('{*}CommonPrefixes'):
                child = _text(entry, 'Prefix')
                if not child or not child.startswith(prefix) or not re.fullmatch(r'[A-Za-z0-9_.-]+/', child[len(prefix):]):
                    raise ValueError('Invalid child directory prefix')
                if child[len(prefix):] in ('./', '../'):
                    raise ValueError('Unsafe directory prefix')
                values.append(child)
            # A changed upstream layout must not silently become an empty index.
            if any((_text(entry, 'Key') or '').endswith('.fits') for entry in tree.findall('{*}Contents')):
                raise ValueError('Unexpected FITS outside the documented directory hierarchy')
        else:
            for entry in tree.findall('{*}Contents'):
                key = _text(entry, 'Key')
                if not key or not key.endswith('.fits'):
                    continue
                mirror._key(key, index.releases)
                if not key.startswith(prefix):
                    raise ValueError('Object outside the requested partition')
                etag, size = _text(entry, 'ETag'), _text(entry, 'Size')
                if not etag or not size or int(size) <= 0:
                    raise ValueError('Missing object identity')
                values.append((key, json.dumps([etag, size, _text(entry, 'LastModified')])))
        if len(values) > page_size:
            raise ValueError('Listing exceeds requested page size')
        return values, nxt if truncated == 'true' else None
    except (ET.ParseError, TypeError, ValueError) as exc:
        mirror.fail('archive_mirror_listing_invalid', str(exc))


def _directories(index, prefix, deadline):
    result, token, seen = [], None, set()
    while True:
        if time.monotonic() >= deadline:
            mirror.fail('archive_mirror_catalog_yield', 'Directory discovery will resume in the next ingestion batch')
        children, nxt = _listing(index, prefix, token, delimiter=True)
        result.extend(children)
        if len(result) > 100000:
            mirror.fail('archive_mirror_listing_invalid', 'Directory listing exceeds the catalogue partition limit')
        if nxt is None:
            return sorted(set(result))
        if nxt in seen:
            mirror.fail('archive_mirror_listing_invalid', 'Directory continuation token cycle')
        seen.add(nxt)
        token = nxt


def _schema(index):
    index.db.executescript('''
        CREATE TABLE IF NOT EXISTS mirror_catalog_releases (
            release TEXT PRIMARY KEY, discovered INTEGER NOT NULL DEFAULT 0,
            enumerated INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS mirror_catalog_directories (
            prefix TEXT PRIMARY KEY, release TEXT NOT NULL, complete INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS mirror_catalog_partitions (
            prefix TEXT PRIMARY KEY, release TEXT NOT NULL, token TEXT,
            complete INTEGER NOT NULL DEFAULT 0, pages INTEGER NOT NULL DEFAULT 0,
            ordinal INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS mirror_catalog_schedule ON mirror_catalog_partitions(complete,pages,ordinal);
    ''')
    with index.db:
        index.db.executemany('INSERT OR IGNORE INTO mirror_catalog_releases(release) VALUES (?)', ((release,) for release in index.releases))


def _discover(index, deadline, report):
    """Persist each planning period independently; commit completeness last."""
    for release in index.releases:
        if time.monotonic() >= deadline:
            return
        state = index.db.execute('SELECT * FROM mirror_catalog_releases WHERE release=?', (release,)).fetchone()
        if state['discovered']:
            continue
        if not state['enumerated']:
            try:
                periods = _directories(index, release + '/level2/', deadline)
                index._capacity(extra=sum(len(period) + 512 for period in periods) + 16384)
                with index.db:
                    index.db.executemany('INSERT OR IGNORE INTO mirror_catalog_directories(prefix,release) VALUES (?,?)', ((prefix, release) for prefix in periods))
                    index.db.execute('UPDATE mirror_catalog_releases SET enumerated=1 WHERE release=?', (release,))
            except mirror.MirrorError as exc:
                report({'code': exc.code, 'message': exc.message})
                continue
        periods = index.db.execute('SELECT prefix FROM mirror_catalog_directories WHERE release=? AND complete=0 ORDER BY prefix', (release,)).fetchall()
        # Only a bounded batch is submitted, so a deadline never leaves hundreds
        # of queued network calls running after this process should have yielded.
        for offset in range(0, len(periods), 16):
            if time.monotonic() >= deadline:
                break
            with ThreadPoolExecutor(max_workers=16) as pool:
                tasks = {pool.submit(_directories, index, row['prefix'], deadline): row['prefix'] for row in periods[offset:offset+16]}
                for future in as_completed(tasks):
                    period = tasks[future]
                    try:
                        versions = future.result()
                        partitions = [version + str(detector) + '/' for version in versions for detector in range(1, 7)]
                        index._capacity(extra=sum(len(prefix) + 512 for prefix in partitions) + 16384)
                        with index.db:
                            # Ordinals interleave periods and detectors; the
                            # number of committed pages is the first priority.
                            for prefix in partitions:
                                index.db.execute('INSERT OR IGNORE INTO mirror_catalog_partitions(prefix,release,ordinal) VALUES (?,?,?)',
                                                 (prefix, release, 0))
                            index.db.execute('UPDATE mirror_catalog_directories SET complete=1 WHERE prefix=?', (period,))
                    except mirror.MirrorError as exc:
                        report({'code': exc.code, 'message': exc.message, 'prefix': period})
        remaining = index.db.execute('SELECT 1 FROM mirror_catalog_directories WHERE release=? AND complete=0 LIMIT 1', (release,)).fetchone()
        if not remaining:
            with index.db:
                index.db.execute('UPDATE mirror_catalog_releases SET discovered=1 WHERE release=?', (release,))
    # A deterministic breadth order independent of asynchronous directory timing.
    partitions = index.db.execute('SELECT prefix,release FROM mirror_catalog_partitions').fetchall()
    ordered = sorted(partitions, key=lambda row: (row['prefix'].split('/')[2], row['prefix'].split('/')[-2], index.releases.index(row['release']) if row['release'] in index.releases else len(index.releases), row['prefix']))
    with index.db:
        index.db.executemany('UPDATE mirror_catalog_partitions SET ordinal=? WHERE prefix=?', ((number, row['prefix']) for number, row in enumerate(ordered)))


def scan_catalog(index, page_size=128, max_pages=64, workers=32, max_seconds=180):
    """Run one bounded ingestion batch; return the existing mirror JSON protocol."""
    if not (1 <= page_size <= 1000 and 1 <= max_pages <= 10000 and 1 <= workers <= 256 and 1 <= max_seconds <= 600):
        mirror.fail('invalid_request', 'catalog page-size 1..1000, max-pages 1..10000, workers 1..256, max-seconds 1..600 required')
    deadline = time.monotonic() + max_seconds
    pages = indexed = retried = errors_total = 0
    errors = []
    def report(error):
        nonlocal errors_total
        errors_total += 1
        if len(errors) < 20:
            errors.append({key: value for key, value in error.items() if key != 'identity'})
    def result():
        return {'index': index.status(), 'pages_processed': pages, 'objects_indexed': indexed,
                'retry_objects_processed': retried, 'errors': errors, 'errors_total': errors_total}
    _schema(index)
    try:
        index._capacity()
    except mirror.MirrorError as exc:
        report({'code': exc.code, 'message': exc.message})
        return result()
    _discover(index, deadline, report)
    marks = ','.join('?' for _ in index.releases)
    due = index.db.execute(f'SELECT key,identity FROM mirror_retries WHERE release IN ({marks}) AND next_attempt<=? ORDER BY next_attempt,key LIMIT ?',
                           (*index.releases, time.time(), min(page_size, workers * 2))).fetchall()
    if due and time.monotonic() < deadline:
        pending = [(row['key'], row['identity']) for row in due]
        succeeded, failed = index._read_objects(pending, workers)
        written, capacity = index._persist_outcomes(pending, succeeded, failed)
        indexed += written
        retried = len(pending)
        for error in failed:
            report(error)
        if capacity:
            report({'code': capacity.code, 'message': capacity.message})
            return result()
    skipped = set()
    while pages < max_pages and time.monotonic() < deadline:
        rows = index.db.execute(f'SELECT * FROM mirror_catalog_partitions WHERE release IN ({marks}) AND complete=0 ORDER BY pages,ordinal,prefix', index.releases).fetchall()
        rows = [row for row in rows if row['prefix'] not in skipped]
        if not rows:
            break
        depth = rows[0]['pages']
        # At most four header-request waves per batch, even with one
        # worker or a caller requesting very large listing pages. A network
        # outage therefore cannot turn one batch into thousands of timeouts.
        budget = min(1024, workers * 4)
        size = 1 if depth == 0 else min(page_size, budget)
        width = min(32, workers, max_pages - pages, max(1, budget // size))
        batch = [row for row in rows if row['pages'] == depth][:width]
        listed = []
        with ThreadPoolExecutor(max_workers=min(32, len(batch))) as pool:
            tasks = {pool.submit(_listing, index, row['prefix'], row['token'], size): row for row in batch}
            for future in as_completed(tasks):
                row = tasks[future]
                try:
                    objects, token = future.result()
                    listed.append((row, objects, token))
                except mirror.MirrorError as exc:
                    skipped.add(row['prefix'])
                    report({'code': exc.code, 'message': exc.message, 'prefix': row['prefix']})
        pending = []
        for _, objects, _ in listed:
            for key, identity in objects:
                old = index.db.execute('SELECT identity FROM mirror_objects WHERE key=?', (key,)).fetchone()
                retry = index.db.execute('SELECT identity FROM mirror_retries WHERE key=?', (key,)).fetchone()
                if (not old or old[0] != identity) and (not retry or retry[0] != identity):
                    pending.append((key, identity))
        succeeded, failed = index._read_objects(pending, workers)
        written, capacity = index._persist_outcomes(pending, succeeded, failed)
        indexed += written
        for error in failed:
            report(error)
        if capacity:
            report({'code': capacity.code, 'message': capacity.message})
            break
        # Outcomes are durable before checkpoint advancement. A crash here
        # replays listings while verified identities avoid duplicate header I/O.
        with index.db:
            for row, _, token in listed:
                index.db.execute('UPDATE mirror_catalog_partitions SET token=?,complete=?,pages=pages+1 WHERE prefix=? AND token IS ? AND pages=?',
                                 (token, int(token is None), row['prefix'], row['token'], row['pages']))
        pages += len(listed)
    return result()
