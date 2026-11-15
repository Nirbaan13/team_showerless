"""Unit checks for explicit real-only behavior; no app or HTTP server is started."""
import asyncio
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

# Import-time initialization must never touch the workspace's user databases.
with TemporaryDirectory() as directory, patch.dict(os.environ, {
    "PLANETX_DB_PATH": str(Path(directory) / "catalogue.sqlite"),
    "VERIFICATIONS_DB_PATH": str(Path(directory) / "verification.sqlite"),
}):
    import catalogue_db
    import service


class TestRealOnly(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.environment = patch.dict(os.environ, {
            "DEMO_REAL_ONLY": "1", "PLANETX_DB_PATH": str(root / "catalogue.sqlite"),
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.database = patch.object(service, "DB_PATH", root / "verification.sqlite")
        self.database.start()
        self.addCleanup(self.database.stop)

    def initialize(self):
        service.init_db()
        catalogue_db.init_db()

    def catalogue_count(self):
        with catalogue_db.get_connection() as connection:
            return connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]

    def test_fresh_strict_databases_have_no_fictional_seed_records(self):
        self.initialize()
        self.assertEqual(service.get_verifications(), [])
        self.assertEqual(service.get_candidates()["candidates"], [])
        connection = service.get_db()
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM candidates").fetchone()[0], 0)
        finally:
            connection.close()
        self.assertEqual(self.catalogue_count(), 0)
        candidate = catalogue_db.create_candidate(name="User record", ra=1, dec=2, candidate_type="unclassified")
        self.assertIsNone(candidate["snr"])
        self.assertEqual(candidate["epoch_count"], 0)
        self.assertEqual(candidate["validation_checks"], [])
        self.assertEqual(candidate["fixed_stack_url"], "")
        self.assertEqual(candidate["motion_stack_url"], "")

    def test_missing_api_epoch_evidence_stays_absent_and_supplied_measurements_survive(self):
        self.initialize()
        unknown = service.create_candidate_entry(service.CreateCandidateRequest(name="No epoch evidence", ra=1, dec=2))
        self.assertEqual(unknown["epoch_count"], 0)
        measured = service.create_candidate_entry(service.CreateCandidateRequest(
            name="Measured record", ra=3, dec=4, epoch_count=4, snr=12.3,
            speed_arcsec_hr=1.5, fit_rms_px=0.2,
            fixed_stack_url="/published/fixed.png", motion_stack_url="/published/motion.png",
        ))
        self.assertEqual(measured["epoch_count"], 4)
        self.assertEqual(measured["snr"], 12.3)
        self.assertEqual(measured["fixed_stack_url"], "/published/fixed.png")
        self.assertEqual(measured["motion_stack_url"], "/published/motion.png")
        self.initialize()
        self.assertEqual(self.catalogue_count(), 2)

    def test_user_comments_persist_without_creating_placeholder_catalogue_measurements(self):
        self.initialize()
        note = service.post_verification(service.VerificationPayload(
            id="real-user-note", candidateId="user-target", message="Needs another epoch",
            setting={"ra": 1, "dec": 2, "candidateName": "User target"},
        ))
        self.assertEqual(note["message"], "Needs another epoch")
        self.assertEqual(self.catalogue_count(), 0)
        self.initialize()
        self.assertEqual([item["id"] for item in service.get_verifications()], ["real-user-note"])
        self.assertEqual(self.catalogue_count(), 0)

    def test_disabled_flag_preserves_ordinary_seeds_and_defaults(self):
        with patch.dict(os.environ, {"DEMO_REAL_ONLY": "0"}):
            self.initialize()
            self.assertGreater(len(service.get_verifications()), 0)
            self.assertGreater(self.catalogue_count(), 0)
            candidate = catalogue_db.create_candidate(name="Ordinary record", ra=1, dec=2)
            self.assertEqual(candidate["epoch_count"], 3)
            self.assertTrue(candidate["validation_checks"])
            self.assertIn("/api/motion/coadd/", candidate["fixed_stack_url"])

    def test_strict_guard_rejects_legacy_synthetic_products_without_running_handlers(self):
        guard = getattr(service, "real_only_products", None)
        self.assertTrue(callable(guard), "The explicit real-only product guard is missing")
        for path in ["/catalog", "/api/motion/catalog", "/api/motion/cutout/render", "/api/motion/spectrum",
                     "/api/motion/coadd/user-target/motion.png", "/api/catalogue/auto-submit", "/api/motion/catalogue/auto-submit"]:
            with self.subTest(path=path):
                following = AsyncMock()
                response = asyncio.run(guard(SimpleNamespace(url=SimpleNamespace(path=path)), following))
                self.assertEqual(response.status_code, 501)
                following.assert_not_awaited()

    def test_guard_keeps_genuine_handlers_and_disabled_mode_unchanged(self):
        guard = getattr(service, "real_only_products", None)
        self.assertTrue(callable(guard), "The explicit real-only product guard is missing")
        for flag, path in [("1", "/health"), ("1", "/api/motion/search"), ("1", "/api/catalogue/candidates"),
                           ("0", "/api/motion/coadd/user-target/motion.png")]:
            with self.subTest(flag=flag, path=path), patch.dict(os.environ, {"DEMO_REAL_ONLY": flag}):
                sentinel = object()
                following = AsyncMock(return_value=sentinel)
                request = SimpleNamespace(url=SimpleNamespace(path=path))
                self.assertIs(asyncio.run(guard(request, following)), sentinel)
                following.assert_awaited_once_with(request)


if __name__ == "__main__":
    unittest.main()
