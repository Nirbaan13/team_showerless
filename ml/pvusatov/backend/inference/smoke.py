"""Exercise the packaged CLI and frozen model on real archived exposures."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="spherex-inference-smoke-") as temporary:
        folder = Path(temporary)
        request = folder / "request.json"
        request.write_text(json.dumps({
            "schema_version": 1,
            "analysis_id": "packaged-model-smoke",
            "source": {"kind": "preset", "preset_id": "comet-d6"},
            "options": {},
        }))
        subprocess.run(
            [sys.executable, "-m", "ml_inference", "--request", str(request),
             "--output", str(folder / "output")],
            env=dict(os.environ, PYTHONPATH=str(root)), check=True, timeout=120,
        )
        result = json.loads((folder / "output" / "result.json").read_text())
        assert not result.get("error"), result.get("error")
        assert len(result["frames"]) == 4, "The real fixture has four independent exposures"
        assert result["candidates"], "The detector must return computed tracks"
        digest = hashlib.sha256((root / "models" / "ranker.onnx").read_bytes()).hexdigest()
        assert result["model"]["sha256"] == digest, "Inference did not identify the packaged model"
        for resource in result["resources"]:
            name = resource["name"]
            assert Path(name).name == name, "Resource escaped the output directory"
            assert (folder / "output" / name).is_file(), name
        assert any(candidate.get("score") is not None for candidate in result["candidates"])
        print("Packaged real-data inference and frozen-model digest verified:", digest)


if __name__ == "__main__":
    main()
