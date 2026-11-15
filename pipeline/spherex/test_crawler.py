"""Unit tests for SPHEREx autonomous crawler and ingestion state."""

import json
import tempfile
import unittest
from pathlib import Path

from pipeline.spherex.crawler import IngestionState, register_discovered_candidate


class TestCrawler(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.tmp_dir.name) / "test_checkpoint.json"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_state_initialization_and_saving(self):
        state = IngestionState(self.state_file)
        self.assertFalse(state.is_processed("exp-001"))

        state.mark_processed(["exp-001", "exp-002"])
        self.assertTrue(state.is_processed("exp-001"))
        self.assertTrue(state.is_processed("exp-002"))
        self.assertFalse(state.is_processed("exp-003"))

        # Verify persistent disk file was written
        self.assertTrue(self.state_file.exists())
        with open(self.state_file, "r") as f:
            data = json.load(f)
        self.assertIn("exp-001", data["processed_exposures"])
        self.assertIn("exp-002", data["processed_exposures"])
        self.assertIsNotNone(data["last_crawl_utc"])

    def test_candidate_registration(self):
        cand = {
            "id": "cand-crawler-test-unit",
            "ra": 166.79,
            "dec": 5.29,
            "classification": "moving_object",
            "confidence": "high",
            "notes": "Test candidate registered from crawler test",
            "metadata": {"speed_arcsec_hr": 120.5},
        }
        success = register_discovered_candidate(cand)
        self.assertTrue(success)


if __name__ == "__main__":
    unittest.main()
