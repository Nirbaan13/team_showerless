"""Test the deployed Apache rewrite/PHP proxy against a disposable HTTP fixture."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import socket
import subprocess
from tempfile import TemporaryDirectory
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BINARY = bytes(range(256)) * 32

class Upstream(BaseHTTPRequestHandler):
    def do_GET(self):
        body = BINARY if self.path.endswith('/binary') else (b'data: ready\n\n' if self.path.endswith('/events') else json.dumps({'path': self.path, 'body': self.rfile.read(int(self.headers.get('Content-Length', '0'))).decode()}).encode())
        self.send_response(404 if self.path.endswith('/missing') else 202 if self.command == 'POST' else 200)
        self.send_header('Content-Type', 'application/octet-stream' if self.path.endswith('/binary') else 'text/event-stream' if self.path.endswith('/events') else 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)
    do_POST = do_GET
    def log_message(self, *_):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--public', type=Path, required=True)
    args = parser.parse_args()
    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    name = f'frontend-hostinger-qa-{port}'
    try:
        with TemporaryDirectory(prefix='frontend-hostinger-qa-') as directory:
            root = Path(directory)
            shutil.copy(args.public / '.htaccess', root / '.htaccess')
            if (args.public / 'api-proxy.php').exists():
                shutil.copy(args.public / 'api-proxy.php', root / 'api-proxy.php')
            (root / 'index.html').write_text('<html>SPA homepage</html>')
            root.chmod(0o755)
            for file in root.iterdir():
                file.chmod(0o644)
            command = f"a2enmod rewrite >/dev/null && sed -i 's/Listen 80/Listen 127.0.0.1:{port}/' /etc/apache2/ports.conf && sed -i 's/:80>/:{port}>/' /etc/apache2/sites-enabled/000-default.conf && printf '<Directory /var/www/html>\nAllowOverride All\nRequire all granted\n</Directory>\n' > /etc/apache2/conf-enabled/qa.conf && apache2-foreground"
            subprocess.run(['docker', 'run', '--rm', '-d', '--network', 'host', '--name', name, '-e', f'SPACEAPPS_API_UPSTREAM=http://127.0.0.1:{upstream.server_port}', '-v', f'{root}:/var/www/html:ro', args.image, 'sh', '-c', command], check=True, stdout=subprocess.DEVNULL)
            base = f'http://127.0.0.1:{port}'
            for _ in range(50):
                try:
                    with urlopen(base, timeout=1): break
                except OSError: time.sleep(0.1)
            for path in ['/api/catalogue/candidates?q=WISE%200855', '/backend/api/downloads/test']:
                with urlopen(base + path, timeout=5) as result:
                    assert result.headers.get_content_type() == 'application/json', result.headers
                    assert json.load(result)['path'] == path
                print(f'GET {path}: JSON upstream', flush=True)
            body = b'{"download_id":"real-job"}'
            with urlopen(Request(base + '/backend/api/analyses/motion', data=body, headers={'Content-Type': 'application/json'}), timeout=5) as result:
                assert result.status == 202
                assert json.load(result)['body'].encode() == body
            for path, expected in [('/backend/api/missing', 404), ('/api-proxy.php', 404)]:
                try: urlopen(base + path, timeout=5)
                except HTTPError as error:
                    assert error.code == expected
                    assert error.headers.get_content_type() == 'application/json'
                else: raise AssertionError(f'{path} must return {expected}')
            with urlopen(base + '/backend/api/binary', timeout=5) as result:
                assert result.read() == BINARY
                assert result.headers.get_content_type() == 'application/octet-stream'
            with urlopen(base + '/backend/api/events', timeout=5) as result:
                assert result.read() == b'data: ready\n\n'
                assert result.headers.get_content_type() == 'text/event-stream'
            with urlopen(base + '/viewer-bookmark', timeout=5) as result:
                assert result.read() == b'<html>SPA homepage</html>'
            print('POST body/202, error/404, direct-file guard, binary, SSE and SPA routing pass', flush=True)
    finally:
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        upstream.shutdown()

if __name__ == '__main__':
    main()
