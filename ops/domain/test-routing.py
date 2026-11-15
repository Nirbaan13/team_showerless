#!/usr/bin/env python3
"""Exercise the real Caddy config with isolated HTTP fixtures and private TLS."""
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = 'spherexblink.tech'
release = threading.Event()


def fixture(name, port):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == '/api/events':
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                self.wfile.write(b'data: first\n\n')
                self.wfile.flush()
                release.wait(10)
                self.close_connection = True
                return
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            payload = json.dumps({'upstream': name, 'method': self.command,
                                  'path': self.path, 'body': body.decode()}).encode()
            self.send_response(503 if self.path == '/api/error' else 200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_POST = do_GET

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class ResolvedHTTPS(http.client.HTTPSConnection):
    def connect(self):
        self.sock = self._context.wrap_socket(
            socket.create_connection(('127.0.0.1', self.port), self.timeout),
            server_hostname=self.host)


def main():
    servers = [fixture('backend', 18082), fixture('frontend', 18083)]
    try:
        with tempfile.TemporaryDirectory(prefix='spaceapps-domain-routing-') as tmp:
            root = Path(tmp)
            env = dict(os.environ, SPACEAPPS_HTTP_PORT='18081', SPACEAPPS_HTTPS_PORT='18443',
                       SPACEAPPS_CADDY_ADMIN='off', SPACEAPPS_TLS_POLICY='tls internal',
                       SPACEAPPS_API_UPSTREAM='127.0.0.1:18082',
                       SPACEAPPS_FRONTEND_UPSTREAM='127.0.0.1:18083',
                       XDG_DATA_HOME=str(root/'data'), XDG_CONFIG_HOME=str(root/'config'))
            with (root/'caddy.log').open('w+') as log:
                process = subprocess.Popen(['caddy', 'run', '--config', str(ROOT/'ops/domain/Caddyfile'),
                                            '--adapter', 'caddyfile'], env=env, stdout=log, stderr=log)
                try:
                    certificate = root/'data/caddy/pki/authorities/local/root.crt'
                    deadline = time.monotonic()+15
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            log.seek(0)
                            raise AssertionError(log.read())
                        try:
                            if certificate.exists():
                                probe_context = ssl.create_default_context(cafile=str(certificate))
                                with probe_context.wrap_socket(socket.create_connection(('127.0.0.1', 18443), .2), server_hostname=DOMAIN):
                                    break
                        except OSError:
                            pass
                        time.sleep(.05)
                    context = ssl.create_default_context(cafile=str(certificate))

                    def request(path, method='GET', body=None, host=DOMAIN):
                        c = ResolvedHTTPS(host, 18443, context=context, timeout=2)
                        try:
                            c.request(method, path, body=body)
                            response = c.getresponse()
                            return response.status, response.getheader('Content-Type'), json.loads(response.read())
                        finally:
                            c.close()

                    for path, expected in [('/', 'frontend'), ('/assets/test.js', 'frontend'),
                                           ('/frontend-version.json', 'frontend'), ('/api/motion/search', 'frontend'),
                                           ('/api/catalogue/items', 'frontend'), ('/api/observations-search?q=one', 'backend'),
                                           ('/api/observations-download/chunks/123', 'backend'), ('/docs', 'backend'),
                                           ('/openapi.json', 'backend'), ('/health', 'backend')]:
                        status, media, data = request(path)
                        assert (status, media, data['upstream'], data['path']) == (200, 'application/json', expected, path), (path, data)
                    status, _, data = request('/backend/api/observations-download?selected=one', 'POST', '{"observation_ids":["one"]}')
                    assert status == 200 and data == {'upstream': 'backend', 'method': 'POST',
                        'path': '/api/observations-download?selected=one', 'body': '{"observation_ids":["one"]}'}, data
                    status, media, data = request('/backend/api/error')
                    assert status == 503 and media == 'application/json' and data['upstream'] == 'backend'
                    assert request('/health', host='www.'+DOMAIN)[2]['upstream'] == 'backend'
                    direct = http.client.HTTPConnection('127.0.0.1', 18081, timeout=2)
                    direct.request('GET', '/health')
                    assert json.loads(direct.getresponse().read())['upstream'] == 'backend'
                    direct.close()
                    redirect = http.client.HTTPConnection('127.0.0.1', 18081, timeout=2)
                    redirect.request('GET', '/viewer?selected=one', headers={'Host': DOMAIN})
                    response = redirect.getresponse()
                    assert response.status == 308 and response.getheader('Location') == 'https://'+DOMAIN+'/viewer?selected=one', (response.status, response.getheaders())
                    response.read()
                    redirect.close()
                    stream = ResolvedHTTPS(DOMAIN, 18443, context=context, timeout=2)
                    stream.request('GET', '/backend/api/events')
                    response = stream.getresponse()
                    assert response.getheader('Content-Type') == 'text/event-stream'
                    assert response.readline() == b'data: first\n', 'SSE waited for the response to finish'
                    release.set()
                    stream.close()
                    print('PASS: TLS/SNI, www, frontend, prefix/query/body, API errors, legacy health, HTTPS redirect and live SSE')
                finally:
                    release.set()
                    process.terminate()
                    try:
                        process.wait(5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()
