"""Check the deployed HTTP contract without posting candidates or discussions.

By default, start a real local server with disposable SQLite databases under /tmp.
Inside the image: python /app/smoke_deployment.py
For an existing service: python ml/smoke_deployment.py --base-url http://localhost:8001
Add --check-runtime when running against an existing server from inside its image.
"""

import argparse
from contextlib import contextmanager
import importlib
import json
import math
import os
from pathlib import Path
import random
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from urllib.request import Request, urlopen


def request(base_url, path, payload=None, timeout=15):
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(base_url.rstrip("/") + path, data=data,
                  headers={"Content-Type": "application/json"} if data else {})
    with urlopen(req, timeout=timeout) as response:
        body = response.read()
        assert response.status == 200, (path, response.status)
        if response.headers.get_content_type() == "image/png":
            assert body.startswith(b"\x89PNG\r\n\x1a\n"), "Invalid coadd PNG"
            return body
        return json.loads(body)


def synthetic_detection():
    """Four independently noisy frames with one known, linear Gaussian source."""
    rng = random.Random(718)
    images = []
    for epoch in range(4):
        x0, y0 = 12 + 3 * epoch, 15 + 2 * epoch
        images.append([
            [rng.gauss(0, 1) + 35 * math.exp(-((x-x0)**2 + (y-y0)**2) / (2 * 1.2**2))
             for x in range(40)] for y in range(40)
        ])
    return {"images": images, "times": [0, 1, 2, 3]}


def check_http(base_url):
    health = request(base_url, "/health")
    assert health["status"] == "ok", health
    assert health["service"] == "spherex-ml-detector", health
    benchmark = request(base_url, "/benchmark/3i-atlas")
    assert benchmark["object"] == "3I/ATLAS", benchmark
    assert benchmark["observations"], "Benchmark observations missing"
    catalogue = request(base_url, "/api/motion/catalogue/candidates?limit=5")
    assert catalogue["status"] == "success", catalogue
    assert catalogue["total"] >= 4 and catalogue["candidates"], catalogue
    kpis = request(base_url, "/api/motion/catalogue/kpis")
    assert kpis["total_candidates"] >= 4, kpis
    detail = request(base_url, "/api/motion/catalogue/candidates/PX-000001")
    assert detail["id"] == "PX-000001", detail
    assert isinstance(request(base_url, "/api/motion/verifications"), list)
    assert isinstance(request(base_url, "/api/motion/candidates"), list)
    request(base_url, "/api/motion/coadd/PX-000001/motion.png")
    detection = request(base_url, "/api/motion/detect", synthetic_detection())
    assert detection["status"] == "success", detection
    assert detection["candidate_count"] == len(detection["candidates"]), detection
    recovered = any(
        candidate["epochs"] == [0, 1, 2, 3]
        and all(math.hypot(x - (12 + 3 * epoch), y - (15 + 2 * epoch)) <= 1.5
                for epoch, (x, y) in enumerate(candidate["positions_xy"]))
        for candidate in detection["candidates"]
    )
    assert recovered, "Synthetic linear source was not recovered over all four epochs"
    return {"status": "ok", "base_url": base_url, "catalogue_total": catalogue["total"],
            "detected_synthetic_tracks": detection["candidate_count"]}


def check_runtime():
    directory = Path(__file__).resolve().parent
    project = directory if (directory / "science").is_dir() else directory.parent
    sys.path.insert(0, str(project))
    for name in ("PIL.Image", "numpy", "scipy", "sklearn", "fastapi", "uvicorn",
                 "pydantic", "astropy.io.fits", "science.motion.live"):
        importlib.import_module(name)
    import numpy as np
    from PIL import Image
    assert json.loads((directory / "candidate-example.json").read_text())["object"] == "3I/ATLAS"
    with Image.open(directory / "spherex-result.png") as image:
        image.verify()
    with np.load(directory / "spherex_3i_atlas.npz", allow_pickle=False) as data:
        assert data["images"].ndim == 3 and data["times"].size >= 3
    for case in ("december-d2", "december-d6", "vesta-d3", "vesta-d6"):
        with np.load(project / "science" / "motion" / "cases" / f"{case}.npz",
                     allow_pickle=False) as data:
            assert data.files, f"Empty science fixture: {case}"


@contextmanager
def isolated_server():
    directory = Path(__file__).resolve().parent
    project = directory if (directory / "science").is_dir() else directory.parent
    with TemporaryDirectory(prefix="ml-deployment-smoke-", dir="/tmp") as scratch:
        env = dict(os.environ, VERIFICATIONS_DB_PATH=f"{scratch}/verifications.sqlite",
                   PLANETX_DB_PATH=f"{scratch}/planetx_catalogue.db",
                   PYTHONDONTWRITEBYTECODE="1", XDG_CACHE_HOME=f"{scratch}/cache")
        env["PYTHONPATH"] = os.pathsep.join((str(directory), str(project), env.get("PYTHONPATH", "")))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base_url = f"http://127.0.0.1:{port}"
        with open(f"{scratch}/server.log", "w+") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "service:app", "--host", "127.0.0.1",
                 "--port", str(port)], cwd=directory, env=env, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("Isolated service exited during startup")
                    try:
                        request(base_url, "/health", timeout=1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Isolated service did not become ready within 30 seconds")
                        time.sleep(0.1)
                yield base_url
            except BaseException:
                log.seek(0)
                sys.stderr.write(log.read())
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Check an existing service instead of starting an isolated one")
    parser.add_argument("--check-runtime", action="store_true", help="Also import dependencies and read packaged assets")
    args = parser.parse_args()
    if args.check_runtime or not args.base_url:
        check_runtime()
    if args.base_url:
        result = check_http(args.base_url)
    else:
        with isolated_server() as base_url:
            result = check_http(base_url)
            result["isolated_sqlite"] = True
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
