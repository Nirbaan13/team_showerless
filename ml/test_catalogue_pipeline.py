"""Comprehensive automated tests for PlanetX Persistent Candidate Catalogue & External Submission Pipeline."""

import json
import sqlite3
import unittest
from pathlib import Path

import catalogue_db


class TestCataloguePipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        catalogue_db.init_db()

    def test_01_seed_benchmark_candidates(self):
        """Verifies that all 4 NASA benchmark candidates are seeded with accurate parameters."""
        cands, total = catalogue_db.list_candidates()
        self.assertGreaterEqual(total, 4)

        cand_map = {c["id"]: c for c in cands}
        self.assertIn("PX-000001", cand_map)
        self.assertIn("PX-000002", cand_map)
        self.assertIn("PX-000003", cand_map)
        self.assertIn("PX-000004", cand_map)

        # 3I/ATLAS verification
        atlas = cand_map["PX-000001"]
        self.assertEqual(atlas["name"], "3I/ATLAS")
        self.assertEqual(atlas["status"], "community_verified")
        self.assertAlmostEqual(atlas["speed_arcsec_hr"], 175.7, places=1)
        self.assertAlmostEqual(atlas["fit_rms_px"], 0.22, places=2)

        # Vesta verification
        vesta = cand_map["PX-000002"]
        self.assertEqual(vesta["name"], "(4) Vesta")
        self.assertEqual(vesta["status"], "community_verified")
        self.assertAlmostEqual(vesta["speed_arcsec_hr"], 42.1, places=1)

        # Barnard's Star verification
        barnard = cand_map["PX-000003"]
        self.assertIn("Barnard", barnard["name"])
        self.assertEqual(barnard["status"], "community_verified")

        # WISE 0855-0714 verification
        wise = cand_map["PX-000004"]
        self.assertEqual(wise["name"], "WISE 0855-0714")
        self.assertEqual(wise["status"], "under_review")

    def test_02_kpi_counters(self):
        """Verifies that live KPI counters reflect database state."""
        kpis = catalogue_db.get_kpis()
        self.assertGreaterEqual(kpis["total_candidates"], 4)
        self.assertGreaterEqual(kpis["community_verified"], 3)
        self.assertGreaterEqual(kpis["under_review"], 1)
        self.assertGreaterEqual(kpis["passed_validation"], 3)
        self.assertGreaterEqual(kpis["submitted_external"], 1)

    def test_03_create_candidate_auto_increment(self):
        """Verifies dynamic candidate creation assigns sequential PX-XXXXXX IDs."""
        new_cand = catalogue_db.create_candidate(
            name="2026-NEO-TEST",
            ra=180.5000,
            dec=-15.2000,
            candidate_type="moving_object",
            snr=15.2,
            speed_arcsec_hr=55.4,
            fit_rms_px=0.21,
            spectral_summary={"features": ["Silicate"], "detector_arrays": ["D2"]},
            author_id="researcher-test-01",
            author_name="Dr. Test",
        )
        self.assertTrue(new_cand["id"].startswith("PX-"))
        self.assertEqual(new_cand["name"], "2026-NEO-TEST")
        self.assertEqual(new_cand["status"], "under_review")

        # Check automated validation checks created
        self.assertGreaterEqual(len(new_cand["validation_checks"]), 3)

    def test_04_consensus_engine_rules(self):
        """Verifies voting rules, ballot-stuffing prevention, and consensus transitions."""
        test_cand = catalogue_db.create_candidate(
            name="Consensus Test Object",
            ra=200.0,
            dec=10.0,
            candidate_type="moving_object",
            snr=12.0,
            speed_arcsec_hr=25.0,
            fit_rms_px=0.18,
            author_id="author-lead",
            author_name="Lead Author",
        )
        cid = test_cand["id"]

        # Vote 1: Cast vote by author
        catalogue_db.add_classification(
            candidate_id=cid,
            user_id="author-lead",
            user_name="Lead Author",
            user_role="Volunteer",
            vote="likely_real",
        )

        # Attempt duplicate vote by same user -> should raise PermissionError
        with self.assertRaises(PermissionError):
            catalogue_db.add_classification(
                candidate_id=cid,
                user_id="author-lead",
                user_name="Lead Author",
                user_role="Volunteer",
                vote="likely_real",
            )

        # Attempt duplicate vote by same fingerprint -> should raise PermissionError
        with self.assertRaises(PermissionError):
            catalogue_db.add_classification(
                candidate_id=cid,
                user_id="another-user",
                user_name="Another User",
                user_role="Volunteer",
                vote="likely_real",
                fingerprint_hash="fp-author-lead",
            )

        # Add 2 more votes (total 3 independent votes) -> Level 1 Under Review
        for i in range(1, 3):
            catalogue_db.add_classification(
                candidate_id=cid,
                user_id=f"reviewer-{i}",
                user_name=f"Reviewer {i}",
                user_role="Volunteer",
                vote="likely_real",
            )
        cand_detail = catalogue_db.get_candidate_by_id(cid)
        self.assertEqual(cand_detail["status"], "under_review")
        self.assertTrue(cand_detail["consensus"]["level1_qualified"])
        self.assertFalse(cand_detail["consensus"]["level2_qualified"])

        # Add 7 more votes (total 10 independent votes) -> Level 2 Community Verified
        for i in range(3, 10):
            catalogue_db.add_classification(
                candidate_id=cid,
                user_id=f"reviewer-{i}",
                user_name=f"Reviewer {i}",
                user_role="Volunteer",
                vote="likely_real",
            )
        cand_detail = catalogue_db.get_candidate_by_id(cid)
        self.assertEqual(cand_detail["status"], "community_verified")
        self.assertTrue(cand_detail["consensus"]["level2_qualified"])

    def test_05_external_submission_recording(self):
        """Verifies external submission recording updates status and persists response logs."""
        cands, _ = catalogue_db.list_candidates()
        cid = cands[0]["id"]
        ades_xml = f"<optical><trkSub>{cid}</trkSub></optical>"

        res = catalogue_db.record_external_submission(
            candidate_id=cid,
            destination="MPC",
            status="submitted",
            external_reference_id=f"MPC-NEOCP-{cid}",
            payload_text=ades_xml,
            response_log="Astrometric observation received and catalogued by MPC desk.",
        )
        self.assertEqual(res["status"], "submitted")
        self.assertEqual(res["destination"], "MPC")

        # Verify candidate record updated
        cand = catalogue_db.get_candidate_by_id(cid)
        self.assertEqual(cand["status"], "submitted_external")
        self.assertTrue(any(s["destination"] == "MPC" for s in cand["external_submissions"]))


if __name__ == "__main__":
    unittest.main()
