"""Real-only mode rejects synthetic products and starts with empty social/catalogue data."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import catalogue_db
import service


class TestRealOnly(unittest.TestCase):
    def test_synthetic_products_are_unavailable_but_health_remains_real(self):
        with patch.dict(os.environ, {"DEMO_REAL_ONLY": "1"}):
            client = TestClient(service.app)
            for path in ["/api/motion/cutout/render?ra=1&dec=2", "/api/motion/spectrum?ra=1&dec=2", "/api/motion/coadd/anything/motion.png", "/catalog?ra=1&dec=2"]:
                with self.subTest(path=path):
                    self.assertEqual(client.get(path).status_code, 501)
            self.assertEqual(client.get('/health').status_code, 200)

    def test_new_real_only_databases_never_seed_discussions_or_candidates(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"DEMO_REAL_ONLY": "1", "PLANETX_DB_PATH": str(Path(directory) / 'catalogue.sqlite')}), patch.object(service, 'DB_PATH', Path(directory) / 'verification.sqlite'):
            service.init_db()
            catalogue_db.init_db()
            self.assertEqual(service.get_verifications(), [])
            with catalogue_db.get_connection() as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM candidates').fetchone()[0], 0)
            candidate = catalogue_db.create_candidate(name='User record', ra=1, dec=2, candidate_type='unclassified')
            self.assertIsNone(candidate['snr'])
            self.assertEqual(candidate['epoch_count'], 0)
            self.assertEqual(candidate['validation_checks'], [])
            self.assertEqual(candidate['fixed_stack_url'], '')
            self.assertEqual(candidate['motion_stack_url'], '')
            from_api = service.create_candidate_entry(service.CreateCandidateRequest(name='Incomplete API record', ra=1, dec=2))
            self.assertEqual(from_api['epoch_count'], 0)
            measured = service.create_candidate_entry(service.CreateCandidateRequest(name='Reported epochs', ra=1, dec=2, epoch_count=4))
            self.assertEqual(measured['epoch_count'], 4)


if __name__ == '__main__':
    unittest.main()
