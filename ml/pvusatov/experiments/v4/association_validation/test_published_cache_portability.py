"""Recount the published numeric caches from a fresh, guarded offline copy."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
ARCHIVE_SHA256 = "928f1f8824fa8575c11087d74aa3b3901b9f5f5a1bb1d1172f89f0f873b8131c"
ARCHIVE_BYTES = 107970560


def test_published_numeric_cache_recounts_without_original_inputs(tmp_path):
    """Catch corrupt publication parts or a recount that depends on old paths."""
    published = HERE / "results/numeric-cache"
    manifest = json.loads((published / "manifest.json").read_text())
    assert manifest["archive_sha256"] == ARCHIVE_SHA256
    assert manifest["archive_bytes"] == ARCHIVE_BYTES
    assert [part["path"] for part in manifest["parts"]] == [
        f"cache.tar.part{index:03d}" for index in range(4)
    ]

    archive = tmp_path / "cache.tar"
    archive_digest = hashlib.sha256()
    with archive.open("wb") as destination:
        for part in manifest["parts"]:
            source = published / part["path"]
            assert source.stat().st_size == part["bytes"], part["path"]
            part_digest = hashlib.sha256()
            with source.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    part_digest.update(chunk)
                    archive_digest.update(chunk)
                    destination.write(chunk)
            assert part_digest.hexdigest() == part["sha256"], part["path"]
    assert archive.stat().st_size == ARCHIVE_BYTES
    assert archive_digest.hexdigest() == ARCHIVE_SHA256

    output = tmp_path / "proof"
    audit = HERE / "engineering-repair-1/independent-audit/prove_portable.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(audit),
            "--repo-root", str(REPO),
            "--cache-archive", str(archive),
            "--output-dir", str(output),
        ],
        cwd=tmp_path,
        env=dict(
            os.environ,
            OPENBLAS_NUM_THREADS="1",
            OMP_NUM_THREADS="1",
            MKL_NUM_THREADS="1",
            NUMEXPR_NUM_THREADS="1",
            PYTHONDONTWRITEBYTECODE="1",
        ),
        capture_output=True,
        text=True,
        timeout=180,
    )
    proof_path = output / "portable-proof.json"
    proof = json.loads(proof_path.read_text()) if proof_path.exists() else None
    try:
        assert completed.returncode == 0, (completed.stdout, completed.stderr)
        assert proof is not None
        recount = json.loads((output / "portable-recount.json").read_text())
        assert proof["status"] == recount["status"] == "PASS"
        assert proof["cache_archive_sha256"] == ARCHIVE_SHA256
        assert proof["cache_archive_bytes"] == ARCHIVE_BYTES
        assert proof["archive_file_members"] == manifest["file_members"] == 3156
        assert proof["child_exit_code"] == 0
        assert proof["child_original_inputs_denied"] is True
        assert recount["python_io_guard_enabled"] is True
        assert recount["identity_equality_fields"] == 1000
        assert recount["audited_candidate_rows"] == 271293
        denied = [
            "/home/usatovpavel/.codex/worktrees/spaceapps-zio-backend/"
            "ml/pvusatov/experiments/v4/association_validation/protocol.json",
            "/tmp/spaceapps-association-validation/synthetic-repair-1/run-manifest.json",
            "/etc/passwd",
        ]
        assert proof["intentional_denied_reads"] == denied
        assert recount["intentional_original_and_outside_read_probes_rejected"] == denied
        assert proof["model_execution"] is False
        assert proof["raw_pixels_read"] is False
        assert proof["scoring_or_simulation"] is False
    finally:
        if proof is not None:
            fresh = Path(proof["fresh_copy_directory"])
            assert not fresh.is_symlink(), "refusing to remove a symlink"
            assert fresh.parent.resolve() == Path(tempfile.gettempdir()).resolve()
            assert fresh.name.startswith("association-offline-proof-")
            shutil.rmtree(fresh)
