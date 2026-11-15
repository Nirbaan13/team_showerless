"""Exercise deployment readiness recovery using the Scala response shapes."""
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import struct
import sys
from threading import Thread
from unittest.mock import patch

import pytest


@pytest.fixture
def readiness_module():
    path = Path(__file__).with_name('verify_frontend_routes.py')
    spec = importlib.util.spec_from_file_location('frontend_route_readiness', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def route_server():
    state = {'resets_remaining': 1, 'requests': []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state['requests'].append(self.path)
            if state['resets_remaining']:
                state['resets_remaining'] -= 1
                self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                self.connection.close()
                self.close_connection = True
                return
            replies = {
                '/api/capabilities': (200, dict(revision='test-revision', pipeline={'available': True},
                    motion_models={'models': [{'model_id': 'installed'}]},
                    motion_analysis={'status': 'supported', 'endpoint': '/api/analyses/motion'})),
                '/api/analyses/models': (200, {'models': [{'model_id': 'installed'}]}),
                '/api/motion/verifications': (200, []),
                '/api/catalogue/kpis': (200, {'total_candidates': 0}),
                '/api/catalogue/candidates': (200, {'candidates': []}),
            }
            status, body = replies.get(self.path, (501, dict(code='unsupported_legacy_operation',
                retryable=False, motion_analysis_url='/api/analyses/motion')))
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_nullable_model_discovery_retries_then_verifies_routes(capsys, readiness_module):
    module = readiness_module
    capabilities = dict(revision='test-revision', pipeline={'available': True},
                        motion_models={'models': [{'model_id': 'installed'}]},
                        motion_analysis={'status': 'supported', 'endpoint': '/api/analyses/motion'},
                        legacy_motion_service={'status': 'unsupported'},
                        community_catalogue={'status': 'unsupported'})
    unsupported = dict(code='unsupported_legacy_operation', retryable=False,
                       motion_analysis_url='/api/analyses/motion')
    transient = dict(capabilities, motion_models=None,
                     motion_analysis={'status': 'unavailable', 'endpoint': '/api/analyses/motion'})
    replies = [(200, transient), (200, capabilities),
               (200, {'models': [{'model_id': 'installed'}]}),
               (200, []), (200, {'total_candidates': 0}),
               (200, {'candidates': []})] + [(501, unsupported)] * 2
    with patch.object(module, 'request', side_effect=replies) as request, \
         patch.object(module.time, 'sleep') as sleep, \
         patch.object(sys, 'argv',
                      ['verify_frontend_routes.py', '--base-url', 'http://example.invalid']):
        module.main()
    assert request.call_count == 8
    sleep.assert_called_once_with(2)
    assert '"status": "PASS"' in capsys.readouterr().out


def test_connection_reset_retries_real_http_then_verifies_all_routes(capsys, readiness_module, route_server):
    base, state = route_server
    with patch.object(readiness_module.time, 'sleep'), \
         patch.object(sys, 'argv', ['verify_frontend_routes.py', '--base-url', base]):
        readiness_module.main()
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'PASS'
    assert state['requests'] == [
        '/api/capabilities', '/api/capabilities', '/api/analyses/models',
        '/api/motion/verifications', '/api/catalogue/kpis', '/api/catalogue/candidates',
        '/api/motion/coadd/PX-000001/motion.png', '/api/motion/cutout/render',
    ]
    assert [route['http_status'] for route in result['routes']] == [200, 200, 200, 501, 501]


def test_persistent_connection_resets_fail_after_thirty_attempts(capsys, readiness_module, route_server):
    base, state = route_server
    state['resets_remaining'] = 30
    with patch.object(readiness_module.time, 'sleep'), \
         patch.object(sys, 'argv', ['verify_frontend_routes.py', '--base-url', base]), \
         pytest.raises(ConnectionResetError):
        readiness_module.main()
    assert state['requests'] == ['/api/capabilities'] * 30
    assert capsys.readouterr().out == ''
