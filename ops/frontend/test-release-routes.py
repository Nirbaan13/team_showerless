"""Contract tests for separately deployed native processing and registry APIs."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import threading
import unittest

path = Path(__file__).resolve().parents[2] / 'ml/pvusatov/tools/ml_image_scope/verify_frontend_routes.py'
spec = importlib.util.spec_from_file_location('live_routes', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Routes(unittest.TestCase):
    def setUp(self):
        self.registry_status = 200
        self.image_status = 501
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                status = 200
                if self.path == '/api/capabilities':
                    body = {'revision': 'fixture', 'pipeline': {'available': True}, 'motion_models': {'models': [{}]}, 'motion_analysis': {'status': 'supported', 'endpoint': '/api/analyses/motion'}, 'legacy_motion_service': {'status': 'unsupported'}, 'community_catalogue': {'status': 'unsupported'}}
                elif self.path == '/api/analyses/models': body = {'models': [{}]}
                elif self.path == '/api/motion/verifications': status, body = owner.registry_status, []
                elif self.path == '/api/catalogue/kpis': status, body = owner.registry_status, {'total_candidates': 0}
                elif self.path == '/api/catalogue/candidates': status, body = owner.registry_status, {'candidates': [], 'total': 0}
                else: status, body = owner.image_status, {'code': 'unsupported_legacy_operation', 'retryable': False, 'motion_analysis_url': '/api/analyses/motion'}
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())
            def log_message(self, *_): pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
    def test_separate_registry_does_not_inherit_native_unsupported_status(self):
        self.assertEqual(module.probe(self.base)['status'], 'PASS')
    def test_registry_outage_fails_release(self):
        self.registry_status = 501
        with self.assertRaises(AssertionError): module.probe(self.base)
    def test_legacy_generated_image_is_still_rejected(self):
        self.image_status = 200
        with self.assertRaises(AssertionError): module.probe(self.base)

if __name__ == '__main__': unittest.main()
