"""Unit tests for ML inference microservice & SQLite verification endpoints."""

import os
import unittest
from fastapi.testclient import TestClient

from service import app, get_db


class TestVerificationEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_check(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")

    def test_initial_verifications_seeded(self):
        resp = self.client.get("/api/motion/verifications")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()
        self.assertGreaterEqual(len(items), 8)
        candidate_ids = {item["candidateId"] for item in items}
        self.assertIn("3I/ATLAS", candidate_ids)
        self.assertIn("(4) Vesta (D6 BLOOM)", candidate_ids)

    def test_create_and_upvote_verification(self):
        payload = {
            "candidateId": "3I/ATLAS",
            "author": "Test Reviewer",
            "role": "Researcher",
            "message": "Astrometric track confirmed across all 4 epochs.",
            "vote": "confirm_motion",
            "upvotes": 1,
            "setting": {
                "ra": 166.79,
                "dec": 5.29,
                "candidateId": "3I/ATLAS",
                "selectedArray": 6,
            },
        }
        create_resp = self.client.post("/api/motion/verifications", json=payload)
        self.assertEqual(create_resp.status_code, 200)
        created = create_resp.json()
        self.assertIn("id", created)
        self.assertEqual(created["author"], "Test Reviewer")

        # Upvote
        upvote_resp = self.client.post(f"/api/motion/verifications/{created['id']}/upvote")
        self.assertEqual(upvote_resp.status_code, 200)
        upvoted = upvote_resp.json()
        self.assertEqual(upvoted["upvotes"], 2)

    def test_filter_verifications_by_candidate(self):
        resp = self.client.get("/api/motion/verifications?candidate_id=cand-wise-0855-01")
        self.assertEqual(resp.status_code, 200)
        items = resp.json()
        self.assertGreaterEqual(len(items), 1)
        for it in items:
            self.assertEqual(it["candidateId"], "cand-wise-0855-01")

    def test_candidate_registration(self):
        payload = {
            "id": "cand-gaia-pm-test",
            "ra": 269.452,
            "dec": 4.693,
            "classification": "moving_object",
            "confidence": "high",
            "notes": "Proper motion validation test",
        }
        post_resp = self.client.post("/api/motion/candidates", json=payload)
        self.assertEqual(post_resp.status_code, 200)

        get_resp = self.client.get("/api/motion/candidates")
        self.assertEqual(get_resp.status_code, 200)
        cands = get_resp.json()
        cand_ids = [c["id"] for c in cands]
        self.assertIn("cand-gaia-pm-test", cand_ids)


if __name__ == "__main__":
    unittest.main()
