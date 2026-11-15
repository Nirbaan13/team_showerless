"""Autonomous SPHEREx NASA/IRSA Crawler & Ingestion Worker.

Monitors IRSA SIA/TAP services for newly published SPHEREx exposures,
runs candidate trajectory detection on new multi-epoch clusters, and
registers discovered moving-object candidates directly into the centralized database.
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Crawler] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("spherex_crawler")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "science" / "motion"))
sys.path.insert(0, str(ROOT_DIR / "ml"))

try:
    from science.motion.live import discover, search_motion, COLLECTIONS, ARCHIVE_HOST, SearchError
except ImportError as err:
    logger.warning("Could not import live motion modules: %s", err)
    discover = None
    search_motion = None

# Monitored science targets and benchmark sky tiles
DEFAULT_MONITORED_TARGETS = [
    {"name": "3I/ATLAS Benchmark Field", "ra": 166.790, "dec": 5.290, "detector": 6, "size_arcmin": 15},
    {"name": "(4) Vesta Asteroid Track Field", "ra": 223.024, "dec": -11.992, "detector": 6, "size_arcmin": 15},
    {"name": "Barnard's Star High-Proper-Motion Field", "ra": 269.452, "dec": 4.693, "detector": 2, "size_arcmin": 15},
    {"name": "WISE 0855-0714 Sub-Brown Dwarf Field", "ra": 133.795, "dec": -7.245, "detector": 5, "size_arcmin": 15},
]


class IngestionState:
    """Tracks processed exposure IDs and timestamp checkpoints."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning("Failed to load state file (%s), reinitializing: %s", self.state_file, e)
        return {
            "last_crawl_utc": None,
            "processed_exposures": [],
            "candidates_discovered": 0,
            "crawl_history": [],
        }

    def save(self) -> None:
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save state file: %s", e)

    def is_processed(self, exposure_id: str) -> bool:
        return exposure_id in set(self.data.get("processed_exposures", []))

    def mark_processed(self, exposure_ids: List[str]) -> None:
        known = set(self.data.get("processed_exposures", []))
        known.update(exposure_ids)
        # Keep a bounded set of the latest 10,000 exposure IDs
        self.data["processed_exposures"] = list(known)[-10000:]
        self.data["last_crawl_utc"] = datetime.now(timezone.utc).isoformat()
        self.save()


def get_db_connection() -> Optional[sqlite3.Connection]:
    db_path = Path(os.getenv("VERIFICATIONS_DB_PATH", str(ROOT_DIR / "data" / "verifications.sqlite")))
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error("Failed to connect to SQLite candidates database: %s", e)
        return None


def register_discovered_candidate(candidate_data: Dict[str, Any]) -> bool:
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn:
            meta_json = json.dumps(candidate_data.get("metadata", {}))
            conn.execute("""
                INSERT INTO candidates (id, ra, dec, classification, confidence, notes, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    ra = excluded.ra,
                    dec = excluded.dec,
                    classification = excluded.classification,
                    confidence = excluded.confidence,
                    notes = excluded.notes,
                    metadata_json = excluded.metadata_json
            """, (
                candidate_data["id"],
                candidate_data["ra"],
                candidate_data["dec"],
                candidate_data.get("classification", "moving_object"),
                candidate_data.get("confidence", "high"),
                candidate_data.get("notes", "Auto-discovered by SPHEREx background crawler"),
                meta_json,
            ))
        return True
    except Exception as e:
        logger.error("Database upsert failed for candidate %s: %s", candidate_data.get("id"), e)
        return False
    finally:
        conn.close()


def crawl_target(
    target: Dict[str, Any],
    days_back: int,
    state: IngestionState,
    dry_run: bool = False,
) -> Tuple[int, int]:
    """
    Crawls a target field for new exposures and runs motion detection.
    Returns (new_exposures_count, new_candidates_count).
    """
    if not discover or not search_motion:
        logger.warning("Motion analysis module not available; skipping target %s", target["name"])
        return 0, 0

    end_d = datetime.now(timezone.utc).date()
    start_d = end_d - timedelta(days=min(6, days_back))
    ra, dec = target["ra"], target["dec"]
    det = target.get("detector", 6)
    size_arcmin = target.get("size_arcmin", 15)

    logger.info("Scanning IRSA for %s (RA=%.3f, Dec=%.3f, Det=D%d, Range: %s to %s)...",
                target["name"], ra, dec, det, start_d, end_d)

    # Convert dates to MJD
    mjd_start = (start_d - date(1858, 11, 17)).days
    mjd_stop = (end_d - date(1858, 11, 17)).days + 1

    # Check for new exposures
    retries = 3
    exposures = []
    for attempt in range(1, retries + 1):
        try:
            exposures = discover(ra, dec, det, mjd_start, mjd_stop)
            break
        except Exception as e:
            logger.warning("Attempt %d: Query failed for %s: %s", attempt, target["name"], e)
            if attempt < retries:
                time.sleep(2 ** attempt)
            else:
                logger.error("IRSA query exhausted retries for %s. Continuing.", target["name"])
                return 0, 0

    if not exposures:
        logger.info("No exposures found for %s in specified date range.", target["name"])
        return 0, 0

    exp_ids = [exp.id for exp in exposures]
    new_ids = [eid for eid in exp_ids if not state.is_processed(eid)]

    logger.info("Found %d total exposures (%d newly released) across collections %s",
                len(exposures), len(new_ids), COLLECTIONS)

    if not new_ids:
        logger.info("All exposures for %s have already been ingested.", target["name"])
        return 0, 0

    if dry_run:
        logger.info("[Dry Run] Would process %d new exposures for %s", len(new_ids), target["name"])
        return len(new_ids), 0

    # Run motion search pipeline on new observation cluster
    logger.info("Executing multi-epoch motion search pipeline on %s...", target["name"])
    candidates_found = 0
    try:
        review_result = search_motion(ra, dec, det, start_d, end_d, size_arcmin, retain_outliers=True)
        tracks = review_result.get("tracks", [])
        logger.info("Motion detection complete for %s. Recovered %d moving tracks.", target["name"], len(tracks))

        for rank, track in enumerate(tracks, start=1):
            cand_id = f"cand-{target['name'].replace(' ', '_').lower()}-track-{rank}"
            cand_entry = {
                "id": cand_id,
                "ra": ra,
                "dec": dec,
                "classification": "moving_object",
                "confidence": "high" if rank <= 3 else "medium",
                "notes": (
                    f"Automated SPHEREx ingest: track #{rank} detected across "
                    f"{len(review_result.get('epochs', []))} epochs. Sky speed: "
                    f"{track.get('speed_arcsec_hr', 0):.1f} arcsec/hr, Fit RMS: "
                    f"{track.get('fit_rms_px', 0):.2f} px."
                ),
                "metadata": {
                    "target_name": target["name"],
                    "detector": det,
                    "pipeline_version": "2.0-loo",
                    "speed_arcsec_hr": track.get("speed_arcsec_hr"),
                    "fit_rms_px": track.get("fit_rms_px"),
                    "motion_stack": track.get("motion_stack"),
                    "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
                },
            }
            if register_discovered_candidate(cand_entry):
                candidates_found += 1
                logger.info("Registered new candidate: %s (#%d)", cand_id, rank)

        state.mark_processed(exp_ids)
        return len(new_ids), candidates_found

    except SearchError as se:
        logger.warning("Pipeline search error for %s (Status %d): %s", target["name"], se.status, se)
        return len(new_ids), 0
    except Exception as exc:
        logger.error("Unexpected error processing %s: %s", target["name"], exc, exc_info=True)
        return len(new_ids), 0


def run_crawler_cycle(
    targets: List[Dict[str, Any]],
    state: IngestionState,
    days_back: int = 6,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Runs a complete crawl cycle across all configured target fields."""
    logger.info("=== Starting SPHEREx NASA/IRSA Ingestion Crawl Cycle ===")
    cycle_start = time.time()
    total_new_exposures = 0
    total_new_candidates = 0

    for target in targets:
        new_exp, new_cand = crawl_target(target, days_back, state, dry_run=dry_run)
        total_new_exposures += new_exp
        total_new_candidates += new_cand

    elapsed = time.time() - cycle_start
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "new_exposures_found": total_new_exposures,
        "new_candidates_registered": total_new_candidates,
        "monitored_targets_count": len(targets),
    }

    state.data.setdefault("crawl_history", []).append(summary)
    state.data["crawl_history"] = state.data["crawl_history"][-50:]  # Keep latest 50 runs
    state.save()

    logger.info("=== Crawl Cycle Complete in %.2fs. New Exposures: %d, Candidates Registered: %d ===",
                elapsed, total_new_exposures, total_new_candidates)
    return summary


def main():
    parser = argparse.ArgumentParser(description="SPHEREx Automated NASA/IRSA Ingestion Crawler")
    parser.add_argument("--once", action="store_true", help="Execute one ingestion cycle and exit (for cron/CI)")
    parser.add_argument("--interval-minutes", type=int, default=60, help="Minutes between crawl cycles (default: 60)")
    parser.add_argument("--days-back", type=int, default=6, help="Days to look back on each query (max 6)")
    parser.add_argument("--dry-run", action="store_true", help="Query IRSA without downloading/saving")
    parser.add_argument("--state-file", type=str, default=str(ROOT_DIR / "data" / "crawler_checkpoint.json"))
    parser.add_argument("--targets-file", type=str, default=None, help="Path to custom targets JSON file")

    args = parser.parse_args()

    state = IngestionState(Path(args.state_file))

    targets = DEFAULT_MONITORED_TARGETS
    if args.targets_file and Path(args.targets_file).exists():
        try:
            with open(args.targets_file, "r", encoding="utf-8") as f:
                targets = json.load(f)
            logger.info("Loaded %d custom targets from %s", len(targets), args.targets_file)
        except Exception as e:
            logger.warning("Could not read targets file (%s), using defaults: %s", args.targets_file, e)

    if args.once:
        summary = run_crawler_cycle(targets, state, days_back=args.days_back, dry_run=args.dry_run)
        print(json.dumps(summary, indent=2))
        sys.exit(0)

    logger.info("Starting crawler daemon (running every %d minutes)...", args.interval_minutes)
    while True:
        try:
            run_crawler_cycle(targets, state, days_back=args.days_back, dry_run=args.dry_run)
        except KeyboardInterrupt:
            logger.info("Crawler stopped by user.")
            break
        except Exception as e:
            logger.error("Unhandled error in crawl loop: %s", e, exc_info=True)

        logger.info("Sleeping for %d minutes until next check...", args.interval_minutes)
        time.sleep(args.interval_minutes * 60)


if __name__ == "__main__":
    main()
