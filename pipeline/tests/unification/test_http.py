"""Boundary tests use real subprocesses; science is covered separately."""
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def payload():
    return {"schema_version": 1, "job_id": str(uuid.uuid4()), "inputs": [], "grid": {}}


def test_private_router_rejects_path_escape_and_oversized_body(tmp_path):
    from unification.http import create_router
    app = FastAPI()
    app.include_router(create_router(tmp_path))
    with TestClient(app) as client:
        request = payload()
        request["job_id"] = "../../escape"
        rejected = client.post("/internal/image-unifications", json=request)
        oversized = client.post("/internal/image-unifications", content=b"x" * 131073)
    assert rejected.status_code == 422
    assert oversized.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_deadline_kills_and_reaps_real_child(tmp_path, monkeypatch):
    from unification.http import Supervisor, WorkerFailure
    original = asyncio.create_subprocess_exec
    pid_file = tmp_path / "child.pid"
    children = []

    async def spawn(*args, **kwargs):
        process = await original(sys.executable, "-c",
            "import os,time,pathlib;pathlib.Path(" + repr(str(pid_file)) + ").write_text(str(os.getpid()));time.sleep(60)", **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)

    async def run():
        supervisor = Supervisor(tmp_path, deadline=0.4)
        with pytest.raises(WorkerFailure) as error:
            await supervisor.run(payload())
        assert error.value.status == 504
        assert children[0].returncode is not None
        assert not list(tmp_path.glob("unifications/*/request.json"))
    asyncio.run(run())
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


def test_disconnect_and_concurrent_admission_cleanup(tmp_path, monkeypatch):
    from unification.http import Supervisor, WorkerFailure
    original = asyncio.create_subprocess_exec
    spawned = asyncio.Event()
    children = []
    async def spawn(*args, **kwargs):
        process = await original(sys.executable, "-c", "import time;time.sleep(60)", **kwargs)
        children.append(process)
        spawned.set()
        return process
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)

    async def run():
        disconnected = asyncio.Event()
        async def check():
            return disconnected.is_set()
        supervisor = Supervisor(tmp_path, deadline=5)
        first = asyncio.create_task(supervisor.run(payload(), check))
        await spawned.wait()
        with pytest.raises(WorkerFailure) as error:
            await supervisor.run(payload())
        assert error.value.status == 429
        disconnected.set()
        with pytest.raises(WorkerFailure) as error:
            await first
        assert error.value.status == 499
        assert children[0].returncode is not None
        assert not supervisor.busy
    asyncio.run(run())


def test_cancel_during_spawn_reaps_child(tmp_path, monkeypatch):
    from unification.http import Supervisor
    original = asyncio.create_subprocess_exec
    children = []

    async def run():
        spawned = asyncio.Event()
        release = asyncio.Event()
        async def spawn(*args, **kwargs):
            child = await original(sys.executable, "-c", "import time;time.sleep(60)", **kwargs)
            children.append(child)
            spawned.set()
            await release.wait()
            return child
        monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
        supervisor = Supervisor(tmp_path, deadline=5)
        task = asyncio.create_task(supervisor.run(payload()))
        await spawned.wait()
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert children[0].returncode is not None
        assert not supervisor.busy
    asyncio.run(run())


def test_excessive_child_stdout_is_rejected_and_reaped(tmp_path, monkeypatch):
    from unification.http import Supervisor, WorkerFailure
    original = asyncio.create_subprocess_exec
    children = []
    async def spawn(*args, **kwargs):
        child = await original(sys.executable, "-c", "import sys,time;sys.stdout.write('x'*200000);sys.stdout.flush();time.sleep(60)", **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    async def run():
        with pytest.raises(WorkerFailure) as error:
            await Supervisor(tmp_path, deadline=5).run(payload())
        assert error.value.status == 502
        assert children[0].returncode is not None
    asyncio.run(run())


def test_real_worker_produces_loadable_bundle_over_http(tmp_path):
    import hashlib
    import numpy as np
    from astropy.io import fits
    from unification.http import create_router
    from unification.ml import load_bundle
    request = payload()
    request["grid"] = {"kind": "pixel", "width": 8, "height": 8}
    request["options"] = {"normalization": "none", "mask_policy": "science", "target_unit": None}
    source = tmp_path / "unifications" / request["job_id"] / "inputs" / "000.fits"
    source.parent.mkdir(parents=True)
    fits.PrimaryHDU(np.full((8, 8), 7, dtype=np.float32)).writeto(source)
    request["inputs"] = [{"id": "native-0", "path": source.relative_to(tmp_path).as_posix(),
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "profile": "generic",
        "image_hdu": None, "plane_indices": [], "metadata": {"provider": "test", "observation_id": "epoch-0"}}]
    app = FastAPI()
    app.include_router(create_router(tmp_path))
    with TestClient(app) as client:
        response = client.post("/internal/image-unifications", json=request)
    assert response.status_code == 200, response.text
    result = response.json()
    bundle_path = tmp_path / result["bundle"]["path"]
    bundle = load_bundle(bundle_path)
    assert bundle.images.shape == (1, 8, 8)
    assert np.allclose(bundle.images, 7)
    assert np.isfinite(bundle.tensor).all()
    assert hashlib.sha256(bundle_path.read_bytes()).hexdigest() == result["bundle"]["sha256"]
    assert not result["detection_ready"]


def test_composed_app_preserves_original_routes(monkeypatch, tmp_path):
    monkeypatch.setenv("UNIFICATION_DATA_ROOT", str(tmp_path))
    from unification.app import app
    paths = {(route.path, method) for route in app.routes for method in getattr(route, "methods", [])}
    assert {("/health", "GET"), ("/api/cutout/search", "POST"),
            ("/api/cutout/render", "GET"), ("/api/spectrum", "GET"),
            ("/api/spectrum/measure", "POST"),
            ("/internal/image-unifications", "POST")} <= paths
