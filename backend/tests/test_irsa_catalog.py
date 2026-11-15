"""Catalogue ingestion uses real FITS headers and anonymous S3-shaped HTTP."""
import importlib
import json
from pathlib import Path
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit
from xml.sax.saxutils import escape

import pytest
from test_irsa_mirror import image

sys.path.insert(0, str(Path(__file__).parents[1] / 'python'))
import irsa_mirror as mirror


@pytest.fixture
def bucket():
    state = {'objects': {}, 'requests': [], 'listings': [], 'fail': set(), 'fail_prefix': set(), 'page': 1000}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            p = urlsplit(self.path)
            q = parse_qs(p.query)
            if q.get('list-type') == ['2']:
                prefix = q['prefix'][0]
                state['listings'].append(prefix)
                if prefix in state['fail_prefix']:
                    self.send_error(503)
                    return
                keys = sorted(k for k in state['objects'] if k.startswith(prefix))
                delimiter = q.get('delimiter') == ['/']
                if delimiter:
                    keys = sorted(set(prefix + k[len(prefix):].split('/')[0] + '/' for k in keys))
                start = int(q.get('continuation-token', ['0'])[0])
                count = min(int(q['max-keys'][0]), state['page'])
                end = start + count
                more = end < len(keys)
                body = f'<ListBucketResult><IsTruncated>{str(more).lower()}</IsTruncated>'
                if more:
                    body += f'<NextContinuationToken>{end}</NextContinuationToken>'
                for key in keys[start:end]:
                    if delimiter:
                        body += f'<CommonPrefixes><Prefix>{escape(key)}</Prefix></CommonPrefixes>'
                    else:
                        body += f'<Contents><Key>{escape(key)}</Key><ETag>"id-{escape(key)}"</ETag><Size>{len(state["objects"][key])}</Size><LastModified>2026-01-01T00:00:00Z</LastModified></Contents>'
                body = (body + '</ListBucketResult>').encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            key = p.path.lstrip('/')
            state['requests'].append(key)
            if key in state['fail']:
                self.send_error(503)
                return
            data = state['objects'][key]
            end = min(int(self.headers['Range'].split('-')[1]), len(data)-1)
            self.send_response(206)
            self.send_header('Content-Range', f'bytes 0-{end}/{len(data)}')
            self.send_header('Content-Length', str(end+1))
            self.end_headers()
            self.wfile.write(data[:end+1])
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    state['root'] = f'http://127.0.0.1:{server.server_port}/'
    yield state
    server.shutdown()
    server.server_close()
    worker.join()


def add(bucket, period='2025W17_4B', detector=1, name='a', release='qr2'):
    key = f'{release}/level2/{period}/l2b-v27-2026-196/{detector}/{name}.fits'
    bucket['objects'][key] = image(detector=detector)
    return key


def idx(tmp_path, bucket):
    return mirror.MirrorIndex(tmp_path / 'mirror.sqlite', bucket['root'], ['qr2'])


def scan(index, **kwargs):
    return importlib.import_module('irsa_catalog').scan_catalog(index, **kwargs)


def test_first_samples_cover_periods_and_detectors_before_deeper_pages(tmp_path, bucket):
    first = add(bucket)
    add(bucket, name='b')
    other = add(bucket, period='2026W20_1A', detector=6)
    add(bucket, period='2026W20_1A', detector=6, name='b')
    index = idx(tmp_path, bucket)
    result = scan(index, max_pages=12, workers=8)
    assert result['objects_indexed'] == 2
    assert not result['index']['complete']
    assert set(bucket['requests']) == {first, other}
    rows = index.db.execute('SELECT prefix,pages,complete FROM mirror_catalog_partitions').fetchall()
    assert len(rows) == 12
    assert all(row['pages'] == 1 for row in rows)
    # New process resumes rather than restarting catalogue discovery or headers.
    old_listings = list(bucket['listings'])
    result = scan(idx(tmp_path, bucket), max_pages=12, workers=8)
    assert result['objects_indexed'] == 2
    assert len(bucket['requests']) == 4
    assert result['index']['complete']
    assert bucket['listings'].count('qr2/level2/') == old_listings.count('qr2/level2/')
    assert all(row['complete'] for row in index.db.execute('SELECT complete FROM mirror_catalog_partitions'))


def test_directory_pagination_and_discovery_failure_are_resumable(tmp_path, bucket):
    add(bucket)
    add(bucket, period='2026W20_1A', detector=2)
    bucket['page'] = 1
    bad = 'qr2/level2/2026W20_1A/'
    bucket['fail_prefix'].add(bad)
    index = idx(tmp_path, bucket)
    first = scan(index, max_pages=1)
    assert first['errors']
    assert not first['index']['complete']
    assert index.db.execute('SELECT discovered FROM mirror_catalog_releases').fetchone()[0] == 0
    bucket['fail_prefix'].clear()
    result = scan(idx(tmp_path, bucket), max_pages=100)
    assert not result['errors']
    assert index.db.execute('SELECT discovered FROM mirror_catalog_releases').fetchone()[0] == 1
    assert index.db.execute('SELECT COUNT(*) FROM mirror_catalog_partitions').fetchone()[0] == 12
    assert len(set(bucket['requests'])) == 2


def test_failed_headers_durable_then_retried_without_relisting(tmp_path, bucket):
    key = add(bucket)
    bucket['fail'].add(key)
    index = idx(tmp_path, bucket)
    first = scan(index, max_pages=100)
    assert first['errors']
    assert index.db.execute('SELECT COUNT(*) FROM mirror_retries').fetchone()[0] == 1
    assert not first['index']['complete']
    assert all(row['complete'] for row in index.db.execute('SELECT complete FROM mirror_catalog_partitions'))
    bucket['fail'].clear()
    with index.db:
        index.db.execute('UPDATE mirror_retries SET next_attempt=0')
    old_listings = len(bucket['listings'])
    result = scan(idx(tmp_path, bucket), max_pages=100)
    assert result['retry_objects_processed'] == 1
    assert result['index']['complete']
    assert index.db.execute('SELECT COUNT(*) FROM mirror_retries').fetchone()[0] == 0
    assert len(bucket['listings']) == old_listings


def test_capacity_failure_does_not_advance_partition(tmp_path, bucket, monkeypatch):
    add(bucket)
    index = idx(tmp_path, bucket)
    # Discovery fits but no header outcome can be committed.
    original = index._persist_outcomes
    def full(*args, **kwargs):
        return 0, mirror.MirrorError('archive_mirror_capacity', 'full')
    monkeypatch.setattr(index, '_persist_outcomes', full)
    result = scan(index, max_pages=100)
    assert result['errors'][0]['code'] == 'archive_mirror_capacity'
    assert all(row['pages'] == 0 for row in index.db.execute('SELECT pages FROM mirror_catalog_partitions'))
    monkeypatch.setattr(index, '_persist_outcomes', original)
    result = scan(index, max_pages=100)
    assert result['objects_indexed'] == 1


def test_configuration_bounds_rejected_before_network(tmp_path, bucket):
    index = idx(tmp_path, bucket)
    for options in ({'workers': 0}, {'workers': 257}, {'page_size': 1001}, {'max_seconds': 601}, {'max_pages': 0}):
        with pytest.raises(mirror.MirrorError, match='invalid_request'):
            scan(index, **options)
    assert not bucket['listings']


@pytest.mark.parametrize('body', [
    '<ListBucketResult><IsTruncated>true</IsTruncated></ListBucketResult>',
    '<ListBucketResult><IsTruncated>false</IsTruncated><Contents><Key>qr2/level2/foreign/version/1/a.fits</Key><ETag>"id"</ETag><Size>100</Size></Contents></ListBucketResult>',
    '<ListBucketResult><IsTruncated>false</IsTruncated><Contents><Key>qr2/level2/period/version/1/a.fits</Key><Size>100</Size></Contents></ListBucketResult>',
])
def test_invalid_partition_listing_is_rejected(tmp_path, bucket, monkeypatch, body):
    catalog = importlib.import_module('irsa_catalog')
    monkeypatch.setattr(mirror, '_http', lambda *args, **kwargs: (body.encode(), {}))
    with pytest.raises(mirror.MirrorError, match='archive_mirror_listing_invalid'):
        catalog._listing(idx(tmp_path, bucket), 'qr2/level2/period/version/1/')


def test_directory_escape_is_rejected(tmp_path, bucket, monkeypatch):
    catalog = importlib.import_module('irsa_catalog')
    body = '<ListBucketResult><IsTruncated>false</IsTruncated><CommonPrefixes><Prefix>qr2/level2/../</Prefix></CommonPrefixes></ListBucketResult>'
    monkeypatch.setattr(mirror, '_http', lambda *args, **kwargs: (body.encode(), {}))
    with pytest.raises(mirror.MirrorError, match='archive_mirror_listing_invalid'):
        catalog._directories(idx(tmp_path, bucket), 'qr2/level2/', float('inf'))


def test_deadline_yields_without_false_complete_directory(tmp_path, bucket, monkeypatch):
    catalog = importlib.import_module('irsa_catalog')
    monkeypatch.setattr(catalog.time, 'monotonic', lambda: 10)
    with pytest.raises(mirror.MirrorError, match='archive_mirror_catalog_yield'):
        catalog._directories(idx(tmp_path, bucket), 'qr2/level2/', 9)
    assert not bucket['listings']


def test_small_worker_count_bounds_header_request_waves(tmp_path, bucket, monkeypatch):
    for number in range(8):
        add(bucket, name=f'object{number}')
    catalog = importlib.import_module('irsa_catalog')
    original = catalog._listing
    sizes = []
    def observe(index, prefix, token=None, page_size=1000, delimiter=False):
        if not delimiter:
            sizes.append(page_size)
        return original(index, prefix, token, page_size, delimiter)
    monkeypatch.setattr(catalog, '_listing', observe)
    scan(idx(tmp_path, bucket), workers=1, page_size=1000, max_pages=100)
    assert max(sizes) <= 4


def test_empty_release_is_complete_only_after_directory_discovery(tmp_path, bucket):
    index = idx(tmp_path, bucket)
    assert not index.status()['complete']
    result = scan(index)
    assert result['index']['complete']
    assert result['index']['objects_indexed'] == 0
    assert index.search({'position': 'CIRCLE 0 0 1'})['images'] == []


def test_catalogue_discovery_overrides_legacy_completion(tmp_path, bucket):
    index = idx(tmp_path, bucket)
    assert index.scan()['index']['complete']
    add(bucket)
    bucket['fail_prefix'].add('qr2/level2/')
    result = scan(index)
    assert result['errors']
    assert not result['index']['complete']
    with pytest.raises(mirror.MirrorError, match='archive_mirror_index_warming'):
        index.search({'position': 'CIRCLE 0 0 1'})


def test_status_uses_one_snapshot_during_final_failed_ingestion(tmp_path, bucket):
    import sqlite3
    add(bucket)
    index = idx(tmp_path, bucket)
    scan(index, max_pages=6)
    # The final page is incomplete until the concurrent writer persists
    # its failed header and advances the final checkpoint.
    index.db.execute('UPDATE mirror_catalog_partitions SET complete=0')
    index.db.commit()
    writer = sqlite3.connect(index.path)
    fired = []
    def advance(statement):
        if 'SELECT COUNT(*) FROM mirror_catalog_releases' in statement and not fired:
            fired.append(True)
            with writer:
                writer.execute('INSERT INTO mirror_retries VALUES (?,?,?,?,?,?,?)',
                               ('qr2/level2/missing.fits', 'qr2', 'identity', '{}', 0, 0, 1))
                writer.execute('UPDATE mirror_catalog_partitions SET complete=1')
    index.db.set_trace_callback(advance)
    status = index.status()
    index.db.set_trace_callback(None)
    writer.close()
    # All fields must reflect either the before or after snapshot together.
    assert fired
    assert status['complete'] == (status['listing_complete'] and status['failed_objects'] == 0)
    # The trace commits before the catalogue SELECT; under a single read
    # transaction the reader still observes the original retry-free snapshot.
    assert status['complete'] is False
    assert status['listing_complete'] is False
    assert status['failed_objects'] == 0
    assert index.status()['failed_objects'] == 1
    assert index.status()['complete'] is False
