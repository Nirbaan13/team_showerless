"""Exercise actual Nginx locations against isolated Scala/ML HTTP fixtures.

Run with a locally available frontend image and config path; no production API
receives requests and the disposable server binds only to loopback.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import subprocess
from tempfile import TemporaryDirectory
import threading
import time
from urllib.request import Request, urlopen


def fixture(name):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'upstream': name, 'path': self.path}).encode())
        do_POST = do_GET
        def log_message(self, *_):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    scala, ml = fixture('scala'), fixture('ml')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    name = f'frontend-qa-routing-{port}'
    config = args.config.read_text().replace('listen 8080;', f'listen 127.0.0.1:{port};')
    config = config.replace('host.docker.internal:8001', f'127.0.0.1:{ml.server_port}')
    config = config.replace('host.docker.internal:80', f'127.0.0.1:{scala.server_port}')
    try:
        with TemporaryDirectory(prefix='frontend-qa-routing-') as directory:
            path = Path(directory) / 'default.conf'
            path.write_text(config)
            subprocess.run(['docker', 'run', '--rm', '-d', '--name', name, '--network', 'host', '-v', f'{path}:/etc/nginx/conf.d/default.conf:ro', args.image], check=True, stdout=subprocess.DEVNULL)
            base = f'http://127.0.0.1:{port}'
            for _ in range(30):
                try:
                    with urlopen(base + '/backend/health', timeout=2):
                        break
                except OSError:
                    time.sleep(0.1)
            for method, url, expected in [
                ('GET', '/api/catalogue/candidates?q=test', 'ml'),
                ('GET', '/api/catalogue/candidates/PX-000001', 'ml'),
                ('GET', '/api/catalogue/kpis', 'ml'),
                ('POST', '/api/catalogue/candidates/PX-000001/classify', 'ml'),
                ('GET', '/api/motion/verifications', 'ml'),
                ('POST', '/api/motion/verifications', 'ml'),
                ('GET', '/api/motion/candidates', 'ml'),
                ('GET', '/api/motion/catalog?ra=1&dec=2', 'scala'),
                ('GET', '/backend/health', 'scala'),
                ('POST', '/api/catalogue/auto-submit', 'scala'),
                ('POST', '/api/catalogue/candidates/PX-000001/submissions', 'scala'),
                ('GET', '/api/motion/coadd/PX-000001/motion.png', 'scala'),
                ('GET', '/api/motion/cutout/render', 'scala'),
            ]:
                with urlopen(Request(base + url, method=method, data=b'{}' if method == 'POST' else None), timeout=3) as response:
                    actual = json.load(response)
                assert actual['upstream'] == expected, (url, expected, actual)
                print(f'{method} {url}: {expected}', flush=True)
    finally:
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        scala.shutdown()
        ml.shutdown()


if __name__ == '__main__':
    main()
